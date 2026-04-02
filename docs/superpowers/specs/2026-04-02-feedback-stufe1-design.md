# Feedback Stufe 1 — Design Spec

**Datum:** 2026-04-02
**Ziel:** Nutzer können Antworten bewerten (Daumen hoch/runter), schlechte Antworten erneut generieren lassen, und der Admin sieht eine Feedback-Übersicht.

---

## 1. Datenmodell

Neue Tabelle `feedback`:

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| id | Integer, PK, autoincrement | |
| message_id | Integer, FK → messages.id, CASCADE DELETE, UNIQUE | 1:1-Beziehung |
| rating | String(4), NOT NULL | "up" oder "down" |
| comment | Text, nullable | Optionaler Freitext bei negativer Bewertung |
| created_at | DateTime, NOT NULL | Zeitstempel |

- CASCADE DELETE: Feedback wird automatisch gelöscht wenn die zugehörige Message gelöscht wird.
- UNIQUE auf message_id: max. ein Feedback pro Nachricht (Upsert-Logik im Backend).

## 2. Frontend UI

Feedback-Elemente erscheinen **nur bei Assistenten-Nachrichten**, dezent unterhalb der Antwort-Bubble.

### Thumbs up/down
- Zwei kleine SVG-Icons (~16px), hellgrau (`#666`), rechts unter der Bubble
- Hover: leicht heller
- Aktiver Zustand: ausgefüllt in Grün (up) bzw. Rot (down)
- Klick auf 👎: kleines Textfeld klappt inline darunter auf (Placeholder: "Was war schlecht?", max 500 Zeichen), mit "Senden"-Link
- Klick auf 👍: sofort gespeichert, kein Dialog

### Retry-Button
- Kleines Reload-Icon (↻), gleiche Größe/Farbe wie Thumbs, in derselben Zeile
- Klick: löscht aktuelle Assistenten-Nachricht serverseitig (inkl. Feedback), sendet Frage erneut, streamt neue Antwort an dieselbe Stelle

### Timing
- Icons erscheinen erst **nach Abschluss des Streamings**
- Während Retry: Icons ausgeblendet, Lade-Indikator an Stelle der alten Antwort

### Layout
```
┌─────────────────────────────────┐
│  Assistenten-Antwort ...        │
└─────────────────────────────────┘
              👍  👎  ↻    ← hellgrau, klein, rechtsbündig
```

## 3. Backend API

Alle Endpoints unter CSRF-Schutz.

### POST /feedback
- Body: `{ "message_id": 123, "rating": "up"|"down", "comment": "..." }`
- Prüft: Message existiert und gehört zur Session des Nutzers
- Upsert: existiert Feedback für message_id → überschreiben
- Response: `{ "ok": true }`

### POST /retry
- Body: `{ "message_id": 123 }`
- Prüft: Message ist Assistenten-Nachricht und gehört zur Session
- Löscht die Assistenten-Nachricht (CASCADE löscht Feedback)
- Holt letzte User-Nachricht davor aus derselben Konversation
- Streamt neue Antwort via SSE (gleiche Logik wie /ask, ohne neue User-Message)
- Response: SSE-Stream

### GET /admin/feedback
- Response JSON: `{ "stats": { "total", "up", "down" }, "items": [...] }`
- Items: `{ "date", "question", "answer_preview", "rating", "comment" }`
- Sortiert nach Datum absteigend
- Optional: `?filter=down` für nur negative

### Routing
- `/feedback` und `/retry` in `app/routes/chat.py`
- `/admin/feedback` in `app/routes/admin.py`

## 4. Admin-Übersicht

Neuer Abschnitt "Feedback" auf `/admin`, unterhalb der bestehenden Karten.

### Statistik-Zeile
- Drei kompakte Werte: Gesamt | 👍 | 👎
- Gleicher Karten-Stil wie bestehende Info-Karten

### Feedback-Tabelle
| Datum | Frage | Antwort | Bewertung | Kommentar |
|-------|-------|---------|-----------|-----------|
| 02.04.2026 14:23 | Wann wurde... | Der Verein wurde... | 👎 | Jahreszahl falsch |

- Antwort ~80 Zeichen, Frage ~60 Zeichen gekürzt
- Filter-Dropdown: "Alle" / "Nur negativ" (JS, kein Neuladen)
- Sortierung: neueste zuerst
- Leerzustand: "Noch kein Feedback vorhanden."
