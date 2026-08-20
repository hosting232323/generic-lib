import os
import jwt
import pytz
import uuid
import hashlib
import secrets
from functools import wraps
from contextlib import contextmanager
from datetime import datetime, timedelta
from flask import g, request, jsonify, make_response

from api.settings import IS_DEV
from database_api import Session
from database_api.operations import create, get_by_params, delete_bulk
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


def build_auth(session_model, get_user_by_id, user_model=None):
  """Costruisce il sistema access/refresh per un progetto.

  - session_model: entita' con user_id, token_hash, expires_at, revoked,
    rotated_at, family_id
  - get_user_by_id: funzione (id) -> user, con attributi id e role
  - user_model: entita' utente, usata come punto di serializzazione stabile fra
    login, refresh, logout e reset password. Omettendola si perde quella
    garanzia, non il funzionamento.
  """

  def _cleanup_expired_sessions(user_id, db=None):
    """Cancella le sessioni scadute dell'utente (lazy cleanup al login).

    Le righe revocate ma non ancora scadute non si toccano: sono le lapidi su
    cui si regge il riconoscimento del replay. Cancellarle renderebbe un token
    rubato indistinguibile da uno inventato.
    """
    rows = (
      db.query(session_model).filter(session_model.user_id == user_id).all()
      if db is not None
      else get_by_params(session_model, [('user_id', user_id)])
    )
    old = [s for s in rows if _aware(s.expires_at) < _now()]
    if old:
      if db is not None:
        delete_bulk(old, session=db)
      else:
        delete_bulk(old)

  def _lock_user(db, user_id):
    """Serializza le operazioni di sessione dello stesso utente.

    Il lock deve stare su una riga **stabile**. Bloccare le righe di sessione
    non basta: FOR UPDATE blocca quelle viste dalla query, non impedisce a una
    rotazione concorrente di inserirne una nuova, e il successore appena nato
    sfuggirebbe alla revoca. La riga utente invece c'e' sempre ed e' la stessa
    per login, refresh, logout e reset password, che e' esattamente l'insieme
    di operazioni da mettere in fila.

    Senza user_model (progetto non ancora aggiornato) si prosegue senza lock,
    col comportamento di prima. Su SQLite si salta: le scritture sono gia'
    serializzate e FOR UPDATE non esiste.
    """
    if user_model is None or db.bind.dialect.name == 'sqlite':
      return
    db.query(user_model).filter(user_model.id == user_id).with_for_update().first()

  def _reload_user(db, user_id):
    """Rilegge l'utente dentro la transazione che tiene il lock.

    L'istanza che il chiamante ha in mano e' stata caricata prima: se nel
    frattempo e' passato un reset password, e' gia' vecchia.
    """
    if user_model is None:
      return None
    return db.query(user_model).filter(user_model.id == user_id).first()

  def _revoke_where(db, *conditions) -> int:
    """Revoca in un solo statement, cosi' vede tutto cio' che e' committato.

    Una lista di righe letta prima del lock sarebbe gia' vecchia quando la si
    usa: l'UPDATE per condizione, eseguito dopo il lock, prende anche le righe
    nate nel frattempo.
    """
    return (
      db.query(session_model)
      .filter(session_model.revoked.is_(False), *conditions)
      .update({'revoked': True, 'expires_at': _tombstone_expiry()}, synchronize_session=False)
    )

  def _revoke_family_rows(db, family_id) -> int:
    return _revoke_where(db, session_model.family_id == family_id)

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

  @contextmanager
  def user_session_lock(user_id):
    """Transazione con la riga utente bloccata, condivisibile col chiamante.

    Serve a chi deve cambiare qualcosa dell'utente *e* chiudergli le sessioni
    nello stesso atto: il reset password. Facendolo in due transazioni separate,
    un refresh concorrente puo' infilarsi in mezzo e creare un successore dopo
    la revoca, lasciando dentro proprio chi si voleva cacciare fuori.
    """
    with Session() as db:
      _lock_user(db, user_id)
      yield db
      db.commit()

  def revoke_family(family_id, db=None) -> int:
    """Chiude la catena compromessa, e solo quella.

    Chi ha rubato il token non ha nulla che appartenga alle altre famiglie:
    revocarle tutte non lo caccia fuori piu' di cosi', sloggia gli altri
    dispositivi dell'utente per niente.
    """
    if db is not None:
      return _revoke_family_rows(db, family_id)

    with Session() as own:
      # Serve l'utente per prendere il lock: senza, un refresh concorrente
      # infilerebbe il successore dopo la revoca, come succedeva al logout.
      row = own.query(session_model).filter(session_model.family_id == family_id).first()
      if row is None:
        return 0
      _lock_user(own, row.user_id)
      revoked = _revoke_family_rows(own, family_id)
      own.commit()
      return revoked

  def revoke_user_sessions(user_id, db=None) -> int:
    """Chiude tutte le sessioni attive di un utente.

    La usano il reuse detection e i progetti quando la password cambia: senza
    questa, reimpostare la password di un utente compromesso non caccia fuori
    chi gli ha rubato il refresh token, che resterebbe valido per giorni.

    Passando `db` si entra nella transazione del chiamante — che deve gia'
    tenere il lock utente, tipicamente via user_session_lock.
    """
    if db is not None:
      return _revoke_where(db, session_model.user_id == user_id)
    with user_session_lock(user_id) as own:
      return _revoke_where(own, session_model.user_id == user_id)

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

  def login_response(user, extra: dict = None, transport: str = None, verify=None):
    """Apre una sessione per l'utente.

    `verify` e' una funzione (utente_riletto, transazione) -> bool eseguita
    **dentro** il lock. Serve al login: verificare la password prima lascia una
    finestra in cui un reset password concorrente cambia le credenziali e revoca
    le sessioni, mentre il login prosegue con quelle vecchie e ne apre una nuova.
    Verifica, eventuale migrazione dell'hash e nascita della sessione devono
    essere lo stesso atto.

    Se `verify` restituisce False, non viene creata nessuna sessione e la
    risposta e' None: l'errore lo formula il chiamante, che sa cosa dire.
    """
    with Session() as db:
      _lock_user(db, user.id)
      # L'utente si rilegge dopo il lock: prima poteva essere gia' cambiato.
      fresh = _reload_user(db, user.id) or user
      if verify is not None and not verify(fresh, db):
        return None

      _cleanup_expired_sessions(fresh.id, db=db)
      raw = _issue_refresh(fresh.id, db=db)
      db.commit()
    return _token_response(fresh, raw, extra, _wants_cookie(transport))

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
      # Il lock va preso prima del compare-and-swap: mette in fila anche logout
      # e reset password, che altrimenti potrebbero passare fra la revoca della
      # riga vecchia e la nascita del successore.
      _lock_user(db, row.user_id)
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
        _revoke_where(db, session_model.user_id == row.user_id)
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
          _lock_user(db, row.user_id)
          family_id = getattr(row, 'family_id', None)
          if family_id:
            _revoke_family_rows(db, family_id)
          else:
            _revoke_where(db, session_model.id == row.id)
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

  return SimpleAuth(
    login_response, refresh, logout, authentication, revoke_user_sessions, revoke_family, user_session_lock
  )


class SimpleAuth:
  def __init__(
    self, login_response, refresh, logout, authentication, revoke_user_sessions, revoke_family, user_session_lock
  ):
    self.login_response = login_response
    self.refresh = refresh
    self.logout = logout
    self.authentication = authentication
    self.revoke_user_sessions = revoke_user_sessions
    self.revoke_family = revoke_family
    self.user_session_lock = user_session_lock
