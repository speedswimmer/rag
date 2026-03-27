/* Chat UI logic — history stored in sessionStorage, no server-side state */

'use strict';

const chatMessages  = document.getElementById('chatMessages');
const chatForm      = document.getElementById('chatForm');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
const charCounter   = document.getElementById('charCounter');
const STORAGE_KEY   = 'rag_chat_history';
const MAX_LENGTH    = 2000;

// ------------------------------------------------------------------
// Session history
// ------------------------------------------------------------------

function loadHistory() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveHistory(history) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch {
    // sessionStorage full — silently ignore
  }
}

// ------------------------------------------------------------------
// DOM helpers
// ------------------------------------------------------------------

function appendMessage(role, content, sources) {
  const wrapper = document.createElement('div');
  wrapper.className = `message message-${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = content;

  if (sources && sources.length > 0) {
    const sourcesEl = buildSources(sources);
    wrapper.appendChild(bubble);
    wrapper.appendChild(sourcesEl);
  } else {
    wrapper.appendChild(bubble);
  }

  chatMessages.appendChild(wrapper);
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
// Form submission
// ------------------------------------------------------------------

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const question = questionInput.value.trim();
  if (!question) return;

  // Clear input and lock UI
  questionInput.value = '';
  autoResize(questionInput);
  setLoading(true);

  // Add user message
  appendMessage('user', question, null);

  // Persist to session history
  const history = loadHistory();
  history.push({ role: 'user', content: question });

  // Loading indicator
  const loadingEl = addLoadingIndicator();

  try {
    const resp = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    const data = await resp.json();
    loadingEl.remove();

    if (!resp.ok || data.error) {
      appendMessage('assistant', `Fehler: ${data.error || resp.statusText}`, null);
    } else {
      appendMessage('assistant', data.answer, data.sources);
      history.push({ role: 'assistant', content: data.answer, sources: data.sources });
    }
  } catch (err) {
    loadingEl.remove();
    appendMessage('assistant', `Verbindungsfehler: ${err.message}`, null);
  }

  saveHistory(history);
  setLoading(false);
  questionInput.focus();
});

function setLoading(loading) {
  sendBtn.disabled = loading;
  sendBtn.querySelector('.btn-text').classList.toggle('hidden', loading);
  sendBtn.querySelector('.btn-spinner').classList.toggle('hidden', !loading);
}

// ------------------------------------------------------------------
// Restore session history on page load
// ------------------------------------------------------------------

(function restoreHistory() {
  const history = loadHistory();
  history.forEach((entry) => {
    if (entry.role === 'user' || entry.role === 'assistant') {
      appendMessage(entry.role, entry.content, entry.sources || null);
    }
  });
})();

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

// Submit on Enter, newline on Shift+Enter
questionInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    chatForm.dispatchEvent(new Event('submit', { cancelable: true }));
  }
});
