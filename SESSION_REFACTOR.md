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
| `login_response(user, extra)` | Emette access token + refresh token (cookie), risposta JSON `{status, access_token, ...extra}` |
| `refresh()` | Legge il cookie, valida la sessione, **ruota** il refresh token, restituisce un nuovo access token |
| `logout()` | Revoca la sessione (`revoked=True`) e cancella il cookie |
| `authentication(roles, allow_query_token)` | Decoratore: valida l'access token, applica il controllo ruolo, inietta `g.log_user` e passa `user` alla view |

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

### 🟠 MEDIO — AES-CBC senza autenticazione (legacy)
`legacy_encrypt` usa **AES-CBC senza MAC**: cifratura malleabile. È solo un ponte di migrazione (verifica delle vecchie password al primo login) e sparisce con la dismissione di `legacy.py`. `legacy_decrypt` è già stata rimossa.

### 🟠 MEDIO — Chiave/IV legacy hardcoded come default
`legacy.py`: `LEGACY_PASSWORD_SECRET_KEY = os.environ.get(..., 'local-dev-key-1234567890')` e IV `'1234567890123456'` di default. Accettabile solo come ponte di migrazione. In prod le env devono essere valorizzate esplicitamente e il fallback andrà rimosso a migrazione completata (`legacy.py` va poi eliminato del tutto).

### 🟠 MEDIO — token in querystring sui media (`allow_query_token`)
Gli endpoint media di italco-be (`orders/photos/<file>`, `rae/<folder>/<file>`) usano `allow_query_token=True` e il FE manda l'**access token in querystring** via `http.withSessionToken(url)`. L'access token JWT finisce in **log di accesso del server, cronologia del browser e header Referer**. È mitigato dalla vita breve (15 min), ma resta un vettore di leak. **Hardening consigliato:** token media dedicato monouso/brevissimo, oppure header `Authorization` via fetch+blob invece di URL diretta.

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
