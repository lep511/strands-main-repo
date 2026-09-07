#!/usr/bin/env python3
"""
Chat Frontend for AgentCore Runtime Loan Orchestrator.

Run: python3 app.py        (English UI)
     python3 app-kor.py    (Korean UI - orchestrator responds in Korean)
Then open: http://localhost:3000

The /chat endpoint streams newline-delimited JSON (NDJSON) events so the
browser can show, in real time, which specialist agent is running and the
response text as the orchestrator generates it:
    {"type": "status", "tool": "<gateway tool name>"}
    {"type": "delta",  "text": "<response text chunk>"}
    {"type": "final",  "response": "<complete response>"}
    {"type": "error",  "error": "<message>"}
Blank lines are keep-alive heartbeats and must be ignored by clients.
"""
import json
import queue
import threading
import uuid
import boto3
from botocore.config import Config
from flask import Flask, request, render_template_string, Response, stream_with_context

app = Flask(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
import os

# Read runtime info from runtime_info.json if available
_runtime_info_path = os.path.join(os.path.dirname(__file__), 'runtime_info.json')
if os.path.exists(_runtime_info_path):
    with open(_runtime_info_path) as f:
        _info = json.load(f)
    _account = _info.get('account_id', os.environ.get('AWS_ACCOUNT_ID', ''))
    _region = _info.get('region', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
    _runtime_id = _info.get('runtime_id', os.environ.get('RUNTIME_ID', ''))
    RUNTIME_ARN = f"arn:aws:bedrock-agentcore:{_region}:{_account}:runtime/{_runtime_id}"
else:
    RUNTIME_ARN = os.environ.get(
        'RUNTIME_ARN',
        'arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/LoanOrchestrator-XXXXX'
    )
    _region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

# Multi-agent orchestration can run for minutes: raise the read timeout past
# botocore's 60s default, and disable retries so a slow call is never
# re-invoked (duplicate account creation etc.)
client = boto3.client(
    'bedrock-agentcore',
    region_name=_region,
    config=Config(read_timeout=900, connect_timeout=10, retries={'max_attempts': 0}),
)

# Interval between keep-alive newlines sent while waiting on the runtime.
# Must stay below CloudFront's 30s origin response timeout.
HEARTBEAT_SECONDS = 10
# ─────────────────────────────────────────────────────────────────────────────

# ─── Language ────────────────────────────────────────────────────────────────
# UI strings per language. app-kor.py calls set_language('ko') before app.run()
# and the chosen language is also sent to the orchestrator, which switches to
# a Korean system prompt.
LANG = 'en'

STRINGS = {
    'en': {
        'html_lang': 'en',
        'title': 'UK Loan Assistant',
        'status_online': 'Online',
        'badge': 'FCA Compliant',
        'welcome': """Hello! I'm your UK loan assistant. I can help you apply for a short-term personal loan of up to £5,000.

To get started, I'll need a few details:
• Your name, phone & email
• National Insurance Number
• Employment & salary details
• Loan amount and purpose

How can I help you today?""",
        'chips': [
            'I want to apply for a loan',
            'What loans are available?',
            'Check my eligibility',
        ],
        'placeholder': 'Type a message…',
        'send_title': 'Send',
        'js': {
            'connection_error': 'Connection error: ',
            'no_response': 'No response.',
            'incomplete': '⚠ The response was interrupted — please send your message again.',
        },
        # Progress labels keyed by gateway target name (matched by substring
        # against the MCP tool name reported by the orchestrator).
        'agents': {
            'account-data-loader': '1/5 Account Data Loader — creating / verifying the customer account',
            'eligibility-filter': '2/5 Eligibility Filter — running KYC & eligibility checks',
            'loan-product-matcher': '3/5 Loan Product Matcher — building an FCA-compliant offer',
            'risk-assessment': '4/5 Risk Assessment — PIN security checks',
            'approval-decision': '5/5 Approval Decision — final approval & disbursement',
        },
    },
    'ko': {
        'html_lang': 'ko',
        'title': '영국 대출 도우미',
        'status_online': '온라인',
        'badge': 'FCA 준수',
        'welcome': """안녕하세요! 영국 단기 대출 도우미입니다. 최대 £5,000까지의 단기 개인 대출 신청을 도와드립니다.

시작하려면 몇 가지 정보가 필요합니다:
• 이름, 전화번호, 이메일
• National Insurance Number
• 고용 형태와 급여 정보
• 대출 금액과 목적

무엇을 도와드릴까요?""",
        'chips': [
            '대출을 신청하고 싶어요',
            '어떤 대출 상품이 있나요?',
            '대출 자격을 확인해 주세요',
        ],
        'placeholder': '메시지를 입력하세요…',
        'send_title': '전송',
        'js': {
            'connection_error': '연결 오류: ',
            'no_response': '응답이 없습니다.',
            'incomplete': '⚠ 응답이 중간에 끊겼습니다 — 메시지를 다시 보내 주세요.',
        },
        'agents': {
            'account-data-loader': '1/5 계정 데이터 로더 — 고객 계정 생성·확인',
            'eligibility-filter': '2/5 자격 필터 — KYC·자격 요건 심사',
            'loan-product-matcher': '3/5 대출 상품 매칭 — FCA 기준 상품 구성',
            'risk-assessment': '4/5 리스크 평가 — PIN 보안 처리',
            'approval-decision': '5/5 승인 결정 — 최종 승인 및 지급',
        },
    },
}


def set_language(lang):
    """Called by app-kor.py to switch the UI and response language."""
    global LANG
    if lang not in STRINGS:
        raise ValueError(f"Unsupported language: {lang}")
    LANG = lang
# ─────────────────────────────────────────────────────────────────────────────

HTML = '''<!DOCTYPE html>
<html lang="{{ s.html_lang }}">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{{ s.title }}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', system-ui, sans-serif;
      background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
      padding: 16px;
    }
    #shell {
      width: 100%; max-width: 760px; height: 92vh;
      display: flex; flex-direction: column;
      border-radius: 20px; overflow: hidden;
      box-shadow: 0 24px 64px rgba(0,0,0,.5);
      background: #ffffff;
    }
    #header {
      background: linear-gradient(90deg, #1565c0, #1e88e5);
      padding: 18px 24px; display: flex; align-items: center; gap: 14px; flex-shrink: 0;
    }
    #header .avatar { width:42px;height:42px;background:rgba(255,255,255,.2);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.3em; }
    #header .info { flex:1; }
    #header .name { color:#fff;font-weight:600;font-size:1.05em; }
    #header .status { color:rgba(255,255,255,.75);font-size:.78em;margin-top:2px;display:flex;align-items:center;gap:5px; }
    #header .dot { width:7px;height:7px;background:#69f0ae;border-radius:50%; }
    #header .badge { background:rgba(255,255,255,.15);color:#fff;font-size:.72em;padding:4px 10px;border-radius:20px;font-weight:500; }
    #messages { flex:1;overflow-y:auto;padding:24px 20px;display:flex;flex-direction:column;gap:16px;background:#f8f9fb; }
    #messages::-webkit-scrollbar { width:5px; }
    #messages::-webkit-scrollbar-thumb { background:#d0d5dd;border-radius:4px; }
    .row { display:flex;align-items:flex-end;gap:10px; }
    .row.user { flex-direction:row-reverse; }
    .bubble-avatar { width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.9em;flex-shrink:0; }
    .row.agent .bubble-avatar { background:linear-gradient(135deg,#1565c0,#1e88e5);color:#fff; }
    .row.user  .bubble-avatar { background:linear-gradient(135deg,#6a1b9a,#ab47bc);color:#fff; }
    .bubble { max-width:72%;padding:12px 16px;border-radius:18px;font-size:.93em;line-height:1.6;white-space:pre-wrap;word-break:break-word; }
    .row.agent .bubble { background:#fff;color:#1a1a2e;border-bottom-left-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.07); }
    .row.user  .bubble { background:linear-gradient(135deg,#6a1b9a,#ab47bc);color:#fff;border-bottom-right-radius:4px; }
    .typing-dots { display:flex;gap:4px;padding:4px 2px; }
    .typing-dots span { width:7px;height:7px;background:#90a4ae;border-radius:50%;animation:bounce 1.2s infinite; }
    .typing-dots span:nth-child(2){animation-delay:.2s}.typing-dots span:nth-child(3){animation-delay:.4s}
    @keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}
    /* Agent progress steps shown inside the reply bubble */
    .steps { display:none;flex-direction:column;gap:6px;margin-bottom:10px;padding:9px 12px;background:#f1f5f9;border-radius:10px;font-size:.82em;color:#455a64;white-space:normal; }
    .steps.visible { display:flex; }
    .step { display:flex;align-items:center;gap:8px; }
    .step .step-icon { width:14px;display:inline-flex;justify-content:center;flex-shrink:0; }
    .step.done { color:#2e7d32; }
    .step.failed { color:#c62828; }
    .spinner { width:10px;height:10px;border:2px solid #90caf9;border-top-color:#1565c0;border-radius:50%;display:inline-block;animation:spin .8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    /* Markdown rendering inside agent bubbles */
    .bubble-body.md { white-space:normal; }
    .bubble-body.md p { margin:.45em 0; }
    .bubble-body.md p:first-child { margin-top:0; }
    .bubble-body.md p:last-child { margin-bottom:0; }
    .bubble-body.md ul, .bubble-body.md ol { margin:.4em 0; padding-left:1.35em; white-space:normal; }
    .bubble-body.md li { margin:.15em 0; }
    .bubble-body.md h1, .bubble-body.md h2, .bubble-body.md h3, .bubble-body.md h4 { margin:.6em 0 .35em; font-size:1.05em; }
    .bubble-body.md h1 { font-size:1.15em; }
    .bubble-body.md h1:first-child, .bubble-body.md h2:first-child, .bubble-body.md h3:first-child { margin-top:0; }
    .bubble-body.md code { background:#eef2f7;border-radius:4px;padding:1px 5px;font-size:.9em;font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
    .bubble-body.md pre { background:#0f172a;color:#e2e8f0;border-radius:8px;padding:10px 12px;overflow-x:auto;margin:.5em 0; }
    .bubble-body.md pre code { background:none;color:inherit;padding:0; }
    .bubble-body.md table { border-collapse:collapse;margin:.5em 0;font-size:.92em;display:block;max-width:100%;overflow-x:auto; }
    .bubble-body.md th, .bubble-body.md td { border:1px solid #dbe2ea;padding:5px 9px;text-align:left; }
    .bubble-body.md th { background:#f1f5f9; }
    .bubble-body.md blockquote { border-left:3px solid #90caf9;margin:.5em 0;padding:2px 10px;color:#546e7a; }
    .bubble-body.md a { color:#1565c0; }
    .bubble-body.md hr { border:none;border-top:1px solid #e0e6ed;margin:.7em 0; }
    .bubble-body.md strong { font-weight:600; }
    .bubble-body.md img { max-width:100%; }
    .bubble-body.error { color:#c62828; }
    .error-note { color:#c62828;font-size:.88em;margin-top:8px;white-space:pre-wrap; }
    #input-bar { padding:14px 16px;background:#fff;border-top:1px solid #e8eaed;display:flex;align-items:center;gap:10px;flex-shrink:0; }
    #msg-input { flex:1;padding:11px 18px;border:1.5px solid #e0e0e0;border-radius:28px;font-size:.95em;font-family:inherit;outline:none;transition:border-color .2s;background:#f8f9fb;color:#1a1a2e; }
    #msg-input:focus { border-color:#1e88e5;background:#fff; }
    #send-btn { width:44px;height:44px;background:linear-gradient(135deg,#1565c0,#1e88e5);border:none;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:opacity .2s,transform .1s;flex-shrink:0; }
    #send-btn:hover{opacity:.9;transform:scale(1.05)}#send-btn:disabled{opacity:.4;cursor:not-allowed;transform:none}
    #send-btn svg{width:20px;height:20px;fill:white}
    #suggestions { padding:0 20px 14px;display:flex;flex-wrap:wrap;gap:8px;background:#f8f9fb; }
    .chip { padding:6px 14px;background:#fff;border:1.5px solid #e0e0e0;border-radius:20px;font-size:.8em;color:#1565c0;cursor:pointer;transition:all .15s;font-family:inherit; }
    .chip:hover{background:#e3f2fd;border-color:#1e88e5}
  </style>
</head>
<body>
<div id="shell">
  <div id="header">
    <div class="avatar">🏦</div>
    <div class="info">
      <div class="name">{{ s.title }}</div>
      <div class="status"><span class="dot"></span>{{ s.status_online }}</div>
    </div>
    <div class="badge">{{ s.badge }}</div>
  </div>
  <div id="messages">
    <div class="row agent">
      <div class="bubble-avatar">🤖</div>
      <div class="bubble">{{ s.welcome }}</div>
    </div>
  </div>
  <div id="suggestions">
    {% for chip in s.chips %}<button class="chip" onclick="quickSend(this)">{{ chip }}</button>{% endfor %}
  </div>
  <div id="input-bar">
    <input id="msg-input" type="text" placeholder="{{ s.placeholder }}" autocomplete="off"/>
    <button id="send-btn" onclick="send()" title="{{ s.send_title }}">
      <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
    </button>
  </div>
</div>
<script>
  const LANG = {{ lang | tojson }};
  const UI = {{ s.js | tojson }};
  const AGENT_LABELS = {{ s.agents | tojson }};

  if (window.marked) { marked.use({ breaks: true, gfm: true }); }

  // Fallback UUID (works on HTTP without crypto.randomUUID)
  function genUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  // Unique session per page load — keeps conversation context in Runtime
  const sessionId = genUUID() + '-' + genUUID();
  // History accumulates all turns — sent with each request so agent has full context
  const history = [];

  // Declare DOM refs BEFORE any functions that use them
  const msgInput = document.getElementById('msg-input');
  const btn = document.getElementById('send-btn');
  const messages = document.getElementById('messages');
  const suggestions = document.getElementById('suggestions');

  msgInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  function quickSend(el) {
    msgInput.value = el.textContent;
    suggestions.style.display = 'none';
    send();
  }

  function scrollDown() { messages.scrollTop = messages.scrollHeight; }

  function addMsg(text, role) {
    const row = document.createElement('div');
    row.className = 'row ' + role;
    const av = document.createElement('div');
    av.className = 'bubble-avatar';
    av.textContent = role === 'agent' ? '🤖' : '👤';
    const bub = document.createElement('div');
    bub.className = 'bubble';
    bub.textContent = text;
    row.appendChild(av);
    row.appendChild(bub);
    messages.appendChild(row);
    scrollDown();
    return bub;
  }

  // Render agent text as sanitized markdown; fall back to plain text when the
  // CDN libraries are unavailable (e.g. offline environments).
  function renderMarkdown(el, text) {
    if (window.marked && window.DOMPurify) {
      el.classList.add('md');
      el.innerHTML = DOMPurify.sanitize(marked.parse(text));
    } else {
      el.textContent = text;
    }
  }

  // One reply "turn": progress steps + typing dots + markdown body
  function addAgentTurn() {
    const row = document.createElement('div');
    row.className = 'row agent';
    const av = document.createElement('div');
    av.className = 'bubble-avatar';
    av.textContent = '🤖';
    const bub = document.createElement('div');
    bub.className = 'bubble';
    const steps = document.createElement('div');
    steps.className = 'steps';
    const typing = document.createElement('div');
    typing.className = 'typing-dots';
    typing.innerHTML = '<span></span><span></span><span></span>';
    const body = document.createElement('div');
    body.className = 'bubble-body';
    bub.appendChild(steps);
    bub.appendChild(typing);
    bub.appendChild(body);
    row.appendChild(av);
    row.appendChild(bub);
    messages.appendChild(row);
    scrollDown();
    return { row, bub, steps, typing, body };
  }

  function labelFor(tool) {
    for (const key in AGENT_LABELS) {
      if (tool.indexOf(key) !== -1) return AGENT_LABELS[key];
    }
    // Unknown tool — show the last segment of the gateway tool name
    const parts = tool.split('___');
    return parts[parts.length - 1];
  }

  function finishActiveSteps(turn) {
    turn.steps.querySelectorAll('.step.active').forEach(el => {
      el.classList.remove('active');
      el.classList.add('done');
      el.querySelector('.step-icon').textContent = '✓';
    });
  }

  function failActiveSteps(turn) {
    turn.steps.querySelectorAll('.step.active').forEach(el => {
      el.classList.remove('active');
      el.classList.add('failed');
      el.querySelector('.step-icon').textContent = '✕';
    });
  }

  function addStep(turn, tool) {
    turn.steps.classList.add('visible');
    finishActiveSteps(turn);
    const step = document.createElement('div');
    step.className = 'step active';
    const icon = document.createElement('span');
    icon.className = 'step-icon';
    icon.innerHTML = '<span class="spinner"></span>';
    const label = document.createElement('span');
    label.className = 'step-label';
    label.textContent = labelFor(tool);
    step.appendChild(icon);
    step.appendChild(label);
    turn.steps.appendChild(step);
    scrollDown();
  }

  let sending = false;   // reentrancy guard: Enter can fire while a turn runs

  async function send() {
    const text = msgInput.value.trim();
    if (!text || sending) return;
    sending = true;
    msgInput.value = '';
    btn.disabled = true;
    suggestions.style.display = 'none';

    addMsg(text, 'user');
    // Add user turn to history BEFORE sending
    history.push({ role: 'user', content: text });

    const turn = addAgentTurn();
    let answer = '';          // accumulated streamed text
    let finalText = null;     // authoritative final response
    let sawFinal = false;     // clean end-of-turn marker from the server
    let errorText = null;
    let breakBeforeNextDelta = false;

    function handleEvent(evt) {
      if (evt.type === 'status' && evt.tool) {
        addStep(turn, evt.tool);
        breakBeforeNextDelta = true;
      } else if (evt.type === 'delta' && evt.text != null && evt.text !== '') {
        if (breakBeforeNextDelta && answer && !answer.endsWith('\\n\\n')) answer += '\\n\\n';
        breakBeforeNextDelta = false;
        answer += String(evt.text);
        turn.typing.style.display = 'none';
        renderMarkdown(turn.body, answer);
        scrollDown();
      } else if (evt.type === 'final') {
        sawFinal = true;
        finalText = evt.response;
      } else if (evt.type === 'error') {
        errorText = evt.error || 'Error';
      }
    }

    function processBuffer(buf, flush) {
      let idx;
      while ((idx = buf.indexOf('\\n')) !== -1) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        if (!line) continue;                      // heartbeat keep-alive
        try { handleEvent(JSON.parse(line)); } catch (e) { /* skip bad line */ }
      }
      if (flush && buf.trim()) {
        try { handleEvent(JSON.parse(buf.trim())); } catch (e) { /* skip */ }
        buf = '';
      }
      return buf;
    }

    try {
      // code-server proxies ports — detect if running behind proxy
      const chatUrl = window.location.pathname.includes('/proxy/')
        ? window.location.pathname.replace(/\\/proxy\\/\\d+\\/.*/, '') + '/proxy/3000/chat'
        : '/chat';
      const res = await fetch(chatUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          history: history.slice(-10),  // last 10 turns for context
          language: LANG
        })
      });

      if (!res.ok) {
        errorText = 'HTTP ' + res.status + ' — ' + (await res.text()).slice(0, 200);
      } else if (res.body && res.body.getReader) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buf += decoder.decode(chunk.value, { stream: true });
          buf = processBuffer(buf, false);
        }
        buf += decoder.decode();
        processBuffer(buf, true);
      } else {
        // Very old browsers: no streaming — parse the full body at once
        processBuffer(await res.text(), true);
      }
    } catch (e) {
      errorText = UI.connection_error + e.message;
    }

    // Finalize the turn. A turn only counts as complete when the server sent
    // a final event AND no error arrived — anything else (mid-stream runtime
    // failure, dropped connection, HTTP error) is surfaced to the user
    // instead of letting a truncated reply pass as a finished answer.
    try {
      turn.typing.style.display = 'none';
      const ok = sawFinal && !errorText;
      if (ok) {
        finishActiveSteps(turn);
        // Keep the streamed text (it may include narration between agent
        // calls); fall back to the final event when nothing was streamed.
        const shown = answer || finalText || UI.no_response;
        if (!answer) renderMarkdown(turn.body, shown);
        // Add agent turn to history AFTER receiving — prefer the
        // orchestrator's authoritative final message for context.
        history.push({ role: 'assistant', content: finalText || shown });
      } else {
        failActiveSteps(turn);
        const note = document.createElement('div');
        note.className = 'error-note';
        note.textContent = errorText || UI.incomplete;
        turn.bub.appendChild(note);
        // Drop the unanswered user turn so a retry doesn't confuse the
        // orchestrator with a half-completed exchange.
        if (history.length && history[history.length - 1].role === 'user') history.pop();
      }
      scrollDown();
    } finally {
      btn.disabled = false;
      sending = false;
      msgInput.focus();
    }
  }
</script>
</body>
</html>'''


@app.route('/')
def index():
    return render_template_string(HTML, s=STRINGS[LANG], lang=LANG)


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    session_id = data.get('session_id', str(uuid.uuid4()))
    history = data.get('history', [])  # List of {role, content} dicts
    language = data.get('language', LANG)

    events = queue.Queue()

    def emit(obj):
        events.put(json.dumps(obj))

    def relay_stream(body):
        """Translate the runtime's SSE lines into frontend NDJSON events.

        Returns True if a final event was relayed.
        """
        saw_final = False
        for raw in body.iter_lines(chunk_size=1):
            if not raw:
                continue
            line = raw.decode('utf-8', errors='replace')
            if line.startswith(':'):        # SSE comment / keep-alive
                continue
            if line.startswith('data:'):
                line = line[5:].strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except ValueError:
                emit({'type': 'delta', 'text': line})
                continue
            if isinstance(evt, str):
                emit({'type': 'delta', 'text': evt})
            elif isinstance(evt, dict):
                etype = evt.get('type')
                if etype == 'tool_use' and evt.get('tool'):
                    emit({'type': 'status', 'tool': evt['tool']})
                elif etype == 'delta' and 'text' in evt:
                    emit({'type': 'delta', 'text': evt['text']})
                elif etype == 'final':
                    emit({'type': 'final', 'response': evt.get('result', evt.get('response'))})
                    saw_final = True
                elif etype == 'error' or 'error' in evt:
                    emit({'type': 'error', 'error': str(evt.get('error', evt))})
                # Orchestrators that yield raw Strands events (SDK docs default)
                elif 'data' in evt:
                    emit({'type': 'delta', 'text': str(evt['data'])})
                elif (evt.get('current_tool_use') or {}).get('name'):
                    emit({'type': 'status', 'tool': evt['current_tool_use']['name']})
        return saw_final

    def read_body_bytes(response_obj):
        if hasattr(response_obj, 'read'):
            return response_obj.read()
        if isinstance(response_obj, (bytes, bytearray)):
            return bytes(response_obj)
        if isinstance(response_obj, list):
            return b''.join(
                chunk if isinstance(chunk, (bytes, bytearray)) else chunk.encode()
                for chunk in response_obj
            )
        return b''

    def call_runtime():
        try:
            resp = client.invoke_agent_runtime(
                agentRuntimeArn=RUNTIME_ARN,
                qualifier='DEFAULT',
                runtimeSessionId=session_id,
                payload=json.dumps({
                    'query': message,
                    'history': history,     # Passed to loan_orchestrator handler
                    'language': language,   # 'ko' switches the orchestrator to Korean
                }).encode()
            )
            if 'text/event-stream' in resp.get('contentType', ''):
                if not relay_stream(resp['response']):
                    # Stream ended without a final event — let the client
                    # finalize with whatever text it accumulated.
                    emit({'type': 'final', 'response': None})
            else:
                # Legacy non-streaming runtime: single JSON body
                raw_body = read_body_bytes(resp.get('response'))
                try:
                    parsed = json.loads(raw_body.decode('utf-8'))
                    reply = parsed.get('result', parsed.get('response', str(parsed)))
                except Exception:
                    reply = raw_body.decode('utf-8', errors='replace')
                emit({'type': 'final', 'response': reply})
        except Exception as e:
            emit({'type': 'error', 'error': str(e)})
        finally:
            events.put(None)   # sentinel: close the response

    threading.Thread(target=call_runtime, daemon=True).start()

    def generate():
        # Events stream to the browser as NDJSON lines. While the runtime is
        # quiet (e.g. a specialist Lambda is working) we emit a blank line
        # every HEARTBEAT_SECONDS so CloudFront's 30s origin response timeout
        # never fires.
        while True:
            try:
                item = events.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                yield '\n'
                continue
            if item is None:
                break
            yield item + '\n'

    return Response(
        stream_with_context(generate()),
        mimetype='application/x-ndjson',
        headers={
            # no-transform keeps intermediary compression (e.g. code-server's
            # proxy) from buffering the streamed chunks
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
        },
    )


if __name__ == '__main__':
    print(f"\n🏦 UK Loan Assistant Chat")
    print(f"   Runtime ARN: {RUNTIME_ARN}")
    print(f"   Open: http://localhost:3000\n")
    app.run(host='0.0.0.0', port=3000, debug=False)
