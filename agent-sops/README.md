# Agent SOP CLI

A command-line AI agent for **code task generation** powered by [Strands Agents](https://strandsagents.com/) with [Rich](https://github.com/Textualize/rich) for colored terminal output and markdown rendering.

## Overview

This project provides an interactive CLI agent that uses the **Code Task Generator SOP** (Standard Operating Procedure) to transform rough descriptions or PDD implementation plans into structured, well-formatted code task files. The agent leverages an LLM to analyze your input, plan a task breakdown, and generate `.code-task.md` files ready for implementation.

### Key Features

- **Rich Markdown Rendering** - Agent responses are displayed as beautifully formatted markdown in the terminal
- **Streaming Output** - See tool calls in real-time as the agent works
- **Reasoning Display** - Model thinking is shown in collapsible panels
- **Built-in Tools** - File I/O, directory listing, and shell command execution
- **SOP-Driven Workflow** - Follows the Code Task Generator SOP for consistent, structured output
- **Conversational** - Multi-turn interaction with full conversation history

## Requirements

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) package manager
- AWS credentials configured (for Bedrock model access) or another Strands-compatible model provider

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd agent-sops

# Install dependencies with uv
uv sync
```

## Usage

### Run the CLI Agent

```bash
uv run agent-sops
```

This launches an interactive session:

```
╭────────────────── ● Online ───────────────────╮
│ Agent SOP CLI                                 │
│ Code Task Generator powered by Strands Agents │
╰───────────────────────────────────────────────╯
Type your request to generate code tasks.
Type quit or exit to leave.

You > Create a Python script to check CPU status
  ⚙ Tool #1: run_command
  ⚙ Tool #2: list_directory

  Generated code task: .agents/tasks/2025-01-cpu-info/cpu-info-script.code-task.md
  ...

You > quit
Goodbye!
```

### Example Prompts

| Prompt | What It Does |
|--------|-------------|
| `"Create a REST API for user management"` | Generates a structured code task file in description mode |
| `"Generate tasks from .agents/planning/my-project/implementation/plan.md"` | Processes a PDD plan and creates step-based task files |
| `"Break down building a CLI todo app into tasks"` | Analyzes the idea and creates multiple sequenced code tasks |

### Output Structure

Generated tasks follow this directory convention:

```
.agents/tasks/
└── {project_name}/
    ├── task-name.code-task.md          # Description mode
    └── step01/                         # PDD mode
        ├── task-01-setup.code-task.md
        ├── task-02-core.code-task.md
        └── task-03-tests.code-task.md
```

## Architecture

```
src/agent_sops/
└── __init__.py          # CLI agent entry point
    ├── RichCallbackHandler  # Streams LLM output as Rich markdown
    ├── Tools                # read_file, write_file, list_directory, run_command
    └── main()               # Interactive REPL loop
```

### Components

| Component | Description |
|-----------|-------------|
| `RichCallbackHandler` | Custom callback handler that buffers streamed text chunks and renders them as Rich Markdown when a message completes. Displays tool calls with magenta labels and reasoning in dimmed panels. |
| `@tool read_file` | Reads file contents with path expansion |
| `@tool write_file` | Writes content to files, creating parent directories |
| `@tool list_directory` | Lists directory entries with `[DIR]`/`[FILE]` prefixes |
| `@tool run_command` | Executes shell commands with 30s timeout and stderr capture |

### System Prompt

The agent uses the **Code Task Generator SOP** from `strands-agents-sops` as its system prompt. This SOP instructs the agent to:

1. Detect whether input is a description or a PDD plan
2. Analyze requirements and determine complexity
3. Plan a task breakdown and present it for approval
4. Generate properly formatted `.code-task.md` files

## Development

### Run Tests

```bash
uv run pytest tests/ -v
```

### Project Structure

```
agent-sops/
├── src/agent_sops/
│   ├── __init__.py                  # CLI agent implementation
│   └── code-task-generator.sop.md   # SOP definition
├── tests/
│   └── test_cpu_info.py             # Example test suite
├── cpu_info.py                      # Example generated script
├── pyproject.toml                   # Project config (uv)
└── README.md
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `strands-agents` | Agent framework (LLM orchestration, tool execution) |
| `strands-agents-sops` | Pre-built SOPs as system prompts |
| `rich` | Terminal markdown rendering, colored output, panels |

### Adding New Tools

Create tools using the `@tool` decorator from Strands:

```python
from strands.tools import tool

@tool
def my_tool(param: str) -> str:
    """Description shown to the LLM.

    Parameters:
        param: What this parameter does.
    """
    return "result"
```

Then add it to the agent's tool list in `main()`.

## Configuration

The agent uses the default Strands model provider (AWS Bedrock). To use a different provider, modify the `Agent()` constructor:

```python
from strands_openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
agent = Agent(
    model=model,
    system_prompt=code_task_generator,
    tools=[...],
    callback_handler=RichCallbackHandler(),
)
```

## License

See the repository root for license information.
