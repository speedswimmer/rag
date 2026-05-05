# Antwort-Feedback — Design-Spec

## Zusammenfassung

Einfaches Daumen-hoch/runter-Feedback für Assistenten-Antworten im Chat. Nutzer bewerten Antworten mit einem Klick, die Bewertung wird in einer eigenen Tabelle gespeichert. Erweiterbar um optionale Kommentare (Stufe B) und Feedback-Auswertung zur Systemoptimierung (Stufe 2).

## Scope — Stufe A

- Daumen hoch/runter unter jeder Assistenten-Antwort
- Visuelles Feedback nach Klick (Accent-Highlight)
- Bewertung serverseitig speichern
- Einmal klicken, nicht änderbar

### Explizit nicht in Scope

- Kommentar-Textfeld bei Daumen-runter (Stufe B)
- Feedback-Übersicht im Admin-Dashboard (späteres Feature)
- "Nochmal versuchen"-Button (separates Feature)
- Auswertung/Analyse der Feedbacks (Stufe 2)

## UI-Design

### Position

Zwei kleine Daumen-Icons (hoch/runter) **unter der Assistenten-Bubble**, linksbündig. Erscheinen bei jeder Assistenten-Nachricht — sowohl bei neuen Streaming-Antworten als auch beim Laden bestehender Konversationen.

### Verhalten

1. **Vor Klick:** Beide Icons sichtbar bei ~35% Opacity, Cursor pointer
2. **Nach Klick:** Gewählter Daumen in Accent-Farbe (`#6366f1`), anderer Daumen auf ~15% Opacity, Cursor default
3. **Bereits bewertet (Laden):** Zustand wird aus der DB geladen und direkt im bewerteten Zustand gerendert
4. **Während Streaming:** Buttons erscheinen erst nach Abschluss des Streams (`done`-Event)

### Icons

SVG-Thumbs (inline), kein Emoji — konsistenter über Plattformen und besser steuerbar in Farbe/Größe. Größe ca. 16px, Gap 6px.

## Datenmodell

### Neue Tabelle: `feedback`

| Spalte | Typ | Constraints |
|---|---|---|
| `id` | Integer | PK, autoincrement |
| `message_id` | Integer | FK → `messages.id`, **unique**, not null |
| `rating` | String(4) | not null — `"up"` oder `"down"` |
| `comment` | Text | nullable (für Stufe B) |
| `created_at` | DateTime | not null, default UTC now |

- `message_id` ist unique: maximal ein Feedback pro Nachricht
- `comment` bleibt in Stufe A immer NULL, ist aber im Schema vorbereitet
- Kaskadierendes Löschen: wenn eine Message gelöscht wird, wird auch das Feedback gelöscht

### SQLAlchemy-Model

Neues Model `Feedback` in `app/models.py` mit Relationship auf `Message`. Message erhält eine `feedback`-Relationship (uselist=False, da 1:1).

## API

### `POST /messages/<message_id>/feedback`

Erstellt ein Feedback für die angegebene Nachricht.

**Request:**
```json
{ "rating": "up" }
```

**Validierung:**
- `message_id` muss existieren und zur aktuellen Session gehören
- `rating` muss `"up"` oder `"down"` sein
- Nachricht muss Role `"assistant"` haben
- Falls bereits Feedback existiert: HTTP 409 Conflict

**Response (Erfolg):**
```json
{ "ok": true }
```

**Response (Fehler):**
- 400: rating ungültig
- 404: Nachricht nicht gefunden oder nicht autorisiert
- 409: bereits bewertet

**CSRF:** Header `X-CSRFToken` erforderlich (wie alle POST-Endpoints).

### `GET /conversations/<id>/messages` (bestehend, erweitern)

Gibt pro Message zusätzlich `feedback` zurück:
```json
{
  "id": 42,
  "role": "assistant",
  "content": "...",
  "sources": [...],
  "feedback": "up"
}
```

`feedback` ist `null` wenn keine Bewertung vorliegt.

## Betroffene Dateien

| Datei | Änderung |
|---|---|
| `app/models.py` | Neues `Feedback`-Model, Relationship auf Message |
| `app/routes/chat.py` | Neuer Endpoint `POST /messages/<id>/feedback` |
| `app/routes/conversations.py` | Messages-Endpoint um `feedback`-Feld erweitern |
| `app/static/chat.js` | Feedback-Buttons rendern, Klick-Handler, API-Aufruf |
| `app/static/style.css` | Styles für Feedback-Buttons (normal + bewertet) |

## Sequenzdiagramm

```
Nutzer klickt 👍
  → chat.js: POST /messages/42/feedback { rating: "up" }
  → Server: Validierung (Session, Role, noch nicht bewertet)
  → Server: INSERT INTO feedback (message_id=42, rating="up")
  → Server: { "ok": true }
  → chat.js: Daumen-hoch in Accent, Daumen-runter ausgegraut
```

## Spätere Erweiterungen (nicht in Scope)

- **Stufe B:** Kommentar-Textfeld bei Daumen-runter, gespeichert in `feedback.comment`
- **Admin-Übersicht:** Tabelle aller Feedbacks mit Filter (nur negativ), Nachricht + Quellen einsehbar
- **Stufe 2:** Prompt-Tuning per Negativbeispiele, Retrieval-Gewichtung, Lücken-Erkennung
