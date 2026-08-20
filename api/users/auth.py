import os
import jwt
import pytz
import uuid
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import g, request, jsonify, make_response

from api.settings import IS_DEV
from database_api import Session
from database_api.operations import create, update, get_by_params, delete_bulk
from .setup import (
  DECODE_JWT_TOKEN,
  ACCESS_TOKEN_MINUTES,
  REFRESH_TOKEN_DAYS,
  REFRESH_COOKIE_NAME,
  REFRESH_TOMBSTONE_DAYS,
  REFRESH_GRACE_SECONDS,
)


REFRESH_COOKIE_PATH = os.environ.get('REFRESH_COOKIE_PATH', '/')
REFRESH_COOKIE_DOMAIN = os.environ.get('REFRESH_COOKIE_DOMAIN') or None
REFRESH_COOKIE_SAMESITE = os.environ.get('REFRESH_COOKIE_SAMESITE', 'Lax')
TRANSPORT_HEADER = 'X-Auth-Transport'


def _now():
  return datetime.now(pytz.utc)


def _aware(dt):
  # Postgres (timezone=True) rende datetime tz-aware; SQLite li restituisce
  # naive. Normalizziamo a UTC per confronti sicuri su entrambi.
  return dt if dt.tzinfo else dt.replace(tzinfo=pytz.utc)


def _tombstone_expiry():
  # Una riga revocata resta come lapide: serve solo a riconoscere il replay di
  # un refresh gia' speso, quindi ha una vita molto piu' corta di una sessione.
  return _now() + timedelta(days=REFRESH_TOMBSTONE_DAYS)


def _within_grace(session) -> bool:
  """La sessione e' stata ruotata da pochissimo?

  `rotated_at` e' opzionale: i progetti il cui modello non ha ancora la colonna
  si comportano come prima (nessuna grazia, replay = revoca di tutto).
  """
  rotated_at = getattr(session, 'rotated_at', None)
  if not rotated_at:
    return False
  return (_now() - _aware(rotated_at)).total_seconds() <= REFRESH_GRACE_SECONDS


def _hash_refresh(raw: str) -> str:
  return hashlib.sha256(raw.encode()).hexdigest()


def _wants_cookie(transport=None) -> bool:
  """Decide dove viaggia il refresh token: cookie HttpOnly o corpo JSON.

  I client browser non dichiarano nulla e prendono il cookie, che e' l'unica
  forma che un XSS non sa leggere. Un client nativo (app mobile, dove SameSite
  non esiste e un cookie jar sarebbe solo un impiccio) chiede esplicitamente il
  trasporto `bearer` con l'header X-Auth-Transport e si tiene il refresh token
  nel proprio storage sicuro.
  """
  choice = transport or request.headers.get(TRANSPORT_HEADER) or 'cookie'
  return str(choice).strip().lower() != 'bearer'


def create_access_token(user_id, role=None) -> str:
  payload = {
    'sub': str(user_id),
    'exp': (_now() + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp(),
  }
  if role is not None:
    payload['role'] = role.value if hasattr(role, 'value') else role
  return jwt.encode(payload, DECODE_JWT_TOKEN, algorithm='HS256')


def _strip_bearer(token):
  # Il prefisso si tollera da qualunque parte arrivi il token: header o query.
  # Chi costruisce l'URL di un media parte spesso dallo stesso valore che
  # metterebbe nell'header, e un `Bearer ` di troppo non e' un buon motivo per
  # rispondere "token non valido".
  if not token:
    return None
  token = token.strip()
  return token[7:].strip() if token.startswith('Bearer ') else token


def _read_access_token():
  return _strip_bearer(request.headers.get('Authorization', '')) or None


def build_auth(session_model, get_user_by_id):
  """Costruisce il sistema access/refresh per un progetto.

  - session_model: entita' con user_id, token_hash, expires_at, revoked
  - get_user_by_id: funzione (id) -> user, con attributi id e role
  """

  def _cleanup_expired_sessions(user_id):
    """Cancella le sessioni scadute dell'utente (lazy cleanup al login).

    Le righe revocate ma non ancora scadute non si toccano: sono le lapidi su
    cui si regge il riconoscimento del replay. Cancellarle renderebbe un token
    rubato indistinguibile da uno inventato.
    """
    old = [s for s in get_by_params(session_model, [('user_id', user_id)]) if _aware(s.expires_at) < _now()]
    if old:
      delete_bulk(old)

  def _lock_family(db, family_id):
    """Blocca le righe della famiglia per la durata della transazione.

    Serve a mettere in fila refresh e logout sulla stessa catena: senza, un
    logout puo' passare fra la rotazione e la nascita del successore, e il
    successore sopravviverebbe al logout.

    SQLite non conosce FOR UPDATE, ma serializza gia' le scritture per conto
    suo, quindi li' il lock esplicito si salta.
    """
    if not family_id:
      return []
    query = db.query(session_model).filter(session_model.family_id == family_id)
    if db.bind.dialect.name != 'sqlite':
      query = query.with_for_update()
    return query.all()

  def _revoke_family_rows(db, family_id) -> int:
    rows = [row for row in _lock_family(db, family_id) if not row.revoked]
    for row in rows:
      update(row, {'revoked': True, 'expires_at': _tombstone_expiry()}, session=db)
    return len(rows)

  def _family_has_live_row(db, family_id) -> bool:
    return any(
      not row.revoked and _aware(row.expires_at) >= _now()
      for row in db.query(session_model).filter(session_model.family_id == family_id).all()
    )

  def _issue_refresh(user_id, family_id: str = None, db=None) -> str:
    """Emette un refresh token.

    Ogni login apre una famiglia nuova; ogni rotazione resta nella famiglia da
    cui proviene. La famiglia e' cio' che lega un token alla propria catena, e
    quindi l'unica cosa su cui la finestra di grazia possa poggiare: sapere che
    *l'utente* ha una sessione viva non dice niente su questa catena.
    """
    raw = secrets.token_urlsafe(48)
    params = {
      'user_id': user_id,
      'token_hash': _hash_refresh(raw),
      'expires_at': _now() + timedelta(days=REFRESH_TOKEN_DAYS),
      'revoked': False,
      'family_id': family_id or str(uuid.uuid4()),
    }
    # Il kwarg session si passa solo se c'e' davvero una transazione aperta:
    # db_session_decorator, ricevendo session=None, ne aprirebbe una sua e poi
    # ripasserebbe il kwarg, andando in "multiple values for session".
    if db is not None:
      create(session_model, params, session=db)
    else:
      create(session_model, params)
    return raw

  def _find_session(raw: str):
    sessions = get_by_params(session_model, [('token_hash', _hash_refresh(raw))])
    return sessions[0] if sessions else None

  def _family_is_live(family_id) -> bool:
    """La catena a cui appartiene questo token e' ancora in piedi?

    La grazia copre un solo caso: la rotazione e' appena avvenuta e una
    richiesta partita prima arriva col token vecchio. Ha senso, quindi, solo se
    il successore di *quella* catena e' vivo. Guardare le sessioni dell'utente
    non basta: un altro dispositivo, con una famiglia sua, terrebbe in vita la
    grazia di una catena chiusa dal logout.

    Senza family_id (modello di un progetto non ancora aggiornato) si risponde
    di no: niente grazia, si torna al replay stretto.
    """
    if not family_id:
      return False
    return any(
      not row.revoked and _aware(row.expires_at) >= _now()
      for row in get_by_params(session_model, [('family_id', family_id)])
    )

  def _revoke_rows(rows) -> int:
    for row in rows:
      update(row, {'revoked': True, 'expires_at': _tombstone_expiry()})
    return len(rows)

  def revoke_family(family_id) -> int:
    """Chiude la catena compromessa, e solo quella.

    Chi ha rubato il token non ha nulla che appartenga alle altre famiglie:
    revocarle tutte non lo caccia fuori piu' di cosi', sloggia gli altri
    dispositivi dell'utente per niente.
    """
    rows = [row for row in get_by_params(session_model, [('family_id', family_id)]) if not row.revoked]
    return _revoke_rows(rows)

  def revoke_user_sessions(user_id) -> int:
    """Chiude tutte le sessioni attive di un utente.

    La usano il reuse detection e i progetti quando la password cambia: senza
    questa, reimpostare la password di un utente compromesso non caccia fuori
    chi gli ha rubato il refresh token, che resterebbe valido per giorni.
    """
    return _revoke_rows([s for s in get_by_params(session_model, [('user_id', user_id)]) if not s.revoked])

  def _set_cookie(response, raw: str):
    response.set_cookie(
      REFRESH_COOKIE_NAME,
      raw,
      max_age=REFRESH_TOKEN_DAYS * 24 * 3600,
      httponly=True,
      secure=not IS_DEV,
      samesite=REFRESH_COOKIE_SAMESITE,
      domain=REFRESH_COOKIE_DOMAIN,
      path=REFRESH_COOKIE_PATH,
    )

  def _read_refresh():
    """Legge il refresh token dal trasporto con cui e' arrivato."""
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
      return raw, True
    return (request.get_json(silent=True) or {}).get('refresh_token'), False

  def _token_response(user, raw: str, extra: dict = None, use_cookie: bool = True):
    body = {'status': 'ok', 'access_token': create_access_token(user.id, getattr(user, 'role', None))}
    if extra:
      body.update(extra)
    if not use_cookie:
      body['refresh_token'] = raw

    response = make_response(jsonify(body))
    if use_cookie:
      _set_cookie(response, raw)
    return response

  def login_response(user, extra: dict = None, transport: str = None):
    _cleanup_expired_sessions(user.id)
    return _token_response(user, _issue_refresh(user.id), extra, _wants_cookie(transport))

  def refresh():
    """Rinnova l'access token ruotando il refresh, in una sola transazione.

    Il punto delicato e' la concorrenza: due richieste che arrivano insieme col
    medesimo token leggerebbero entrambe la sessione come attiva e ruoterebbero
    entrambe, lasciando due sessioni vive nella stessa famiglia. La rotazione e'
    quindi un compare-and-swap: l'UPDATE filtra su revoked=false, una sola
    richiesta ottiene la riga e l'altra ne ottiene zero. Su Postgres la
    perdente si blocca sul lock di riga e rivaluta la condizione dopo il commit
    della vincente, quindi vede davvero lo stato aggiornato.
    """
    raw, use_cookie = _read_refresh()
    if not raw:
      return jsonify({'status': 'session', 'message': 'Sessione assente'}), 401

    token_hash = _hash_refresh(raw)
    invalid = jsonify({'status': 'session', 'message': 'Sessione non valida'}), 401

    with Session() as db:
      row = db.query(session_model).filter(session_model.token_hash == token_hash).first()
      if row is None:
        return invalid

      family_id = getattr(row, 'family_id', None)
      # Il lock va preso prima del compare-and-swap: mette in fila anche il
      # logout, che altrimenti potrebbe passare fra la revoca della riga vecchia
      # e la nascita del successore.
      _lock_family(db, family_id)
      db.refresh(row)

      # La scadenza si verifica qui e non nella WHERE: il confronto fra
      # datetime aware e colonne che SQLite restituisce naive non e' portabile,
      # mentre _aware() lo normalizza. La finestra e' di giorni, la precisione
      # al millisecondo non serve.
      if not row.revoked and _aware(row.expires_at) < _now():
        return invalid

      won = (
        db.query(session_model)
        .filter(session_model.token_hash == token_hash, session_model.revoked.is_(False))
        .update(
          {'revoked': True, 'rotated_at': _now(), 'expires_at': _tombstone_expiry()},
          synchronize_session=False,
        )
      )

      if won:
        user = get_user_by_id(row.user_id)
        if not user:
          db.commit()
          return jsonify({'status': 'session', 'message': 'Utente non trovato'}), 401

        new_raw = _issue_refresh(row.user_id, family_id, db=db)
        db.commit()
        return _token_response(user, new_raw, use_cookie=use_cookie)

      # Non abbiamo vinto la corsa: la riga era gia' revocata.
      db.refresh(row)
      if _within_grace(row) and _family_has_live_row(db, family_id):
        # Due schede (o due richieste partite insieme) hanno scoperto l'access
        # token scaduto nello stesso momento. E' il caso normale, non un furto,
        # e trattarlo come replay sloggherebbe l'utente ogni volta che tiene
        # aperte due schede.
        #
        # La condizione e' sulla famiglia, non sull'utente: se il successore di
        # questa catena e' stato revocato (logout, reset password) non c'e'
        # nessuna corsa da giustificare, nemmeno se un altro dispositivo dello
        # stesso utente ha ancora una sessione sua.
        #
        # Qui NON si emette una sessione nuova. Un token gia' speso non puo'
        # generarne altre: se lo facesse, chi lo ha rubato potrebbe riusarlo a
        # ripetizione per tutta la finestra creando una sessione per volta. Si
        # restituisce solo un access token, senza toccare il cookie: il
        # chiamante prosegue col refresh che la rotazione ha gia' messo nel
        # barattolo, condiviso fra le schede.
        user = get_user_by_id(row.user_id)
        if not user:
          return jsonify({'status': 'session', 'message': 'Utente non trovato'}), 401
        db.commit()
        return jsonify({'status': 'ok', 'access_token': create_access_token(user.id, getattr(user, 'role', None))})

      # Reuse detection: un refresh gia' speso che riappare fuori dalla finestra
      # e' o una copia rubata, o il legittimo proprietario a cui l'hanno rubata
      # e ruotata sotto il naso. Non sapendo distinguerli, si chiude la catena.
      if family_id:
        _revoke_family_rows(db, family_id)
      else:
        # Modello senza famiglie: non sapendo quale catena sia, si chiude tutto.
        for stale in db.query(session_model).filter(session_model.user_id == row.user_id).all():
          if not stale.revoked:
            update(stale, {'revoked': True, 'expires_at': _tombstone_expiry()}, session=db)
      db.commit()
      return invalid

  def logout():
    """Chiude la sessione, e con essa tutta la sua catena.

    Il token presentato puo' benissimo essere gia' stato ruotato: basta che il
    refresh automatico sia passato un istante prima del click. Fermarsi alla
    riga trovata, come si faceva, lasciava vivo il successore e il logout non
    chiudeva niente. Si revoca quindi la famiglia, sotto lo stesso lock che usa
    il refresh, cosi' una rotazione in corso non riesce a infilare un successore
    dopo la revoca.
    """
    raw, _ = _read_refresh()
    if raw:
      with Session() as db:
        row = db.query(session_model).filter(session_model.token_hash == _hash_refresh(raw)).first()
        if row is not None:
          family_id = getattr(row, 'family_id', None)
          if family_id:
            _revoke_family_rows(db, family_id)
          elif not row.revoked:
            update(row, {'revoked': True, 'expires_at': _tombstone_expiry()}, session=db)
          db.commit()

    response = make_response(jsonify({'status': 'ok', 'message': 'Logout effettuato'}))
    response.delete_cookie(REFRESH_COOKIE_NAME, domain=REFRESH_COOKIE_DOMAIN, path=REFRESH_COOKIE_PATH)
    return response

  def authentication(roles=None, allow_query_token=False):
    if callable(roles):
      return _decorate(roles, None, False)
    return lambda func: _decorate(func, roles, allow_query_token)

  def _decorate(func, roles, allow_query_token):
    @wraps(func)
    def wrapper(*args, **kwargs):
      # L'header resta la via maestra anche sugli endpoint media: la query e'
      # un ripiego per i contesti che non possono mandare header (src di <img>,
      # download diretti). Trattarla come sostituto invece che come aggiunta
      # rendeva impossibile chiamare quegli endpoint via fetch, ed e' cio' che
      # obbliga il frontend a mettere il token nell'URL.
      token = _read_access_token()
      if not token and allow_query_token:
        token = _strip_bearer(request.args.get('token'))
      if not token or token == 'null':
        return jsonify({'status': 'session', 'message': 'Token assente'}), 401

      try:
        payload = jwt.decode(token, DECODE_JWT_TOKEN, algorithms=['HS256'])
      except jwt.ExpiredSignatureError:
        return jsonify({'status': 'session', 'message': 'Token scaduto'}), 401
      except jwt.InvalidTokenError:
        return jsonify({'status': 'session', 'message': 'Token non valido'}), 401

      # Un token firmato ma di formato vecchio (o comunque senza `sub` numerico)
      # non deve diventare un 500: e' solo un token che non vale piu'.
      try:
        user_id = int(payload['sub'])
      except (KeyError, TypeError, ValueError):
        return jsonify({'status': 'session', 'message': 'Token non valido'}), 401

      user = get_user_by_id(user_id)
      if not user:
        return jsonify({'status': 'session', 'message': 'Utente non trovato'}), 401

      if roles and user.role not in roles:
        return jsonify({'status': 'forbidden', 'message': 'Ruolo non autorizzato'}), 403

      g.log_user = user
      return func(user, *args, **kwargs)

    return wrapper

  return SimpleAuth(login_response, refresh, logout, authentication, revoke_user_sessions, revoke_family)


class SimpleAuth:
  def __init__(self, login_response, refresh, logout, authentication, revoke_user_sessions, revoke_family):
    self.login_response = login_response
    self.refresh = refresh
    self.logout = logout
    self.authentication = authentication
    self.revoke_user_sessions = revoke_user_sessions
    self.revoke_family = revoke_family
