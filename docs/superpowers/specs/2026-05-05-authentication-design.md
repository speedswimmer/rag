# Authentication Design Spec

## Übersicht

Rollenbasierte Authentifizierung für das RAG-System mit Flask-Login. Gastzugang bleibt für Chat erhalten, geschützte Bereiche (Dokumente, Admin) erfordern Login.

## Rollen

Drei hierarchische Rollen: `leser` < `user` < `admin`.

- **Leser:** Chat + Dokumentenliste ansehen
- **User:** zusätzlich Dokumente hochladen und löschen
- **Admin:** zusätzlich Admin-Dashboard, Backup, Rebuild, Settings, System-Prompt, Info-Seite

## Datenmodell

Neue `User`-Tabelle in `app/models.py`:

| Feld | Typ | Beschreibung |
|---|---|---|
| id | Integer, PK | Auto-Increment |
| username | String(80), unique | Login-Name |
| password_hash | String(256) | PBKDF2 via werkzeug.security |
| role | String(10) | "leser", "user", "admin" |
| is_active | Boolean, default True | Zum Deaktivieren ohne Löschen |
| created_at | DateTime | Erstellungszeitpunkt |

Keine Fremdschlüssel zu bestehenden Modellen (Session, Conversation, Message). Die anonyme Session-Logik bleibt unverändert — sauberer Schnitt.

## Zugriffsmatrix

| Route | Gast | Leser | User | Admin |
|---|---|---|---|---|
| GET / (Chat) | ✅ | ✅ | ✅ | ✅ |
| POST /ask | ✅ | ✅ | ✅ | ✅ |
| GET /conversations | ✅ | ✅ | ✅ | ✅ |
| GET /documents | ❌ | ✅ | ✅ | ✅ |
| POST /upload | ❌ | ❌ | ✅ | ✅ |
| DELETE /documents/<name> | ❌ | ❌ | ✅ | ✅ |
| GET /admin | ❌ | ❌ | ❌ | ✅ |
| POST /admin/* | ❌ | ❌ | ❌ | ✅ |
| GET /info | ❌ | ❌ | ❌ | ✅ |
| GET /login | ✅ | — | — | — |
| POST /login | ✅ | — | — | — |
| POST /logout | — | ✅ | ✅ | ✅ |

## Decorators

- `@login_required` — Flask-Login built-in, leitet auf `/login?next=...` um
- `@role_required(min_role)` — Custom Decorator, prüft Rollen-Hierarchie

Rollen-Hierarchie-Mapping: `{"leser": 0, "user": 1, "admin": 2}`. Ein Admin (2) erfüllt automatisch `@role_required("user")` (1).

## Login-Flow

1. Gast ruft geschützte Route auf (z.B. `/documents`)
2. Redirect auf `/login?next=/documents`
3. User gibt Username + Passwort ein
4. Validierung gegen User-Tabelle (`check_password_hash`)
5. Erfolg: `login_user(user, remember=True)` → Redirect auf `next` oder `/`
6. Fehler: Login-Seite mit Meldung "Benutzername oder Passwort falsch"

Remember-Cookie: 30 Tage, immer aktiv (kein Checkbox).

## Logout

- `POST /logout` (CSRF-geschützt)
- `logout_user()` → Redirect auf `/`
- Anonyme Session-ID bleibt erhalten → Gast kann weiter chatten

## Session-Trennung

- Gäste: anonyme UUID via `rag_session_id` Cookie (bestehend)
- Eingeloggte User: Flask-Login Session + eigene anonyme Session-ID
- Conversations bleiben an Session-ID gebunden, nicht an User

## Login-Seite (`/login`)

Eigene Template-Seite `login.html`:
- Zentrierte Card im Dark Theme
- Felder: Benutzername, Passwort
- Fehlermeldung als rote Box (nur bei fehlgeschlagenem Login)
- "Als Gast zum Chat →" Link unterhalb der Card
- CSRF-Token via Flask-WTF

## Navbar-Anpassung

Rollenabhängige Darstellung in `base.html`:

**Gast:**
```
[App-Name]    Chat                              [Anmelden]
```

**Leser:**
```
[App-Name]    Chat    Dokumente                 username · Abmelden
```

**User:**
```
[App-Name]    Chat    Dokumente                 username · Abmelden
```

**Admin:**
```
[App-Name]    Chat    Dokumente    Admin    Info        username · Abmelden
```

Mobile: Burger-Menü mit gleichen rollenabhängigen Links.

## CLI-Benutzerverwaltung

Flask CLI-Commands registriert in `app/__init__.py`:

```bash
flask create-user <username> --role <role>    # Interaktive Passworteingabe
flask change-password <username>              # Neues Passwort setzen
flask list-users                              # Alle Benutzer auflisten
flask disable-user <username>                 # Deaktivieren (kein Login)
```

Passwort-Eingabe via `click.prompt(hide_input=True, confirmation_prompt=True)`.

Beim App-Start: Warnung im Log wenn kein Admin-Benutzer existiert.

## Technische Umsetzung

- **Flask-Login** für Session-Management (`LoginManager`, `UserMixin`, `login_user`, `logout_user`, `current_user`)
- **werkzeug.security** für Passwort-Hashing (`generate_password_hash`, `check_password_hash`)
- `flask-login` als neue Dependency in `requirements.txt`
- Flask-Login `user_loader` Callback in `app/__init__.py`
- `LOGIN_DISABLED` Config für Tests (optional)

## Sicherheit

- Generische Fehlermeldung bei Login-Fehlern (kein Hinweis ob Username oder Passwort falsch)
- CSRF auf Login-Formular
- Passwort-Hashing mit PBKDF2 + Salt
- `is_active` Flag zum Sperren ohne Datenverlust
- Kein Rate-Limiting in Phase 1

## Nicht im Scope

- Passwort-Vergessen / E-Mail-Reset
- Selbst-Registrierung
- Benutzerverwaltung im Admin-Dashboard (nur CLI)
- Migration bestehender anonymer Sessions zu User-Konten
- Rate-Limiting bei Login-Versuchen
- Zwei-Faktor-Authentifizierung
