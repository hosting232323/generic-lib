# Branch `feat/session-refactor` — Stato, analisi e TODO

> Analisi trasversale ai 4 repo coinvolti: **generic-lib**, **generic-fe**, **italco-fe**, **italco-be**.
> Documento vivo: aggiornarlo a ogni evolutiva o quando un punto del TODO viene chiuso.

---

## ⚠️ Regola operativa non negoziabile

**Ogni commit, prima di essere pushato, deve avere la pipeline VERDE.**

- Non si pusha su un branch condiviso con la pipeline rossa o "in dubbio".
- Se la pipeline diventa rossa, la priorità è rimetterla verde **prima** di qualsiasi altra evolutiva.
- Vale per tutti e 4 i repo. Per italco-be la CI gira i test in Postgres e richiede la env `DECODE_JWT_TOKEN` (configurata in `gitlab/test.yml` e `.env.test`).
- Comando locale di verifica prima del push (**da eseguire sulla macchina locale**, in ciascun repo interessato):

```bash
# italco-be — nella cartella del repo
pytest
```

```bash
# generic-lib — nella cartella del repo
pytest tests/test_auth.py
```

---

## 1. Obiettivo del branch

Sostituire il vecchio schema di autenticazione (JWT "monolitico" a lunga durata, token persistito nel `localStorage`, password gestita male tra FE e BE) con un modello **access token + refresh token** standard:

- **Access token** (JWT HS256, breve durata — default **15 min**): viaggia nell'header `Authorization`, vive **solo in memoria** lato FE.
- **Refresh token** (random opaco 48 byte, durata **30 giorni**): in un **cookie HttpOnly** (`Secure` fuori da dev, `SameSite=Lax`), mai leggibile da JS. Salvato lato DB **solo come hash SHA-256**, con **rotazione a ogni refresh** e revoca su logout.
- Rinnovo trasparente: al primo `401` il client HTTP chiama `/refresh` una sola volta, riottiene l'access token e ripete la richiesta originale.

---

## 2. Architettura nuova (generic-lib)

Il cuore condiviso sta in **generic-lib**, riusabile da tutti i backend.

### `api/users/auth.py` — `build_auth(session_model, get_user_by_id)`
Factory che restituisce un oggetto `SimpleAuth` con:

| Metodo | Cosa fa |
|---|---|
| `login_response(user, extra, transport)` | Emette access token + refresh token, risposta JSON `{status, access_token, ...extra}` |
| `refresh()` | Valida la sessione, **ruota** il refresh token, restituisce un nuovo access token |
| `logout()` | Revoca la sessione (`revoked=True`) e cancella il cookie |
| `authentication(roles, allow_query_token)` | Decoratore: valida l'access token, applica il controllo ruolo, inietta `g.log_user` e passa `user` alla view |
| `revoke_user_sessions(user_id)` | Chiude tutte le sessioni attive di un utente (reset password, reuse detection) |

### Il trasporto del refresh token è pluggabile

Il nucleo (token opaco, SHA-256 a riposo, rotazione, revoca) è unico; cambia
solo **dove viaggia** il refresh token:

| Client | Trasporto | Dove sta | Come lo chiede |
|---|---|---|---|
| Browser (italco-fe, fastsite-fe) | cookie `HttpOnly` | browser | default, non dichiara nulla |
| Client nativo (delivery-app) | campo `refresh_token` nel body JSON | secure storage del device | header `X-Auth-Transport: bearer` |

Serviva perché `delivery-app` è un client Flutter con `package:http`: le policy
`SameSite` sono del browser e lì non esistono, e un cookie jar sarebbe solo un
impiccio. Su nativo, per giunta, non c'è XSS, quindi il refresh token in secure
storage è più sicuro che in un cookie.

`refresh()` e `logout()` leggono il cookie e, se assente, il body; rispondono
con lo stesso trasporto con cui sono stati chiamati.

### Reuse detection

La rotazione non aggiorna più la riga in place: la vecchia diventa una **lapide
revocata** (con scadenza accorciata a `REFRESH_TOMBSTONE_DAYS`, default 7) e il
token nuovo nasce su una riga sua. Se qualcuno ripresenta un refresh già speso,
non è più indistinguibile da un token inventato: si sa che è un replay, e
`revoke_user_sessions` chiude **tutte** le sessioni dell'utente.

Senza questo, chi ruba il refresh token e lo usa per primo resta dentro mentre
la vittima si becca un 401 e rifà login. È il controllo che regge l'intero
canale bearer, dove il token non è protetto da `HttpOnly`.

Il cleanup al login cancella solo le sessioni **scadute**: le lapidi revocate
vanno tenute, sono ciò su cui si regge il riconoscimento del replay.

Dettagli di sicurezza già corretti:
- Refresh token salvato **solo hashato** (SHA-256) — un dump della tabella `user_session` non espone token utilizzabili.
- **Rotazione** del refresh a ogni `/refresh`; il replay di un token già ruotato viene respinto (401).
- Distinzione **401** (`status: session` → sessione da rinnovare/rifare login) vs **403** (`status: forbidden` → ruolo non abilitato).
- Cookie `HttpOnly` + `Secure` (in prod) + `SameSite=Lax` → riduce XSS-exfiltration e CSRF sul refresh.
- Config via env: `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`, `REFRESH_COOKIE_NAME`, `REFRESH_COOKIE_*`.

### `api/users/security.py`
- `hash_password` / `verify_password`: hashing tramite **werkzeug** (scrypt/pbkdf2).
- `is_hashed`: euristica per distinguere un hash werkzeug da una password legacy in chiaro/AES.

### Retrocompatibilità
La vecchia `build_session_authentication(...)` è **ancora presente** in `api/users/__init__.py`: gli altri progetti non ancora migrati continuano a funzionare. Solo italco-be è passato a `build_auth`.

### Test
`tests/test_auth.py` copre: login+cookie HttpOnly, rotazione, replay rifiutato, logout+revoca, 401 senza token, 403 ruolo errato, prefisso `Bearer` opzionale, token in query (quando abilitato).

---

## 3. Cosa è cambiato per progetto

### generic-lib
- Nuovi `auth.py`, `security.py`; costanti in `setup.py`. Test aggiunti. Nessuna rottura per i progetti legacy.

### generic-fe (libreria `generic-module`)
- **`src/utils/http.js`**: aggiunto `refreshEndpoint` + `credentials`. Logica `refreshAccessToken` con lock (`refreshing`) per evitare refresh concorrenti; `executeFetch` che intercetta il 401, rinnova e **ripete** la richiesta. Comportamento invariato se `refreshEndpoint` non è configurato.
- **Rimosso `src/utils/encrypt.js`** (AES lato client con CryptoJS) e la dipendenza relativa → vedi §4.
- Adeguati `AuthManager.vue`, `UserLogin.vue`, `UserPassword.vue`.

### italco-fe
- **`stores/user.js`**: l'access token **non è più persistito**; si persistono solo `role` e `userId` per la UI. Al reload l'access token si riottiene dal refresh cookie.
- **`utils/http.js`**: configura `refreshEndpoint: 'user/refresh'`; `withSessionToken` mantenuto per i media protetti (legge l'access token in memoria).
- **`utils/logout.js`**: nuovo — chiama `user/logout` (revoca server-side) e resetta tutti gli store.
- **`UserTable.vue`**: la "mostra password" admin è stata **sostituita** con un dialog "Reimposta password" (vedi §5).
- Modifiche collaterali (ChattyBot, importazioni, layout) legate all'allineamento chatty/UI.

### italco-be
- **`end_points/__init__.py`**: da `build_session_authentication` a `auth = build_auth(UserSession, ...)`.
- **`schema.py`**: nuova entità `UserSession` (user_id, token_hash unico+indicizzato, expires_at, revoked). `format_user` per l'ADMIN **non espone** `password`.
- **Migration `050_user_session.py`**: crea `user_session` (+ indici).
- **`end_points/users/__init__.py`**: `create_user` salva password **hashata**, restituisce il valore una sola volta; `login` verifica con `check_password`, **migra al volo** i vecchi utenti (re-hash) al primo login corretto. Endpoint `POST <id>/password` per admin reset/rigenera. Nuovi endpoint `refresh`, `logout`.
- **`end_points/users/legacy.py`**: `legacy_encrypt` per riconoscere le vecchie password AES durante la migrazione al primo login.
- **`__init__.py`**: `CORS(..., supports_credentials=True)` (necessario per il cookie refresh cross-origin).
- **`chatty.py`**: rinomina rotta/payload (`chat`→`message`, `session_id`→`thread_id`) — allineamento, non auth.

---

## 4. Il nodo password FE → BE (la tua preoccupazione)

> "Non mi piace mandare la password in chiaro dal FE al BE nonostante l'HTTPS."

**Ti confermo che mandarla in chiaro sotto HTTPS e hasharla lato server è la scelta giusta.** Ecco il perché, senza girarci intorno:

1. **L'HTTPS/TLS è esattamente il meccanismo pensato per questo.** In transito la password è già cifrata dal canale (AES a livello TLS). "In chiaro nel body" significa in chiaro *dentro* il tunnel cifrato, non sulla rete.
2. **La vecchia cifratura AES lato client era "security theater".** La chiave (`VITE_SECRET_KEY`) e l'IV erano nel bundle JavaScript → pubblici per chiunque apra i devtools. Cifrare con una chiave pubblica non protegge nulla: chiunque può decifrare.
3. **Peggio: hashare/cifrare lato client trasforma il risultato nella "vera password".** Se il BE ricevesse un blob e lo confrontasse così com'è, quel blob diventa la credenziale: chi lo intercetta si autentica senza conoscere la password originale. Si sposta il problema, non si risolve.
4. **L'unico punto in cui la password deve essere protetta a riposo è il DB**, ed è ciò che ora fa il BE con werkzeug (scrypt): hash **non reversibile** + salt. È lo standard OWASP.

**Conclusione:** la rimozione di `encrypt.js` lato FE e l'hashing lato BE sono **corretti**. Non c'è niente da recuperare su quel fronte.

---

## 5. Vulnerabilità e punti aperti

Ordinati per gravità.

### ✅ RISOLTO — `password_shadow`: copia reversibile della password

> **Implementato il 29-07.** La copia AES reversibile è stata **completamente rimossa**:
> - `generic-lib`: `encrypt_reversible`/`decrypt_reversible`/`_shadow_key`/`PASSWORD_SHADOW_KEY` eliminati da `security.py`.
> - `italco-be`: rimossi shadow da `create_user`/`login`, eliminato endpoint `GET <id>/password` e `reveal_user_password`, rimossa colonna `password_shadow` (schema + migration 050), rimossa `legacy_decrypt`. Aggiunto `POST <id>/password` (admin reimposta/rigenera → valore mostrato una volta).
> - `italco-fe`: `UserTable.vue` occhio reveal → dialog "Reimposta password" con campo copiabile; `UserForm.vue` mostra password dopo creazione utente; store `revealPassword` → `resetPassword`.
> - env/CI: `PASSWORD_SHADOW_KEY` rimossa da `.env`, `.env.sample`, `.env.test`, `gitlab/test.yml`.
>
> Il DB non contiene più password reversibili. Il rischio critico è **chiuso**.

### ✅ RISOLTO — replay concorrente con piu' schede aperte

> La reuse detection, da sola, sloggiava l'utente ovunque nel caso piu' normale:
> due schede aperte scoprono l'access token scaduto nello stesso momento e
> chiamano `/refresh` con lo stesso cookie. La seconda arrivava con un token
> gia' ruotato e veniva letta come furto.
>
> Introdotta una **finestra di grazia** (`REFRESH_GRACE_SECONDS`, default 30s):
> un refresh revocato **dalla rotazione** da pochi secondi non e' un replay, e
> alla seconda scheda viene data una sessione sua. Fuori dalla finestra, e per i
> token revocati da logout o reset password, vale la reuse detection piena.
>
> Durante la grazia **non viene emessa nessuna sessione nuova**: si restituisce
> solo un access token, senza toccare il cookie. Emetterne una permetterebbe a
> chi ha rubato il token di rigiocarlo per tutta la finestra creando una
> sessione per volta, e lascerebbe sessioni orfane anche nel caso legittimo. La
> grazia si applica inoltre solo se l'utente ha ancora una sessione viva: dopo
> un logout o un reset password non c'e' nessuna corsa fra schede da
> giustificare.
>
> La grazia si valuta **sulla famiglia del token**, non sull'utente: ogni login
> apre una famiglia, ogni rotazione vi resta dentro. Guardare le sessioni
> dell'utente non bastava — un secondo dispositivo, con una famiglia sua, teneva
> in vita la grazia di una catena gia' chiusa dal logout, e la richiesta
> ritardata otteneva un access token buono. Stessa logica per la reuse
> detection, che ora revoca la sola catena compromessa: chi ha rubato quel token
> non possiede nulla delle altre famiglie.
>
> Distinzione portata dalle colonne `user_session.rotated_at` (migration 051) e
> `user_session.family_id` (migration 052):
> e' valorizzata solo dalla rotazione. `build_auth` la legge con `getattr`,
> quindi i progetti il cui modello non ce l'ha si comportano come prima.

### 🟠 MEDIO — AES-CBC senza autenticazione (legacy)
`legacy_encrypt` usa **AES-CBC senza MAC**: cifratura malleabile. È solo un ponte di migrazione (verifica delle vecchie password al primo login) e sparisce con la dismissione di `legacy.py`. `legacy_decrypt` è già stata rimossa.

### 🟠 MEDIO — Chiave/IV legacy hardcoded come default
`legacy.py`: `LEGACY_PASSWORD_SECRET_KEY = os.environ.get(..., 'local-dev-key-1234567890')` e IV `'1234567890123456'` di default. Accettabile solo come ponte di migrazione. In prod le env devono essere valorizzate esplicitamente e il fallback andrà rimosso a migrazione completata (`legacy.py` va poi eliminato del tutto).

### 🟠 MEDIO — token in querystring sui media (`allow_query_token`)
Gli endpoint media di italco-be (`orders/photos/<file>`, `rae/<folder>/<file>`) usano `allow_query_token=True` e il FE manda l'**access token in querystring** via `http.withSessionToken(url)`. L'access token JWT finisce in **log di accesso del server, cronologia del browser e header Referer**. È mitigato dalla vita breve (15 min), ma resta un vettore di leak.

**Sbloccato il 17-08:** `allow_query_token` non è più *alternativo* all'header ma
*aggiuntivo*. Prima quegli endpoint ignoravano `Authorization`, il che rendeva
la querystring l'unica strada possibile e quindi obbligatoria; ora si possono
scaricare via `fetch` + blob con l'header, senza toccare il backend. Il token
è anche tollerato con prefisso `Bearer ` nella query (era la causa dei ~10 test
media rossi: `query_token` passava `Bearer <jwt>` nell'URL).

**Resta da fare lato FE:** sostituire `withSessionToken(url)` con fetch+blob, e
decidere se serve comunque un token media dedicato per i `<img>` (dove l'header
non è mandabile). Con l'access token a 15 minuti, un URL "congelato" nel `src`
al render smette di funzionare dopo un quarto d'ora.

### 🟡 BASSO — `verify_password` con fallback plaintext
In `security.py`, se `stored` non è hashato, `verify_password` fa `stored == raw_password` (confronto in chiaro). È il ponte per i progetti non ancora migrati. Da rimuovere una volta migrati tutti gli utenti/progetti.

### 🟡 BASSO — CORS in dev troppo permissivo con credenziali
`IS_DEV`: `CORS(app, supports_credentials=True)` riflette qualsiasi origin **con** credenziali. Solo in dev, ma verificare che in prod `allowed_origins` sia una **lista esplicita** (niente `*`).

### 🟡 BASSO — `DECODE_JWT_TOKEN` in prod
Il segreto JWT HS256 dev'essere lungo e casuale in produzione (in test è `dummy`, corretto). Verificare il valore prod nel secret manager.

---

## 6. TODO — come andare avanti

### Bloccanti prima del merge
- [x] ~~**Implementare "solo hash + reset"** (§5)~~ → **FATTO** (29-07)
- [x] ~~Reuse detection sul refresh token~~ → **FATTO** (17-08, §2)
- [x] ~~Revoca delle sessioni al reset password~~ → **FATTO** (17-08)
- [x] ~~Trasporto bearer per i client nativi~~ → **FATTO** (17-08, §2)
- [ ] **`delivery-app` va aggiornata prima del deploy di italco-be** (§9)
- [ ] **Rollout librerie prima delle app** (§8.1): portare `generic-lib` e `generic-fe` sul branch di default GitHub (o pinnare `@feat/session-refactor`) **prima** di attendersi pipeline verdi su italco.
- [ ] **Testare i media su pagina aperta >15 min** (§8.2): verificare che foto/documenti non si rompano quando l'access token nell'URL scade; decidere la strategia (URL lazy / refresh pre-media / TTL dedicato).
- [ ] Verificare che **tutti i test siano verdi** in ciascun repo e che la **pipeline** giri verde (regola in cima).
- [ ] Provare end-to-end il flusso reale su italco: login → uso app oltre i 15 min (refresh automatico) → reload pagina (riottiene access token dal cookie) → logout (cookie revocato e cancellato).
- [ ] Verificare `allowed_origins` espliciti in prod con `supports_credentials=True`.

### Migrazione dati / rollout
- [ ] Applicare la **migration 050** su tutti gli ambienti (staging → prod) e verificare l'esistenza di `user_session`.
- [ ] Confermare che il **login-time migration** (re-hash al primo accesso) copra tutti gli utenti attivi; pianificare come gestire gli utenti che non fanno login da tempo.
- [ ] Definire la **data di dismissione di `legacy.py`** (e la rimozione dei default hardcoded) una volta migrati tutti.

### Hardening
- [ ] Rimuovere il fallback plaintext in `verify_password` a migrazione conclusa.
- [ ] Valutare **reuse-detection** del refresh token (revoca dell'intera "famiglia" al rilevamento di un replay) — oggi il token ruotato viene solo rifiutato.
- [ ] Valutare un tetto al numero di sessioni attive per utente + job di **pulizia** delle `user_session` scadute/revocate.

### Estensione agli altri progetti (dopo italco)
- [ ] Portare `build_auth` sugli altri backend che oggi usano ancora `build_session_authentication`, uno alla volta, ognuno con la propria pipeline verde.

---

## 7. Riepilogo commit del branch

| Repo | Commit |
|---|---|
| generic-lib | `sistema access token + refresh token` · `rimozione password shadow — solo hash + reset` |
| generic-fe | `refresh-on-401 nel client http e rimozione AES lato client` |
| italco-fe | `adotta sessione access/refresh e rimuove esposizione password` · `reimposta password admin (sostituisce reveal)` |
| italco-be | `adotta sessione access/refresh token` · `rimozione password shadow — solo hash + reset admin` |

> Nota: alcuni commit di italco-be hanno messaggi generici (`push`, `bug-fix`). Prima del merge, valutare un rebase/squash per una history leggibile.

---

## 8. Rebase su `origin/main` (29-07) — integrazioni assorbite e adattamenti

Il branch `feat/session-refactor` è stato **rebasato su `origin/main`** in tutti e 4 i repo.

| Repo | Base ora | Conflitti | Risoluzione |
|---|---|---|---|
| generic-lib | `3983889` (email-attachments) | nessuno | — |
| generic-fe | `d5964b9` (chatty/fix-session) | solo `dist/generic-module.es.js` (artefatto) | **rigenerato** con `npm run build` dal sorgente mergiato (104 kB) |
| italco-be | `6a80b98` (attached-1) | `end_points/__init__.py`, `tests/.../test_init.py` | tenuta la nostra versione (`build_auth` + test nuovi) |
| italco-fe | `bd21698` (token-on-media-urls) | nessuno (riconciliato in auto) | vedi sotto |

### ⚠️ Adattamenti ANCORA DA FARE / da verificare
1. **Ordine di rollout delle librerie (blocca la pipeline verde).**
   `italco-be/pyproject.toml` installa `generic_lib` da `git+https://github.com/hosting232323/generic-lib.git` senza pin di branch. Idem `italco-fe/package.json` con `generic-module`. Finché la nuova lib non è sul **branch di default GitHub**, la CI italco installa la lib **vecchia** e fallisce.
   → **Sequenza obbligata:** (a) push/merge `generic-lib` e `generic-fe` verso il default GitHub, **poi** (b) le pipeline italco possono diventare verdi.
2. **Scadenza del token nelle URL media (regressione funzionale possibile).**
   `withSessionToken` "congela" l'access token nel `src`/`href` al momento del render. Dopo ~15 min quell'URL contiene un token scaduto. Da decidere: (a) costruire la URL al click/lazy, (b) forzare un refresh prima di generare le URL media, (c) token media dedicato.
3. **`package-lock.json` di italco-fe**: modifica WIP non correlata **messa in stash** prima del rebase. Recuperabile con `git stash pop`.

### Verifiche eseguite
- generic-lib: `pytest tests/test_auth.py` → **9 passed** ✅
- generic-fe: `npm run build` → OK (104 kB) ✅
- italco-fe: `npm run build` → OK ✅
- italco-be: `pytest tests/unit` → **507 passed** ✅ (10 failed pre-esistenti su endpoint media, vedi §8.2)

---

## 9. Incremento del 17-08 — invariante same-origin, trasporto, verifiche

### L'invariante su cui poggia tutto il design a cookie

Verificata sui repo, non assunta:

> **Le sessioni sono sempre same-origin. Il cross-origin è sempre anonimo.**

- Tutti i backend usano lo stesso template di deploy: Traefik
  `Host(${PUBLIC_HOST}) && PathPrefix(/api)` con `API_PREFIX: api`, e ogni
  `allowed_origins` elenca apex + `www` dello **stesso** dominio del prodotto.
  italco-be sta su `ares-logistics.it/api`, il frontend su `ares-logistics.it`:
  **stessa origin**, quindi `SameSite=Lax`/`Strict` funziona e non serve nessuna
  difesa CSRF aggiuntiva.
- Le ~20 origin extra di generic-be sono le vetrine, che **non hanno sessioni**:
  copiano lo stesso `http.js` con un `getToken` che è boilerplate morto, non
  usano `AuthManager`, e chiamano endpoint pubblici (il mailer non ha alcun
  decoratore). È un tema di CORS, non di cookie. La guardia
  `auth_header == 'null'` in generic-lib è il fossile di questo pattern.

Se un domani nasce un login utente su un dominio cliente, quella non è una
feature in più: è il cambio della premessa. In quel caso si usa il trasporto
bearer, **non** `SameSite=None`, perché i cookie di terze parti sono già
bloccati su Safari e in dismissione altrove.

### Cosa è entrato in questo incremento

**generic-lib**
- Trasporto pluggabile cookie|bearer (§2) e `revoke_user_sessions`.
- Reuse detection con lapidi; il cleanup al login tocca solo le scadute.
- `allow_query_token` diventa additivo rispetto all'header, e il prefisso
  `Bearer ` è tollerato ovunque arrivi il token.
- Un access token firmato ma senza `sub` (formato vecchio) è un **401**, non
  più un `KeyError` → 500 → report d'errore su Telegram.
- Test: da 9 a 16 su `test_auth.py`; suite completa **72 passed**.

**italco-be**
- `reset_password` revoca le sessioni aperte dell'utente (+ test).
- `EXTRA_ALLOWED_ORIGINS`: la CORS wildcard con credenziali resta solo per lo
  sviluppo locale; valorizzando la env anche l'ambiente di test (che gira con
  `IS_DEV=1`) passa a lista esplicita.
- `REFRESH_COOKIE_PATH=/api` e `REFRESH_COOKIE_SAMESITE=Strict` nel deploy.
- `LEGACY_PASSWORD_SECRET_KEY` di test era **27 byte**: lunghezza non valida per
  AES, quindi `legacy_encrypt` sollevava sempre e i test di login erano rossi
  in `.env.test` **e** in `gitlab/test.yml`. Portata a 32 byte.
- Aggiornati i test che codificavano il comportamento vecchio: header ignorato
  sui media, e `status: session` dove ora un ruolo non abilitato dà 403.
- Suite unit: **531 passed, 0 failed** (erano 14 rossi, ~11 dei quali dati per
  "preesistenti": erano tutti la stessa causa, il `Bearer ` nella query).

**italco-fe**
- `persist: { paths: [...] }` **non funzionava**: in
  pinia-plugin-persistedstate v4 l'opzione è `pick`, e `paths` viene ignorata in
  silenzio → lo store veniva persistito intero, **token compreso**. Cioè la
  modifica cardine del branch lato FE era inefficace. Corretta, più un
  `beforeHydrate` che ripulisce il token già salvato da chi usava l'app prima.

### Verifiche eseguite (17-08)

- `generic-lib`: suite completa → **72 passed**.
- `italco-be`: `pytest ./tests/unit` su Postgres reale → **531 passed**.
- **Browser reale** (Chromium), frontend e backend serviti sulla stessa origin
  con un proxy `/api`, per riprodurre la topologia di produzione:
  - login → 200, cookie `HttpOnly; SameSite=Strict`, invisibile a
    `document.cookie`, nessun `refresh_token` nel body;
  - refresh → il cookie viaggia da solo, rotazione confermata (token diversi);
  - media con header `Authorization` → **404** (autorizzato, file assente) dove
    prima era 401; idem con `?token=<jwt>` e con `?token=Bearer <jwt>`; senza
    token → 401;
  - logout → cookie cancellato, refresh successivo → 401;
  - store: piantato in `localStorage` uno stato legacy con token, dopo il reload
    lo storage contiene solo `{role, userId}` e il token in memoria è vuoto;
  - `user_session` su Postgres: sessioni attive a 30 giorni, lapidi revocate
    accorciate a 7.

### ⚠️ Confermato nel browser: il frontend condiviso manca davvero

Il login **dalla UI** non funziona. Con il `generic-module` oggi pubblicato,
`AuthManager` pretende ancora `secretKey`/`iv` (che il branch ha giustamente
smesso di passare) e cifra la password con una chiave `undefined`: il backend
risponde "Credenziali errate". Le chiamate diritte agli endpoint funzionano
tutte, quindi il backend è a posto: è la libreria FE a non esistere ancora.

Da fare in `generic-fe`, prima di qualunque deploy:
1. rimuovere `encrypt.js` e i prop `secretKey`/`iv` da `AuthManager`/`UserLogin`
   (attenzione: `fastsite-fe` importa ancora `encryptPassword` in 4 file);
2. `refreshEndpoint` + refresh-on-401 con lock anti-concorrenza;
3. `credentials: 'include'` **sempre**, non solo in `logout.js`: su same-origin
   non serve, ma senza di esso il branch si romperebbe in silenzio il giorno in
   cui frontend e backend finissero su origin diverse.

### ⚠️ `delivery-app` va aggiornata prima del deploy

`auth_service.dart` legge `response['token']`, che ora si chiama `access_token`:
al deploy l'app non fa più login. Inoltre dipende dal `new_token` in ogni
risposta, che non esiste più. Il backend ora offre il canale bearer
(`X-Auth-Transport: bearer` → `refresh_token` nel body), quindi il lavoro lato
app è: leggere `access_token`, salvare il `refresh_token` in secure storage,
implementare il refresh. Da notare che la chiave AES delle password è hardcoded
nel sorgente Flutter (`12345678901234567890123456789012`, la chiave
placeholder): è pubblica, e questo alza la priorità della migrazione a scrypt.
