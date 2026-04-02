# Feedback Stufe 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add thumbs up/down feedback, retry button, and admin feedback overview to the RAG chat system.

**Architecture:** New Feedback model with 1:1 relationship to Message. Two new endpoints in chat.py (POST /feedback, POST /retry). Admin feedback overview via GET /admin/feedback + new HTML section. Frontend: subtle SVG icons below assistant bubbles with inline comment form.

**Tech Stack:** Flask, SQLAlchemy, JavaScript (vanilla), CSS

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `app/models.py` | Modify | Add Feedback model |
| `app/routes/chat.py` | Modify | Add POST /feedback and POST /retry endpoints |
| `app/routes/admin.py` | Modify | Add GET /admin/feedback endpoint, pass feedback stats to template |
| `app/static/chat.js` | Modify | Add feedback icons, comment form, retry logic |
| `app/static/style.css` | Modify | Add feedback UI styles |
| `app/templates/admin.html` | Modify | Add feedback section (stats + table + filter) |
| `app/routes/conversations.py` | Modify | Include feedback data in message responses |

---

### Task 1: Feedback Model

**Files:**
- Modify: `app/models.py`

- [ ] **Step 1: Add Feedback model to models.py**

Add after the Message class:

```python
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

    message = db.relationship("Message", backref=db.backref("feedback", uselist=False, cascade="all, delete-orphan"))
```

- [ ] **Step 2: Verify table gets created**

Run the app briefly or check that `db.create_all()` in `app/__init__.py` picks up the new model.

- [ ] **Step 3: Commit**

```bash
git add app/models.py
git commit -m "feat: add Feedback model (1:1 with Message, CASCADE delete)"
```

---

### Task 2: Feedback and Retry Endpoints

**Files:**
- Modify: `app/routes/chat.py`

- [ ] **Step 1: Add POST /feedback endpoint**

Add imports at top of chat.py:
```python
from app.models import Conversation, Feedback, Message
```

Add endpoint:
```python
@chat_bp.post("/feedback")
def submit_feedback():
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id")
    rating = data.get("rating", "")
    comment = (data.get("comment") or "").strip()

    if rating not in ("up", "down"):
        return jsonify({"error": "Ungültige Bewertung"}), 400
    if not message_id:
        return jsonify({"error": "Keine Nachricht angegeben"}), 400
    if comment and len(comment) > 500:
        return jsonify({"error": "Kommentar zu lang (max. 500 Zeichen)"}), 400

    msg = db.session.get(Message, message_id)
    if not msg or msg.role != "assistant":
        return jsonify({"error": "Nachricht nicht gefunden"}), 404

    conv = db.session.get(Conversation, msg.conversation_id)
    if not conv or conv.session_id != g.session_id:
        return jsonify({"error": "Nachricht nicht gefunden"}), 404

    # Upsert
    fb = Feedback.query.filter_by(message_id=message_id).first()
    if fb:
        fb.rating = rating
        fb.comment = comment if rating == "down" else None
    else:
        fb = Feedback(message_id=message_id, rating=rating, comment=comment if rating == "down" else None)
        db.session.add(fb)

    db.session.commit()
    return jsonify({"ok": True})
```

- [ ] **Step 2: Add POST /retry endpoint**

```python
@chat_bp.post("/retry")
def retry():
    data = request.get_json(silent=True) or {}
    message_id = data.get("message_id")

    if not message_id:
        return jsonify({"error": "Keine Nachricht angegeben"}), 400

    msg = db.session.get(Message, message_id)
    if not msg or msg.role != "assistant":
        return jsonify({"error": "Nachricht nicht gefunden"}), 404

    conv = db.session.get(Conversation, msg.conversation_id)
    if not conv or conv.session_id != g.session_id:
        return jsonify({"error": "Nachricht nicht gefunden"}), 404

    conversation_id = msg.conversation_id

    # Find the user message that preceded this assistant message
    user_msg = (
        Message.query
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "user",
            Message.created_at < msg.created_at,
        )
        .order_by(Message.created_at.desc())
        .first()
    )

    if not user_msg:
        return jsonify({"error": "Keine zugehörige Frage gefunden"}), 404

    question = user_msg.content

    # Delete the old assistant message (CASCADE deletes feedback)
    db.session.delete(msg)
    db.session.commit()

    # Load history (excluding the current question)
    cfg = current_app.config.get("RAG_CONFIG")
    context_limit = cfg.context_messages if cfg else 5
    history = _load_history(conversation_id, context_limit)

    def generate():
        full_answer = ""
        sources_data = None

        for event in get_rag_engine().ask_stream(question, history=history):
            if event["type"] == "token":
                full_answer += event["data"]
            elif event["type"] == "sources":
                sources_data = event["data"]
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        if full_answer:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_answer,
                sources=json.dumps(sources_data, ensure_ascii=False) if sources_data else None,
            )
            db.session.add(assistant_msg)

            from datetime import datetime, timezone
            conv_obj = db.session.get(Conversation, conversation_id)
            if conv_obj:
                conv_obj.updated_at = datetime.now(timezone.utc)

            db.session.commit()

            # Send the new message ID so frontend can attach feedback
            yield f"data: {json.dumps({'type': 'message_id', 'data': assistant_msg.id}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/chat.py
git commit -m "feat: add POST /feedback and POST /retry endpoints"
```

---

### Task 3: Return message_id in chat responses

**Files:**
- Modify: `app/routes/chat.py` (ask endpoint — add message_id event after done)
- Modify: `app/routes/conversations.py` (include feedback in message list)

- [ ] **Step 1: Add message_id event to /ask SSE stream**

In the `ask()` endpoint's `generate()` function, after the assistant message is committed, add:

```python
            yield f"data: {json.dumps({'type': 'message_id', 'data': assistant_msg.id}, ensure_ascii=False)}\n\n"
```

(Add this right before the final `yield` of the done event, after `db.session.commit()`.)

- [ ] **Step 2: Include feedback in GET /conversations/<id>/messages**

In `conversations.py`, update the message serialization:

```python
return jsonify([
    {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "sources": json.loads(m.sources) if m.sources else None,
        "created_at": m.created_at.isoformat(),
        "feedback": {"rating": m.feedback.rating, "comment": m.feedback.comment} if m.feedback else None,
    }
    for m in msgs
])
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/chat.py app/routes/conversations.py
git commit -m "feat: return message_id in SSE stream, include feedback in message list"
```

---

### Task 4: Frontend Feedback UI

**Files:**
- Modify: `app/static/chat.js`
- Modify: `app/static/style.css`

- [ ] **Step 1: Add feedback CSS to style.css**

```css
/* Feedback icons */
.feedback-row {
  display: flex;
  justify-content: flex-end;
  gap: .5rem;
  padding: .25rem .3rem 0;
  opacity: 0;
  transition: opacity .2s ease;
}

.message-assistant:hover .feedback-row,
.feedback-row.has-rating { opacity: 1; }

.feedback-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: .2rem;
  border-radius: 4px;
  color: var(--text-dim);
  transition: color var(--transition), background var(--transition);
  display: flex;
  align-items: center;
}

.feedback-btn:hover { color: var(--text-muted); background: var(--bg-input); }
.feedback-btn.active-up { color: var(--success); }
.feedback-btn.active-down { color: var(--error); }
.feedback-btn svg { width: 15px; height: 15px; }

/* Comment form */
.feedback-comment {
  display: flex;
  gap: .5rem;
  align-items: center;
  margin-top: .35rem;
  padding: 0 .3rem;
}

.feedback-comment input {
  flex: 1;
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 6px;
  padding: .3rem .6rem;
  font-size: .8rem;
  font-family: inherit;
  outline: none;
}

.feedback-comment input:focus { border-color: var(--accent); }

.feedback-comment-send {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: .8rem;
  font-weight: 500;
  padding: .2rem .4rem;
  border-radius: 4px;
  transition: background var(--transition);
}

.feedback-comment-send:hover { background: var(--accent-subtle); }
```

- [ ] **Step 2: Add feedback functions to chat.js**

Add SVG icon constants:

```javascript
const ICON_THUMB_UP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z"/></svg>';
const ICON_THUMB_DOWN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z"/></svg>';
const ICON_RETRY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>';
```

Add feedback row builder:

```javascript
function buildFeedbackRow(messageId, existingFeedback) {
  const row = document.createElement('div');
  row.className = 'feedback-row' + (existingFeedback ? ' has-rating' : '');
  row.dataset.messageId = messageId;

  const upBtn = document.createElement('button');
  upBtn.type = 'button';
  upBtn.className = 'feedback-btn' + (existingFeedback?.rating === 'up' ? ' active-up' : '');
  upBtn.innerHTML = ICON_THUMB_UP;
  upBtn.title = 'Gut';

  const downBtn = document.createElement('button');
  downBtn.type = 'button';
  downBtn.className = 'feedback-btn' + (existingFeedback?.rating === 'down' ? ' active-down' : '');
  downBtn.innerHTML = ICON_THUMB_DOWN;
  downBtn.title = 'Schlecht';

  const retryBtn = document.createElement('button');
  retryBtn.type = 'button';
  retryBtn.className = 'feedback-btn';
  retryBtn.innerHTML = ICON_RETRY;
  retryBtn.title = 'Nochmal versuchen';

  upBtn.addEventListener('click', () => submitFeedback(row, messageId, 'up'));
  downBtn.addEventListener('click', () => submitFeedback(row, messageId, 'down'));
  retryBtn.addEventListener('click', () => retryMessage(messageId, row));

  row.appendChild(upBtn);
  row.appendChild(downBtn);
  row.appendChild(retryBtn);
  return row;
}
```

Add submit feedback:

```javascript
async function submitFeedback(row, messageId, rating) {
  // If clicking down, show comment form
  if (rating === 'down') {
    let commentForm = row.parentElement.querySelector('.feedback-comment');
    if (!commentForm) {
      commentForm = document.createElement('div');
      commentForm.className = 'feedback-comment';
      const input = document.createElement('input');
      input.type = 'text';
      input.placeholder = 'Was war schlecht?';
      input.maxLength = 500;
      const sendBtn = document.createElement('button');
      sendBtn.type = 'button';
      sendBtn.className = 'feedback-comment-send';
      sendBtn.textContent = 'Senden';
      sendBtn.addEventListener('click', async () => {
        await doSubmitFeedback(row, messageId, 'down', input.value.trim());
        commentForm.remove();
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); sendBtn.click(); }
      });
      commentForm.appendChild(input);
      commentForm.appendChild(sendBtn);
      row.parentElement.appendChild(commentForm);
      input.focus();
      return;
    }
  }
  await doSubmitFeedback(row, messageId, rating, '');
}

async function doSubmitFeedback(row, messageId, rating, comment) {
  try {
    await apiPost('/feedback', { message_id: messageId, rating, comment });
    // Update button states
    row.querySelector('.feedback-btn:nth-child(1)').className = 'feedback-btn' + (rating === 'up' ? ' active-up' : '');
    row.querySelector('.feedback-btn:nth-child(2)').className = 'feedback-btn' + (rating === 'down' ? ' active-down' : '');
    row.classList.add('has-rating');
  } catch (err) {
    console.error('Feedback failed:', err);
  }
}
```

Add retry logic:

```javascript
async function retryMessage(messageId, feedbackRow) {
  const wrapper = feedbackRow.closest('.message-assistant');
  if (!wrapper) return;

  // Remove feedback row and any comment form
  const commentForm = wrapper.querySelector('.feedback-comment');
  if (commentForm) commentForm.remove();
  feedbackRow.remove();

  // Replace bubble content with loading indicator
  const bubble = wrapper.querySelector('.message-bubble');
  const sources = wrapper.querySelector('.sources');
  if (sources) sources.remove();
  bubble.innerHTML = '<div class="spinner"></div> Generiere neue Antwort …';
  bubble.style.display = 'flex';
  bubble.style.alignItems = 'center';
  bubble.style.gap = '.65rem';
  bubble.style.color = 'var(--text-muted)';
  bubble.style.fontSize = '.875rem';

  let rawText = '';
  let newSources = null;
  let newMessageId = null;

  try {
    const resp = await fetch('/retry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
      body: JSON.stringify({ message_id: messageId }),
    });

    if (!resp.ok) {
      bubble.textContent = 'Fehler beim erneuten Generieren.';
      bubble.style = '';
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let firstToken = true;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let event;
        try { event = JSON.parse(line.slice(6)); } catch { continue; }

        if (event.type === 'token') {
          if (firstToken) {
            bubble.style = '';
            bubble.textContent = '';
            firstToken = false;
          }
          rawText += event.data;
          bubble.textContent = rawText;
          scrollToBottom();
        } else if (event.type === 'sources') {
          newSources = event.data;
        } else if (event.type === 'message_id') {
          newMessageId = event.data;
        } else if (event.type === 'done') {
          if (typeof marked !== 'undefined') {
            bubble.innerHTML = DOMPurify.sanitize(marked.parse(rawText));
          }
          if (newSources && newSources.length > 0) {
            wrapper.appendChild(buildSources(newSources));
          }
          if (newMessageId) {
            wrapper.appendChild(buildFeedbackRow(newMessageId, null));
          }
          scrollToBottom();
        }
      }
    }
  } catch (err) {
    bubble.textContent = 'Verbindungsfehler beim Retry.';
    bubble.style = '';
  }
}
```

- [ ] **Step 3: Integrate feedback into existing message rendering**

Modify `appendMessage()` to accept messageId and feedback, and add feedback row for assistant messages:

```javascript
function appendMessage(role, content, sources, messageId, feedback) {
  // ... existing code ...

  // After building the wrapper, for assistant messages with an ID:
  if (role === 'assistant' && messageId) {
    wrapper.appendChild(buildFeedbackRow(messageId, feedback));
  }

  // ... rest of existing code ...
}
```

Update `openConversation()` to pass messageId and feedback:

```javascript
msgs.forEach(m => appendMessage(m.role, m.content, m.sources, m.id, m.feedback));
```

Update the SSE streaming in the form submit handler to capture `message_id` event and add feedback row on `done`:

In the event processing loop, add:
```javascript
} else if (event.type === 'message_id') {
  currentMessageId = event.data;
```

And in the `done` handler, add:
```javascript
if (currentMessageId && assistantWrapper) {
  assistantWrapper.appendChild(buildFeedbackRow(currentMessageId, null));
}
```

- [ ] **Step 4: Commit**

```bash
git add app/static/chat.js app/static/style.css
git commit -m "feat: add feedback UI (thumbs up/down, comment, retry)"
```

---

### Task 5: Admin Feedback Overview

**Files:**
- Modify: `app/routes/admin.py`
- Modify: `app/templates/admin.html`

- [ ] **Step 1: Add GET /admin/feedback endpoint to admin.py**

```python
from app.models import Feedback, Message

@admin_bp.get("/admin/feedback")
def feedback_data():
    query = (
        db.session.query(Feedback, Message)
        .join(Message, Feedback.message_id == Message.id)
        .order_by(Feedback.created_at.desc())
    )

    filter_param = request.args.get("filter")
    if filter_param == "down":
        query = query.filter(Feedback.rating == "down")

    results = query.all()

    total = Feedback.query.count()
    up_count = Feedback.query.filter_by(rating="up").count()
    down_count = Feedback.query.filter_by(rating="down").count()

    items = []
    for fb, msg in results:
        # Find preceding user message
        user_msg = (
            Message.query
            .filter(
                Message.conversation_id == msg.conversation_id,
                Message.role == "user",
                Message.created_at < msg.created_at,
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        items.append({
            "date": fb.created_at.strftime("%d.%m.%Y %H:%M"),
            "question": (user_msg.content[:60] + "…") if user_msg and len(user_msg.content) > 60 else (user_msg.content if user_msg else "—"),
            "answer_preview": (msg.content[:80] + "…") if len(msg.content) > 80 else msg.content,
            "rating": fb.rating,
            "comment": fb.comment,
        })

    return jsonify({"stats": {"total": total, "up": up_count, "down": down_count}, "items": items})
```

- [ ] **Step 2: Add feedback section to admin.html**

Add after the System-Prompt section and before the System info section:

```html
<!-- Feedback -->
<section class="info-section" style="margin-bottom:1.5rem">
  <h2 class="section-title">Feedback</h2>
  <div id="feedbackStats" style="display:flex;gap:1.5rem;margin-bottom:1rem;font-size:.9rem">
    <span>Gesamt: <strong id="fbTotal">—</strong></span>
    <span style="color:var(--success)">&#x1F44D; <strong id="fbUp">—</strong></span>
    <span style="color:var(--error)">&#x1F44E; <strong id="fbDown">—</strong></span>
  </div>
  <div style="margin-bottom:.75rem">
    <select id="feedbackFilter" style="background:var(--bg-input);border:1px solid var(--border-light);color:var(--text);border-radius:6px;padding:.35rem .6rem;font-size:.82rem;font-family:inherit;outline:none">
      <option value="">Alle</option>
      <option value="down">Nur negativ</option>
    </select>
  </div>
  <div class="docs-table-wrapper">
    <table class="docs-table" id="feedbackTable" style="display:none">
      <thead>
        <tr>
          <th>Datum</th>
          <th>Frage</th>
          <th>Antwort</th>
          <th>Bewertung</th>
          <th>Kommentar</th>
        </tr>
      </thead>
      <tbody id="feedbackBody"></tbody>
    </table>
  </div>
  <p class="empty-hint" id="feedbackEmpty">Noch kein Feedback vorhanden.</p>
</section>
```

- [ ] **Step 3: Add feedback JS to admin.html**

```javascript
// Feedback overview
const feedbackFilter = document.getElementById('feedbackFilter');
feedbackFilter.addEventListener('change', loadFeedback);

async function loadFeedback() {
  const filter = feedbackFilter.value;
  const url = '/admin/feedback' + (filter ? '?filter=' + filter : '');
  try {
    const resp = await fetch(url);
    const data = await resp.json();

    document.getElementById('fbTotal').textContent = data.stats.total;
    document.getElementById('fbUp').textContent = data.stats.up;
    document.getElementById('fbDown').textContent = data.stats.down;

    const tbody = document.getElementById('feedbackBody');
    const table = document.getElementById('feedbackTable');
    const empty = document.getElementById('feedbackEmpty');

    if (data.items.length === 0) {
      table.style.display = 'none';
      empty.style.display = 'block';
      return;
    }

    table.style.display = 'table';
    empty.style.display = 'none';
    tbody.innerHTML = '';

    data.items.forEach(item => {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + item.date + '</td>' +
        '<td>' + escapeHtml(item.question) + '</td>' +
        '<td>' + escapeHtml(item.answer_preview) + '</td>' +
        '<td>' + (item.rating === 'up' ? '&#x1F44D;' : '&#x1F44E;') + '</td>' +
        '<td>' + (item.comment ? escapeHtml(item.comment) : '—') + '</td>';
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Failed to load feedback:', err);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

loadFeedback();
```

- [ ] **Step 4: Commit**

```bash
git add app/routes/admin.py app/templates/admin.html
git commit -m "feat: add admin feedback overview (stats + table + filter)"
```
