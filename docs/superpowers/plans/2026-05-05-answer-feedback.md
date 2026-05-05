# Answer Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add thumbs up/down feedback buttons under every assistant message in the chat, persisted in a dedicated SQLite table.

**Architecture:** New `Feedback` model (1:1 with `Message`) stores ratings. New `POST /messages/<id>/feedback` endpoint handles submissions. Frontend renders SVG thumb icons under each assistant bubble, sends rating via API, and visually locks the chosen thumb in accent color.

**Tech Stack:** Flask, SQLAlchemy, vanilla JS, CSS

---

### Task 1: Feedback Model

**Files:**
- Modify: `app/models.py:46-59`

- [ ] **Step 1: Add Feedback model and Message relationship**

Add the `Feedback` class after the `Message` class in `app/models.py`, and add a `feedback` relationship to `Message`:

```python
class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(
        db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    role = db.Column(db.String(10), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    sources = db.Column(db.Text, nullable=True)  # JSON string
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    conversation = db.relationship("Conversation", back_populates="messages")
    feedback = db.relationship(
        "Feedback", back_populates="message", uselist=False, cascade="all, delete-orphan"
    )


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    message_id = db.Column(
        db.Integer, db.ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )
    rating = db.Column(db.String(4), nullable=False)  # 'up' or 'down'
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    message = db.relationship("Message", back_populates="feedback")
```

- [ ] **Step 2: Verify table creation**

Restart the app (or run a quick test). SQLAlchemy's `db.create_all()` in `app/__init__.py:56` will create the `feedback` table automatically. Verify with:

```bash
cd /home/jarvis/rag
venv/bin/python -c "
from app import create_app
app = create_app()
with app.app_context():
    from app.database import db
    print([t for t in db.engine.table_names() if 'feedback' in t])
"
```

Expected: `['feedback']`

- [ ] **Step 3: Commit**

```bash
git add app/models.py
git commit -m "feat: add Feedback model (1:1 with Message)"
```

---

### Task 2: Feedback API Endpoint

**Files:**
- Modify: `app/routes/chat.py:1-14`

- [ ] **Step 1: Add feedback endpoint to chat.py**

Add the import for `Feedback` and the new endpoint at the end of `app/routes/chat.py`:

```python
# At the top, update the import line:
from app.models import Conversation, Feedback, Message
```

Then add this route after the `_load_history` function:

```python
@chat_bp.post("/messages/<int:message_id>/feedback")
def submit_feedback(message_id: int):
    msg = db.session.get(Message, message_id)
    if not msg:
        return jsonify({"error": "Nachricht nicht gefunden"}), 404

    # Verify message belongs to current session
    conv = db.session.get(Conversation, msg.conversation_id)
    if not conv or conv.session_id != g.session_id:
        return jsonify({"error": "Nachricht nicht gefunden"}), 404

    if msg.role != "assistant":
        return jsonify({"error": "Feedback nur fuer Assistenten-Antworten moeglich"}), 400

    data = request.get_json(silent=True) or {}
    rating = data.get("rating")
    if rating not in ("up", "down"):
        return jsonify({"error": "Ungueltiges Rating (up/down erwartet)"}), 400

    if msg.feedback:
        return jsonify({"error": "Bereits bewertet"}), 409

    feedback = Feedback(message_id=message_id, rating=rating)
    db.session.add(feedback)
    db.session.commit()

    return jsonify({"ok": True})
```

- [ ] **Step 2: Test the endpoint manually**

Start the app and test with curl (use an existing assistant message ID):

```bash
curl -X POST http://localhost:8080/messages/1/feedback \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <token>" \
  -H "Cookie: rag_session_id=<session>" \
  -d '{"rating": "up"}'
```

Expected: `{"ok": true}` with status 200.

Test duplicate: same request again should return `{"error": "Bereits bewertet"}` with status 409.

- [ ] **Step 3: Commit**

```bash
git add app/routes/chat.py
git commit -m "feat: add POST /messages/<id>/feedback endpoint"
```

---

### Task 3: Extend Messages API with Feedback Field

**Files:**
- Modify: `app/routes/conversations.py:61-83`

- [ ] **Step 1: Add feedback to message serialization**

In `app/routes/conversations.py`, update the `get_messages` function to include the feedback field. The eager-loading avoids N+1 queries:

```python
from sqlalchemy.orm import joinedload
```

Add this import at the top, then update the query and serialization:

```python
@conversations_bp.get("/conversations/<conversation_id>/messages")
def get_messages(conversation_id):
    """Return all messages in a conversation."""
    conv = db.session.get(Conversation, conversation_id)
    if not conv or conv.session_id != g.session_id:
        return jsonify({"error": "Nicht gefunden"}), 404

    msgs = (
        Message.query
        .filter_by(conversation_id=conversation_id)
        .options(joinedload(Message.feedback))
        .order_by(Message.created_at)
        .all()
    )
    return jsonify([
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": json.loads(m.sources) if m.sources else None,
            "feedback": m.feedback.rating if m.feedback else None,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ])
```

- [ ] **Step 2: Verify by loading a conversation with rated messages**

Open a conversation that has a feedback entry. The messages JSON should now include `"feedback": "up"` or `"feedback": "down"` for rated messages, and `"feedback": null` for unrated ones.

- [ ] **Step 3: Commit**

```bash
git add app/routes/conversations.py
git commit -m "feat: include feedback rating in messages API response"
```

---

### Task 4: Send Message ID to Frontend After Streaming

**Files:**
- Modify: `app/routes/chat.py:56-94` (inside `generate()`)

- [ ] **Step 1: Include message ID in a new SSE event**

The frontend needs the assistant message's database ID to send feedback later. Modify the `generate()` function inside the `ask()` route. After saving the assistant message, yield a `message_id` event:

Replace the entire `generate()` function with:

```python
    def generate():
        full_answer = ""
        sources_data = None
        saved_message_id = None

        for event in get_rag_engine().ask_stream(question, history=history):
            if event["type"] == "token":
                full_answer += event["data"]
            elif event["type"] == "sources":
                sources_data = event["data"]
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # Save assistant message after streaming completes
        if full_answer:
            try:
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_answer,
                    sources=json.dumps(sources_data, ensure_ascii=False) if sources_data else None,
                )
                db.session.add(assistant_msg)

                # Re-fetch conversation (original may be detached after long streaming)
                fresh_conv = db.session.get(Conversation, conversation_id)
                if fresh_conv:
                    if fresh_conv.title == "Neue Unterhaltung":
                        fresh_conv.title = question[:50]

                    from datetime import datetime, timezone
                    fresh_conv.updated_at = datetime.now(timezone.utc)

                db.session.commit()
                saved_message_id = assistant_msg.id
                logger.info("Saved assistant message (%d chars) to conversation %s", len(full_answer), conversation_id)
            except Exception:
                logger.exception("Failed to save assistant message")
                db.session.rollback()
        else:
            logger.warning("No answer generated — nothing to save")

        # Send message ID so frontend can attach feedback
        yield f"data: {json.dumps({'type': 'message_id', 'data': saved_message_id}, ensure_ascii=False)}\n\n"
```

- [ ] **Step 2: Verify streaming still works**

Open the chat, ask a question, verify the answer streams correctly. Check browser DevTools Network tab — the SSE stream should now include a `message_id` event at the end.

- [ ] **Step 3: Commit**

```bash
git add app/routes/chat.py
git commit -m "feat: send assistant message ID in SSE stream for feedback"
```

---

### Task 5: CSS for Feedback Buttons

**Files:**
- Modify: `app/static/style.css` (append before responsive section)

- [ ] **Step 1: Add feedback button styles**

Add these styles before the `/* Responsive */` comment (before line 976) in `app/static/style.css`:

```css
/* ============================================================
   Feedback buttons
   ============================================================ */
.feedback-row {
  display: flex;
  gap: 6px;
  padding: 4px 0 0 4px;
}

.feedback-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  opacity: 0.35;
  color: var(--text-muted);
  transition: opacity var(--transition), color var(--transition);
  display: flex;
  align-items: center;
}

.feedback-btn:hover {
  opacity: 0.7;
}

.feedback-btn svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.feedback-row.rated .feedback-btn {
  cursor: default;
  opacity: 0.15;
}

.feedback-row.rated .feedback-btn.selected {
  opacity: 1;
  color: var(--accent);
}
```

- [ ] **Step 2: Commit**

```bash
git add app/static/style.css
git commit -m "feat: add CSS for feedback buttons"
```

---

### Task 6: Frontend — Feedback Buttons in chat.js

**Files:**
- Modify: `app/static/chat.js`

This is the largest task. It adds the feedback button rendering and click handling to the chat UI.

- [ ] **Step 1: Add SVG constants and buildFeedbackRow function**

Add this code in the `// DOM helpers` section of `chat.js`, after the `buildSources` function (after line 281):

```javascript
// ------------------------------------------------------------------
// Feedback buttons
// ------------------------------------------------------------------

function createThumbUpSVG() {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M7 22V11l5-9 1.5.5c.8.3 1.5 1.2 1.5 2.1V8h5.5c1.4 0 2.4 1.3 2 2.6l-2.3 8A2 2 0 0 1 18.3 20H7z');
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', '1'); rect.setAttribute('y', '11');
  rect.setAttribute('width', '5'); rect.setAttribute('height', '11');
  rect.setAttribute('rx', '1');
  svg.appendChild(path);
  svg.appendChild(rect);
  return svg;
}

function createThumbDownSVG() {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M17 2v11l-5 9-1.5-.5c-.8-.3-1.5-1.2-1.5-2.1V16H3.5c-1.4 0-2.4-1.3-2-2.6l2.3-8A2 2 0 0 1 5.7 4H17z');
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', '18'); rect.setAttribute('y', '2');
  rect.setAttribute('width', '5'); rect.setAttribute('height', '11');
  rect.setAttribute('rx', '1');
  svg.appendChild(path);
  svg.appendChild(rect);
  return svg;
}

function buildFeedbackRow(messageId, existingRating) {
  const row = document.createElement('div');
  row.className = 'feedback-row' + (existingRating ? ' rated' : '');

  const upBtn = document.createElement('button');
  upBtn.className = 'feedback-btn' + (existingRating === 'up' ? ' selected' : '');
  upBtn.type = 'button';
  upBtn.title = 'Gute Antwort';
  upBtn.appendChild(createThumbUpSVG());

  const downBtn = document.createElement('button');
  downBtn.className = 'feedback-btn' + (existingRating === 'down' ? ' selected' : '');
  downBtn.type = 'button';
  downBtn.title = 'Schlechte Antwort';
  downBtn.appendChild(createThumbDownSVG());

  if (!existingRating && messageId) {
    upBtn.addEventListener('click', () => submitFeedback(messageId, 'up', row, upBtn));
    downBtn.addEventListener('click', () => submitFeedback(messageId, 'down', row, downBtn));
  }

  row.appendChild(upBtn);
  row.appendChild(downBtn);
  return row;
}

async function submitFeedback(messageId, rating, row, selectedBtn) {
  try {
    await apiPost('/messages/' + messageId + '/feedback', { rating });
    row.classList.add('rated');
    selectedBtn.classList.add('selected');
  } catch (err) {
    console.error('Feedback failed:', err);
  }
}
```

- [ ] **Step 2: Update appendMessage to show feedback for loaded messages**

Modify the `appendMessage` function signature and body. Replace the entire function:

```javascript
function appendMessage(role, content, sources, messageId, feedback) {
  const wrapper = document.createElement('div');
  wrapper.className = `message message-${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  if (role === 'assistant' && typeof marked !== 'undefined') {
    bubble.innerHTML = DOMPurify.sanitize(marked.parse(content));
  } else {
    bubble.textContent = content;
  }

  wrapper.appendChild(bubble);

  if (sources && sources.length > 0) {
    wrapper.appendChild(buildSources(sources));
  }

  if (role === 'assistant') {
    wrapper.appendChild(buildFeedbackRow(messageId, feedback));
  }

  if (role === 'user') {
    _currentExchange = document.createElement('div');
    _currentExchange.className = 'exchange';
    chatMessages.appendChild(_currentExchange);
    _currentExchange.appendChild(wrapper);
  } else if (role === 'assistant' && _currentExchange) {
    _currentExchange.appendChild(wrapper);
  } else {
    chatMessages.appendChild(wrapper);
  }

  scrollToBottom();
  return wrapper;
}
```

- [ ] **Step 3: Update openConversation to pass messageId and feedback**

In the `openConversation` function, update the `forEach` call (around line 170) to pass the new parameters:

```javascript
    msgs.forEach(m => appendMessage(m.role, m.content, m.sources, m.id, m.feedback));
```

- [ ] **Step 4: Update streaming handler to add feedback buttons on message_id event**

In the `chatForm` submit handler, handle the new `message_id` SSE event. Find the event handling section (around line 383) and add the `message_id` case. Insert it right before the `} else if (event.type === 'token') {` line:

```javascript
        if (event.type === 'sources') {
          sources = event.data;
        } else if (event.type === 'message_id') {
          if (assistantWrapper && event.data) {
            assistantWrapper.appendChild(buildFeedbackRow(event.data, null));
            scrollToBottom();
          }
        } else if (event.type === 'token') {
```

- [ ] **Step 5: Update all appendMessage call sites with extra parameters**

Find all other calls to `appendMessage` in the file and add `null, null` for `messageId` and `feedback`:

In the submit handler (user message, around line 334):
```javascript
  appendMessage('user', question, null, null, null);
```

In error handlers (find each one):
```javascript
appendMessage('assistant', 'Fehler beim Erstellen der Unterhaltung: ' + err.message, null, null, null);
appendMessage('assistant', `Fehler: ${errData?.error || resp.statusText}`, null, null, null);
appendMessage('assistant', `Fehler: ${event.data}`, null, null, null);
appendMessage('assistant', `Verbindungsfehler: ${err.message}`, null, null, null);
```

- [ ] **Step 6: Verify end-to-end**

1. Open the chat, ask a question
2. After the answer streams in, verify two thumb icons appear below the bubble (faded, ~35% opacity)
3. Click thumbs-up — it should turn accent-colored, thumbs-down fades further
4. Reload the page and open the same conversation — the feedback state should be preserved
5. Verify a second click does nothing (already rated)

- [ ] **Step 7: Commit**

```bash
git add app/static/chat.js
git commit -m "feat: add feedback buttons to chat UI"
```

---

### Task 7: Final Integration Test

- [ ] **Step 1: Full flow test**

1. Start the app fresh
2. Create a new conversation, ask a question
3. Verify feedback buttons appear after streaming completes
4. Click thumbs-down on the answer — verify accent highlight
5. Ask another question in the same conversation
6. Click thumbs-up on the second answer
7. Navigate away (e.g. to /admin), then come back
8. Open the conversation — verify both feedback states are preserved (first: down, second: up)
9. Open browser DevTools console — verify no JS errors

- [ ] **Step 2: Edge cases**

1. Open a conversation with no messages — no feedback buttons should appear
2. Verify user message bubbles have no feedback buttons
3. Check mobile layout (resize browser to <600px) — buttons should remain visible and tappable

- [ ] **Step 3: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: feedback integration fixes"
```
