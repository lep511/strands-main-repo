---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 13
title: "Code Execution Sandbox: Run Untrusted Agent Code Safely"
summary: "Run LLM-generated code in an isolated, air-gapped sandbox with stateful memory across turns."
tags: ["Phase 3: Sandbox", "Prevention", "Sandboxing", "Security"]
canonical_url: "https://adventofagents.com/2026/10/13"
markdown_url: "https://adventofagents.com/2026/10/13.md"
video_url: "https://www.youtube.com/embed/2lqh-yA_Lv0"
primary_video:
  title: "Day 13: Sandboxed Code Execution (Agent Sandbox)"
  creator_name: "Anil Kumar Sirikande"
  duration: "8:14"
  video_url: "https://www.youtube.com/embed/2lqh-yA_Lv0"
companion_videos:
  - id: "s3-d13-jaymin-west-sandbox"
    title: "Agents Are An Environment Problem (Jun 2026) + Oct 12 Google Cloud GKE Agent Sandbox Release"
    creator_name: "Jaymin West"
    creator_handle: "@jayminwest"
    creator_url: "https://www.youtube.com/@jayminwest"
    duration: "13:14"
    video_url: "https://www.youtube.com/embed/aUNSTO6rED0"
    watch_url: "https://www.youtube.com/watch?v=aUNSTO6rED0"
    invitation_headline: "Why autonomous agents are fundamentally an execution environment & sandboxing problem"
---

# 📦 Day 13: Code Execution Sandbox: Run Untrusted Agent Code Safely

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/13?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day13) · [Raw Markdown](https://adventofagents.com/2026/10/13.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day13)

**Summary:** Run LLM-generated code in an isolated, air-gapped sandbox with stateful memory across turns.

## 🧭 Community Perspective & Companion Deep Dive

- **[Featured Perspective: Agents Are An Environment Problem (@jayminwest · Jun 2026)](https://www.youtube.com/watch?v=aUNSTO6rED0)** by **Jaymin West** (@jayminwest · 13:14) — Watch Jaymin West's June 2026 breakdown ('Agents Are An Environment Problem') alongside his upcoming October 12, 2026 Google Cloud video demonstrating Warren on GKE Agent Sandbox (`sigs.k8s.io/agent-sandbox`) with gVisor/Kata microVM isolation.

**Day 13 of Google's Advent of Agents — Season 3**

Days 10 through 12 showed how to screen untrusted prompts and govern which pre-built tools an agent can call. Many workflows, such as calculating a mortgage amortization schedule, analyzing CSV datasets, or running simulations, require your agent to write and execute custom Python or JavaScript on the fly. Running LLM-generated scripts directly on your host machine or shared container exposes your infrastructure to credential harvesting from environment variables, infinite loops, and lateral network movement.

**How It Works**

**Code Execution** in Gemini Enterprise Agent Platform runs untrusted agent code inside a managed, air-gapped sandbox that provisions in under a second. The platform supports multiple sandbox runtimes, including Code Execution for scripting, Computer Use for browser automation, Shell Execution for CLI operations, and custom containers for your own binaries. Because you call the sandbox directly through the Agent Platform API, your agent can use it from any framework (including ADK) whether the agent runs locally on your laptop or in the cloud:

![Code Execution Sandbox Isolation and Stateful Execution Flow](/s03/s3-day13-code-execution-sandbox.png)

- **Air-Gapped Execution & Locked Dependencies**: Each sandbox runs in an isolated file system (2 vCPU and 1.5 GB RAM by default, or 4 vCPU and 4 GB RAM) with zero network access and no access to host resources. Over 50 pre-installed packages (`numpy`, `pandas`, `scipy`, `scikit-learn`, `matplotlib`) are ready out of the box, while arbitrary `pip` or `npm` installations are blocked to prevent supply-chain injection.
- **Multiple On-Demand Sandboxes with Stateful Memory**: A single Agent Runtime host can spin up multiple isolated sandboxes on demand so each user session gets its own private workspace. In `app/tools.py`, `execute_sandbox_code` provisions a runtime and a dedicated sandbox on first use, stores the sandbox name in `tool_context.state["sandbox_name"]`, and reuses it across turns to preserve variables and up to 100 MB of files until its TTL expires (30 minutes here, configurable up to 14 days). `reset_or_cleanup_sandbox` deletes both when you are done.

**Resources:**

- [Code Execution Overview](https://g.dev/cloud/adventofagents-season3-docs-code-execution-overview)
- [Code Execution Quickstart](https://g.dev/cloud/adventofagents-season3-docs-code-execution-quickstart)
- [Sandboxes Overview](https://g.dev/cloud/adventofagents-season3-docs-sandbox-overview)
- [Manage Sandboxes](https://g.dev/cloud/adventofagents-season3-docs-manage-sandboxes)

## Code & Commands

### 1. Quickstart & Local Playground

```bash
export CLOUDSDK_METRICS_ENVIRONMENT="advent-of-agents-s3-day13"

# STEP 1 - Enable the API, install the CLI, and scaffold the math-agent project
# --force --upgrade replaces any older or pip-installed agents-cli with a clean, current one.
gcloud services enable aiplatform.googleapis.com
uv tool install --force --upgrade google-agents-cli
agents-cli create math-agent --prototype --yes
cd math-agent && agents-cli install

# STEP 2 - Replace app/agent.py and create app/tools.py with the next two tabs

# STEP 3 - Authenticate and point the sandbox tools at your project
# Leave GOOGLE_CLOUD_LOCATION as scaffolded ("global") so the Gemini model resolves;
# app/tools.py runs the sandboxes in us-central1 on its own.
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project)

# STEP 4 - Launch the playground, open the URL it prints, and send these three messages
agents-cli playground
# 1) "What is the monthly payment on a 450000 dollar, 30-year mortgage at 6.375% APR?"
#    Verify: an execute_sandbox_code call shows the generated Python; click its response
#    chip to see the sandbox stdout. The answer is $2,807.41. The first call is slower
#    because it provisions the sandbox.
# 2) "Using the variables already in the sandbox, what is the total interest paid?"
#    Verify: the new code uses P, M, and n without redefining them. Total interest is
#    $560,669.24 (or $560,667.60 if the agent rounds the payment first).
# 3) "Clean up the sandbox."
#    Verify: reset_or_cleanup_sandbox runs. Deleting the runtime can take a minute.

# STEP 5 - Stop the playground (Ctrl+C), then delete any sandbox host left behind
uv run python -c "import agentplatform; c = agentplatform.Client(project='$GOOGLE_CLOUD_PROJECT', location='us-central1'); [c.agent_engines.delete(name=r.api_resource.name, force=True) for r in c.agent_engines.list() if r.api_resource.display_name == 'math-agent-sandbox-host']"
```

### 2. Agent Definition (app/agent.py)

```python
# The math agent. Gemini decides when a question needs code; the two tools in
# app/tools.py run that code in an isolated Agent Platform sandbox.
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini

from app.tools import execute_sandbox_code, reset_or_cleanup_sandbox

MODEL = "gemini-3.8-flash"

INSTRUCTION = """You are a rigorous mathematical reasoning assistant.
CRITICAL OPERATIONAL RULES:
1. NEVER guess or mentally approximate complex calculations.
2. For ANY calculation, synthesize Python code and run it with `execute_sandbox_code`.
3. Ensure all values and answers are explicitly printed via print(...) for stdout capture.
4. Variables and state persist across turns in the sandbox container session.
5. If code errors in stderr, analyze the traceback, fix the code, and re-run.
"""

root_agent = Agent(
    name="math_agent",
    model=Gemini(model=MODEL),
    instruction=INSTRUCTION,
    tools=[execute_sandbox_code, reset_or_cleanup_sandbox],
)

app = App(root_agent=root_agent, name="app")
```

### 3. Sandbox Execution Tool (app/tools.py)

```python
# Sandbox tools for the math agent. The agent writes Python and these tools run
# it in an isolated Agent Platform sandbox instead of on your machine.
import json
import os

import agentplatform
from agentplatform import types
from google.adk.tools import ToolContext

# Sandboxes live in a regional Agent Runtime instance; the Gemini model stays on "global".
SANDBOX_LOCATION = "us-central1"
HOST_DISPLAY_NAME = "math-agent-sandbox-host"


def _client() -> agentplatform.Client:
    return agentplatform.Client(
        project=os.environ["GOOGLE_CLOUD_PROJECT"], location=SANDBOX_LOCATION
    )


def execute_sandbox_code(code: str, tool_context: ToolContext) -> dict:
    """Executes Python code in an isolated Google Agent Platform sandbox container.

    Variables and files persist between calls in the same conversation.
    print() every value you need; only stdout and stderr are returned.

    Args:
        code: The Python source to run.
    """
    client = _client()

    # 1. First call in this conversation: provision a parent runtime and an
    #    isolated Python sandbox, and remember both in session state
    sandbox_name = tool_context.state.get("sandbox_name")
    if not sandbox_name:
        runtime = client.agent_engines.create(config={"display_name": HOST_DISPLAY_NAME})
        sandbox_op = client.agent_engines.sandboxes.create(
            spec={"code_execution_environment": {"code_language": "LANGUAGE_PYTHON"}},
            name=runtime.api_resource.name,
            config=types.CreateAgentEngineSandboxConfig(
                display_name="math-reasoning-sandbox",
                ttl="1800s",  # 30-minute time-to-live
            ),
        )
        sandbox_name = sandbox_op.response.name
        tool_context.state["runtime_name"] = runtime.api_resource.name
        tool_context.state["sandbox_name"] = sandbox_name

    # 2. Execute untrusted code in the same sandbox, so variables survive across turns
    response = client.agent_engines.sandboxes.execute_code(
        name=sandbox_name,
        input_data={"code": code},
    )

    result = {}
    for output in response.outputs:
        if output.mime_type == "application/json":
            result = json.loads(output.data.decode("utf-8"))
    return {
        "status": "success",
        "stdout": result.get("msg_out", "").strip(),
        "stderr": result.get("msg_err", "").strip(),
    }


def reset_or_cleanup_sandbox(tool_context: ToolContext) -> dict:
    """Deletes this conversation's sandbox and its parent runtime.

    Call it when the user asks to reset, start fresh, or clean up. The next
    execute_sandbox_code call provisions a new, empty sandbox.
    """
    runtime_name = tool_context.state.get("runtime_name")
    if not runtime_name:
        return {"status": "nothing to clean up"}

    # force=True also deletes the sandboxes inside the runtime
    _client().agent_engines.delete(name=runtime_name, force=True)
    tool_context.state["runtime_name"] = None
    tool_context.state["sandbox_name"] = None
    return {"status": "deleted", "runtime": runtime_name}
```

## Resources & Links

- **#1 Featured Cross-Promotion: [Featured Perspective: Agents Are An Environment Problem (@jayminwest · Jun 2026)](https://www.youtube.com/watch?v=aUNSTO6rED0)** — Jaymin West explains why autonomous agents require isolated runtime sandboxes, paired with his Oct 12, 2026 Google Cloud GKE Agent Sandbox tutorial.
- **[Code Execution Overview](https://g.dev/cloud/adventofagents-season3-docs-code-execution-overview)** — Sandbox features, the 100 MB file I/O and 14-day state limits, and the full list of preinstalled libraries.
- **[Code Execution Quickstart](https://g.dev/cloud/adventofagents-season3-docs-code-execution-quickstart)** — Create a sandbox, run code with execute_code, and reuse the same sandbox to keep state between calls.
- **[Sandboxes Overview](https://g.dev/cloud/adventofagents-season3-docs-sandbox-overview)** — How sandboxes differ from Agent Runtime, the isolation guarantees, TTLs, and the available sandbox types.
- **[Manage Sandboxes](https://g.dev/cloud/adventofagents-season3-docs-manage-sandboxes)** — List, inspect, pause, resume, and delete sandboxes, and set a TTL so they clean up automatically.
