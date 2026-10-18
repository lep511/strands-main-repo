"""STEP 12: the user-facing app (~ the ADK sample UI client).

* /login              simulated sign-in (a signed cookie). In production: Cognito / your IdP.
* /api/chat           gets the user's GitHub token from AgentCore Identity, or a consent URL.
* /oauth2/callback    session binding: AgentCore redirects here after GitHub consent; the app
                      checks the signed-in user and calls CompleteResourceTokenAuth.

Usage:
    uv run src/module-6/app.py      # http://localhost:8501
"""

import hashlib
import hmac
import html
import os
import secrets

import uvicorn
from botocore.exceptions import ClientError
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import APP_PORT, MODEL_ID, WORKLOAD_NAME
from delegation import Delegation
from devops_agent import build_agent

COOKIE = "aoa_day06_user"
_SECRET = os.getenv("APP_SESSION_SECRET", secrets.token_hex(32)).encode()

app = FastAPI(title="Advent of Agents Day 6 — DevOps Assistant")
delegation = Delegation()


def log(user: str, action: str, detail: str = "") -> None:
    print(f"  [delegation] agent={WORKLOAD_NAME} user={user:<10} {action:<18} {detail}", flush=True)


def sign(user: str) -> str:
    return f"{user}.{hmac.new(_SECRET, user.encode(), hashlib.sha256).hexdigest()}"


def signed_in_user(request: Request) -> str | None:
    value = request.cookies.get(COOKIE, "")
    user, _, mac = value.rpartition(".")
    if user and hmac.compare_digest(mac, hmac.new(_SECRET, user.encode(), hashlib.sha256).hexdigest()):
        return user
    return None


@app.post("/login")
def login(username: str = Form(...)) -> RedirectResponse:
    user = "".join(ch for ch in username.lower() if ch.isalnum() or ch in "-_")[:32] or "anonymous"
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE, sign(user), httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE)
    return response


@app.post("/api/chat")
async def chat(request: Request) -> JSONResponse:
    user = signed_in_user(request)
    if not user:
        return JSONResponse({"error": "sign in first"}, status_code=401)
    prompt = (await request.json()).get("prompt", "").strip()

    result = delegation.token_for(user)
    if result.consent_url:
        log(user, "consent-required", "no GitHub token in the vault yet")
        return JSONResponse({"consent_url": result.consent_url})

    log(user, "token-from-vault", "calling GitHub MCP as the user")
    try:
        agent = build_agent(result.token)
    except Exception:
        # Revoked or expired at GitHub: the user must consent again (forceAuthentication).
        log(user, "github-rejected", "token no longer valid")
        retry = delegation.token_for(user, force=True)
        return JSONResponse({"consent_url": retry.consent_url, "error": "GitHub rejected the stored token"})
    reply = await agent.invoke_async(prompt)
    return JSONResponse({"reply": str(reply), "tools": sorted(reply.metrics.tool_metrics)})


@app.get("/oauth2/callback")
def oauth2_callback(request: Request, session_id: str | None = None) -> HTMLResponse:
    user = signed_in_user(request)
    if not session_id:
        return HTMLResponse("missing session_id", status_code=400)
    if not user:
        # Whoever opened the consent link is not signed in here: do NOT bind the token.
        log("?", "binding-rejected", "no signed-in user")
        return HTMLResponse("Sign in to the app before completing consent.", status_code=401)
    try:
        delegation.complete(session_id, user)
    except ClientError as exc:
        # e.g. the session was started by another user, or expired (10 minutes)
        log(user, "binding-rejected", exc.response["Error"]["Code"])
        return HTMLResponse(f"Could not complete consent: {html.escape(exc.response['Error']['Message'])}", status_code=403)
    log(user, "session-bound", "token stored in the vault for this user")
    return RedirectResponse("/?consented=1", status_code=303)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>DevOps Assistant · Day 6</title>
<style>body{{font-family:system-ui;max-width:760px;margin:2rem auto;padding:0 1rem}}
#log div{{margin:.6rem 0;white-space:pre-wrap}} .me{{color:#555}} textarea{{width:100%;height:4rem}}
.consent{{background:#fff7e0;padding:.8rem;border-radius:6px}}</style></head><body>
<h2>🎫 DevOps Assistant <small style="font-weight:normal">· acting on behalf of <b>{user}</b></small></h2>
<form method="post" action="/logout"><button>Sign out</button> <small>model: {model}</small></form>
<div id="log"></div>
<textarea id="prompt">List my private GitHub repositories and my open pull requests.</textarea>
<button id="send">Send</button>
<script>
const log = document.getElementById('log');
function add(cls, text) {{ const d = document.createElement('div'); d.className = cls; d.textContent = text; log.appendChild(d); return d; }}
async function send(prompt) {{
  add('me', '🧑 ' + prompt); const wait = add('', '🤖 …');
  const r = await fetch('/api/chat', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{prompt}})}});
  const data = await r.json();
  if (data.consent_url) {{
    localStorage.setItem('pending', prompt);
    wait.className = 'consent'; wait.textContent = '';
    const a = document.createElement('a'); a.href = data.consent_url; a.textContent = 'Sign in with GitHub to let the agent act as you';
    wait.append('🔐 The agent has no GitHub token for you yet. ', a);
  }} else {{ wait.textContent = '🤖 ' + (data.reply || data.error) + (data.tools ? '\\n\\ntools: ' + data.tools.join(', ') : ''); }}
}}
document.getElementById('send').onclick = () => send(document.getElementById('prompt').value);
if (new URLSearchParams(location.search).get('consented') && localStorage.getItem('pending')) {{
  const p = localStorage.getItem('pending'); localStorage.removeItem('pending'); history.replaceState(null, '', '/'); send(p);
}}
</script></body></html>"""

LOGIN = """<!doctype html><html><head><meta charset="utf-8"><title>Sign in · Day 6</title></head>
<body style="font-family:system-ui;max-width:420px;margin:4rem auto">
<h2>Sign in</h2><p>Simulated identity provider: pick any user name (e.g. <b>alice</b> or <b>bob</b>).</p>
<form method="post" action="/login"><input name="username" autofocus required> <button>Sign in</button></form></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> str:
    user = signed_in_user(request)
    return PAGE.format(user=html.escape(user), model=html.escape(MODEL_ID)) if user else LOGIN


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=APP_PORT)
