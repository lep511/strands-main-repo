import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import type { CallToolResult } from "@modelcontextprotocol/client";
import "./global.css";
import "./mcp-app.css";

interface AgentResult {
  message: string;
  response: string;
  tools_used: string[];
}

function escapeHtml(text: string): string {
  const el = document.createElement("span");
  el.textContent = text;
  return el.innerHTML;
}

function extractResult(result: CallToolResult): AgentResult | null {
  const sc = result.structuredContent as AgentResult | undefined;
  if (sc?.response) return sc;
  return null;
}

function renderConversation(data: AgentResult): void {
  const conv = document.getElementById("conversation")!;
  conv.innerHTML = "";

  const userDiv = document.createElement("div");
  userDiv.className = "message user-message";
  userDiv.innerHTML =
    `<div class="message-label">You</div>` +
    `<div class="message-body">${escapeHtml(data.message)}</div>`;
  conv.appendChild(userDiv);

  const agentDiv = document.createElement("div");
  agentDiv.className = "message agent-message";

  let toolsHtml = "";
  if (data.tools_used.length > 0) {
    const tags = data.tools_used
      .map((t) => `<span class="tool-tag">${escapeHtml(t)}</span>`)
      .join("");
    toolsHtml = `<div class="tools-row">${tags}</div>`;
  }

  agentDiv.innerHTML =
    `<div class="message-label">Agent</div>` +
    toolsHtml +
    `<div class="message-body">${escapeHtml(data.response)}</div>`;
  conv.appendChild(agentDiv);
}

function handleHostContext(ctx: McpUiHostContext): void {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
}

const app = new App({ name: "Strands Agent App", version: "1.0.0" });

app.onteardown = async () => ({});
app.onerror = console.error;

app.ontoolinput = (params) => {
  const message = params.arguments?.message as string | undefined;
  const conv = document.getElementById("conversation")!;
  if (message) {
    conv.innerHTML =
      `<div class="message user-message">` +
      `<div class="message-label">You</div>` +
      `<div class="message-body">${escapeHtml(message)}</div>` +
      `</div>` +
      `<div class="loading"><span class="spinner"></span> Thinking...</div>`;
  }
};

app.ontoolresult = (result) => {
  const data = extractResult(result);
  if (data) {
    renderConversation(data);
    return;
  }

  const text =
    result.content?.find((c) => c.type === "text")?.text ?? "No response";
  const conv = document.getElementById("conversation")!;
  conv.innerHTML =
    `<div class="message agent-message">` +
    `<div class="message-label">Agent</div>` +
    `<div class="message-body ${result.isError ? "error" : ""}">${escapeHtml(text)}</div>` +
    `</div>`;
};

app.onhostcontextchanged = handleHostContext;

const followUpInput = document.getElementById(
  "follow-up-input",
) as HTMLInputElement;
const followUpBtn = document.getElementById("follow-up-btn")!;

async function sendFollowUp(): Promise<void> {
  const text = followUpInput.value.trim();
  if (!text) return;
  followUpInput.value = "";
  try {
    await app.sendMessage(
      { role: "user", content: [{ type: "text", text }] },
      { signal: AbortSignal.timeout(10_000) },
    );
  } catch (e) {
    console.error("Failed to send follow-up:", e);
  }
}

followUpBtn.addEventListener("click", sendFollowUp);
followUpInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendFollowUp();
});

app.connect().then(() => {
  const ctx = app.getHostContext();
  if (ctx) handleHostContext(ctx);
});
