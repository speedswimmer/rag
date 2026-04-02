/* Chat UI — persistent history via server API */

'use strict';

const chatMessages  = document.getElementById('chatMessages');
const chatForm      = document.getElementById('chatForm');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
const charCounter   = document.getElementById('charCounter');
const sidebarList   = document.getElementById('sidebarList');
const newChatBtn    = document.getElementById('newChatBtn');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar       = document.getElementById('sidebar');
const sidebarOverlay= document.getElementById('sidebarOverlay');
const welcomeMsg    = document.getElementById('welcomeMsg');
const MAX_LENGTH    = 2000;
const CSRF_TOKEN    = document.querySelector('meta[name="csrf-token"]').content;

let currentConversationId = null;

// Feedback SVG icons (subtle, 15px via CSS)
const ICON_THUMB_UP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z"/></svg>';
const ICON_THUMB_DOWN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z"/></svg>';
const ICON_RETRY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>';

// ------------------------------------------------------------------
// Sidebar toggle (mobile)
// ------------------------------------------------------------------

if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    sidebarOverlay.classList.toggle('open');
  });
}

if (sidebarOverlay) {
  sidebarOverlay.addEventListener('click', () => {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('open');
  });
}

// ------------------------------------------------------------------
// API helpers
// ------------------------------------------------------------------

async function apiGet(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(resp.statusText);
  return resp.json();
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || resp.statusText);
  }
  return resp;
}

async function apiDelete(url) {
  const resp = await fetch(url, {
    method: 'DELETE',
    headers: { 'X-CSRFToken': CSRF_TOKEN },
  });
  if (!resp.ok) throw new Error(resp.statusText);
}

// ------------------------------------------------------------------
// Sidebar — conversation list
// ------------------------------------------------------------------

async function loadConversations() {
  try {
    const convs = await apiGet('/conversations');
    renderSidebar(convs);
  } catch (err) {
    console.error('Failed to load conversations:', err);
  }
}

function renderSidebar(convs) {
  sidebarList.innerHTML = '';
  if (convs.length === 0) {
    sidebarList.innerHTML = '<div class="sidebar-empty">Noch keine Unterhaltungen</div>';
    return;
  }
  convs.forEach(c => {
    const item = document.createElement('div');
    item.className = 'sidebar-item' + (c.id === currentConversationId ? ' active' : '');
    item.dataset.id = c.id;

    const title = document.createElement('span');
    title.className = 'sidebar-item-title';
    title.textContent = c.title;

    const date = document.createElement('span');
    date.className = 'sidebar-item-date';
    date.textContent = relativeDate(c.updated_at);

    const del = document.createElement('button');
    del.className = 'sidebar-item-delete';
    del.type = 'button';
    del.innerHTML = '&#x1F5D1;';
    del.title = 'Löschen';
    del.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('Unterhaltung löschen?')) return;
      try {
        await apiDelete('/conversations/' + c.id);
        if (currentConversationId === c.id) {
          currentConversationId = null;
          clearChat();
        }
        loadConversations();
      } catch (err) {
        console.error('Delete failed:', err);
      }
    });

    item.appendChild(title);
    item.appendChild(date);
    item.appendChild(del);
    item.addEventListener('click', () => openConversation(c.id));
    sidebarList.appendChild(item);
  });
}

function relativeDate(isoStr) {
  const d = new Date(isoStr);
  const now = new Date();
  const diffMs = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  const diffH = Math.floor(diffMs / 3600000);
  const diffD = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'jetzt';
  if (diffMin < 60) return diffMin + ' Min.';
  if (diffH < 24) return diffH + ' Std.';
  if (diffD < 7) return diffD + (diffD === 1 ? ' Tag' : ' Tage');
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}

// ------------------------------------------------------------------
// Conversation management
// ------------------------------------------------------------------

async function openConversation(id) {
  currentConversationId = id;
  clearChat();

  // Close mobile sidebar
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('open');

  // Mark active
  document.querySelectorAll('.sidebar-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === id);
  });

  try {
    const msgs = await apiGet('/conversations/' + id + '/messages');
    if (msgs.length === 0) {
      showWelcome();
      return;
    }
    hideWelcome();
    msgs.forEach(m => appendMessage(m.role, m.content, m.sources, m.id, m.feedback));
  } catch (err) {
    console.error('Failed to load messages:', err);
  }
}

function startNewChat() {
  currentConversationId = null;
  clearChat();
  showWelcome();

  // Clear active state in sidebar
  document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));

  // Close mobile sidebar
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('open');

  questionInput.focus();
}

newChatBtn.addEventListener('click', startNewChat);

function clearChat() {
  chatMessages.innerHTML = '';
  _currentExchange = null;
}

function showWelcome() {
  if (!document.getElementById('welcomeMsg')) {
    const div = document.createElement('div');
    div.className = 'message message-system';
    div.id = 'welcomeMsg';
    div.innerHTML = '<div class="message-bubble">Wie kann ich dir helfen?</div>';
    chatMessages.appendChild(div);
  }
}

function hideWelcome() {
  const el = document.getElementById('welcomeMsg');
  if (el) el.remove();
}

// ------------------------------------------------------------------
// DOM helpers
// ------------------------------------------------------------------

let _currentExchange = null;

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

  // Feedback row for assistant messages with a known ID
  if (role === 'assistant' && messageId) {
    try {
      wrapper.appendChild(buildFeedbackRow(messageId, feedback));
    } catch (err) {
      console.error('Failed to build feedback row:', err);
    }
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

function buildSources(sources) {
  const container = document.createElement('div');
  container.className = 'sources';

  const toggle = document.createElement('button');
  toggle.className = 'sources-toggle';
  toggle.type = 'button';
  toggle.textContent = `${sources.length} Quelle${sources.length > 1 ? 'n' : ''}`;

  const list = document.createElement('div');
  list.className = 'sources-list';

  sources.forEach((s, i) => {
    const line = document.createElement('div');
    const page = s.page !== undefined && s.page !== '?' ? ` (S. ${s.page})` : '';
    line.textContent = `${i + 1}. ${s.source}${page}`;
    list.appendChild(line);
  });

  toggle.addEventListener('click', () => {
    toggle.classList.toggle('open');
    list.classList.toggle('visible');
  });

  container.appendChild(toggle);
  container.appendChild(list);
  return container;
}

function addLoadingIndicator() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message message-assistant message-loading';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  const spinner = document.createElement('div');
  spinner.className = 'spinner';
  bubble.appendChild(spinner);
  bubble.appendChild(document.createTextNode('Suche relevante Passagen …'));

  wrapper.appendChild(bubble);
  chatMessages.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ------------------------------------------------------------------
// Form submission (SSE streaming)
// ------------------------------------------------------------------

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const question = questionInput.value.trim();
  if (!question) return;

  questionInput.value = '';
  autoResize(questionInput);
  setLoading(true);
  hideWelcome();

  // Create conversation if needed
  if (!currentConversationId) {
    try {
      const resp = await apiPost('/conversations', { title: question.slice(0, 50) });
      const data = await resp.json();
      currentConversationId = data.id;
      loadConversations();
    } catch (err) {
      appendMessage('assistant', 'Fehler beim Erstellen der Unterhaltung: ' + err.message, null);
      setLoading(false);
      return;
    }
  }

  appendMessage('user', question, null);

  const loadingEl = addLoadingIndicator();

  let rawText = '';
  let sources = null;
  let assistantWrapper = null;
  let bubble = null;
  let currentMessageId = null;

  try {
    const resp = await fetch('/ask', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': CSRF_TOKEN,
      },
      body: JSON.stringify({ question, conversation_id: currentConversationId }),
    });

    if (!resp.ok) {
      loadingEl.remove();
      const errData = await resp.json().catch(() => null);
      appendMessage('assistant', `Fehler: ${errData?.error || resp.statusText}`, null);
      setLoading(false);
      questionInput.focus();
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let event;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }

        if (event.type === 'message_id') {
          currentMessageId = event.data;
          // message_id arrives after done, so add feedback row now
          if (assistantWrapper) {
            try {
              assistantWrapper.appendChild(buildFeedbackRow(currentMessageId, null));
              scrollToBottom();
            } catch (err) {
              console.error('Failed to build feedback row:', err);
            }
          }
        } else if (event.type === 'sources') {
          sources = event.data;
        } else if (event.type === 'token') {
          if (!assistantWrapper) {
            loadingEl.remove();
            assistantWrapper = document.createElement('div');
            assistantWrapper.className = 'message message-assistant';
            bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            assistantWrapper.appendChild(bubble);
            if (_currentExchange) {
              _currentExchange.appendChild(assistantWrapper);
            } else {
              chatMessages.appendChild(assistantWrapper);
            }
          }
          rawText += event.data;
          bubble.textContent = rawText;
          scrollToBottom();
        } else if (event.type === 'done') {
          if (bubble && typeof marked !== 'undefined') {
            bubble.innerHTML = DOMPurify.sanitize(marked.parse(rawText));
          }
          if (sources && sources.length > 0 && assistantWrapper) {
            assistantWrapper.appendChild(buildSources(sources));
          }
          scrollToBottom();
          // Refresh sidebar to show updated title/time
          loadConversations();
        } else if (event.type === 'error') {
          loadingEl.remove();
          appendMessage('assistant', `Fehler: ${event.data}`, null);
        }
      }
    }
  } catch (err) {
    loadingEl.remove();
    if (!assistantWrapper) {
      appendMessage('assistant', `Verbindungsfehler: ${err.message}`, null);
    }
  }

  setLoading(false);
  questionInput.focus();
});

function setLoading(loading) {
  sendBtn.disabled = loading;
  sendBtn.querySelector('.btn-text').classList.toggle('hidden', loading);
  sendBtn.querySelector('.btn-spinner').classList.toggle('hidden', !loading);
}

// ------------------------------------------------------------------
// Auto-resize textarea
// ------------------------------------------------------------------

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

questionInput.addEventListener('input', () => {
  autoResize(questionInput);
  updateCharCounter();
});

function updateCharCounter() {
  const len = questionInput.value.length;
  charCounter.textContent = `${len} / ${MAX_LENGTH}`;
  charCounter.classList.toggle('warn',  len >= MAX_LENGTH * 0.85 && len < MAX_LENGTH);
  charCounter.classList.toggle('limit', len >= MAX_LENGTH);
}

questionInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    chatForm.dispatchEvent(new Event('submit', { cancelable: true }));
  }
});

// ------------------------------------------------------------------
// Feedback
// ------------------------------------------------------------------

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

async function submitFeedback(row, messageId, rating) {
  if (rating === 'down') {
    // Show comment form if not already visible
    let commentForm = row.parentElement.querySelector('.feedback-comment');
    if (!commentForm) {
      commentForm = document.createElement('div');
      commentForm.className = 'feedback-comment';
      const input = document.createElement('input');
      input.type = 'text';
      input.placeholder = 'Was war schlecht?';
      input.maxLength = 500;
      const sendLink = document.createElement('button');
      sendLink.type = 'button';
      sendLink.className = 'feedback-comment-send';
      sendLink.textContent = 'Senden';
      sendLink.addEventListener('click', async () => {
        await doSubmitFeedback(row, messageId, 'down', input.value.trim());
        commentForm.remove();
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); sendLink.click(); }
      });
      commentForm.appendChild(input);
      commentForm.appendChild(sendLink);
      row.after(commentForm);
      input.focus();
      return;
    }
  }
  await doSubmitFeedback(row, messageId, rating, '');
}

async function doSubmitFeedback(row, messageId, rating, comment) {
  try {
    await apiPost('/feedback', { message_id: messageId, rating, comment });
    const btns = row.querySelectorAll('.feedback-btn');
    btns[0].className = 'feedback-btn' + (rating === 'up' ? ' active-up' : '');
    btns[1].className = 'feedback-btn' + (rating === 'down' ? ' active-down' : '');
    row.classList.add('has-rating');
  } catch (err) {
    console.error('Feedback failed:', err);
  }
}

async function retryMessage(messageId, feedbackRow) {
  const wrapper = feedbackRow.closest('.message-assistant');
  if (!wrapper) return;

  // Remove feedback row and comment form
  const commentForm = wrapper.querySelector('.feedback-comment');
  if (commentForm) commentForm.remove();
  feedbackRow.remove();

  // Replace content with loading indicator
  const bubble = wrapper.querySelector('.message-bubble');
  const oldSources = wrapper.querySelector('.sources');
  if (oldSources) oldSources.remove();
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
            bubble.removeAttribute('style');
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
    bubble.removeAttribute('style');
  }
}

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------

loadConversations();
