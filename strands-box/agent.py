"""A Strands Agents SDK agent that works on a project from inside a box, on Linux.

The box starts this file with the host's /usr/bin/python3.13 and passes the task on the command
line, after `--`. Every tool goes through the box: shell commands run in the box's shell (the
`bash` alias on PATH), and Python snippets run in Monty (the `python3` alias), so the policy decides
every command and every file operation. This process itself reaches only what [agent.filesystem]
in box.toml grants.
"""

import os
import shlex
import subprocess
import sys

# The SDK sits in a `uv pip install --target` directory. The box refuses every PYTHON* variable, so
# the directory arrives as STRANDS_LIB_DIR and this file puts it on the import path itself.
LIB_DIR = os.environ.get("STRANDS_LIB_DIR")
if not LIB_DIR:
    sys.exit("set STRANDS_LIB_DIR in [agent.env] in box.toml")
sys.path.insert(0, LIB_DIR)

from strands import Agent, tool  # noqa: E402
from strands.models import BedrockModel  # noqa: E402

COMMAND_TIMEOUT = 300
MAX_OUTPUT = 20000

SYSTEM_PROMPT = """You work on the project in the current directory, with the tools you are given.
Every tool runs inside a sandbox whose policy decides each command and each file operation. You may
read the project and write files under out/; anything else may be refused.
Keep answers to a few sentences. When a tool reports that the policy denied an operation, quote the
denial, say what it stopped, and end your turn. Do not look for another way to do it."""


def run(argv: list[str], shown: str) -> str:
    """Run one alias the box put on PATH, show the call on stderr, and return what it printed."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"[tool] {shown} (timed out)", file=sys.stderr)
        return f"timed out after {COMMAND_TIMEOUT}s"
    print(f"[tool] {shown} (exit {done.returncode})", file=sys.stderr)
    if done.stderr:
        print(done.stderr.rstrip(), file=sys.stderr)
    if done.returncode == 0:
        return (done.stdout or "(no output)")[:MAX_OUTPUT]
    return f"exit {done.returncode}\n{done.stdout}{done.stderr}"[:MAX_OUTPUT]


def shell(command: str) -> str:
    """Run one command in the box's shell."""
    return run(["bash", "-c", command], command)


def python(code: str) -> str:
    """Run one Python snippet in Monty, the box's Python interpreter."""
    first = code.strip().splitlines()[0] if code.strip() else ""
    return run(["python3", "-c", code], f"python3 -c {first!r}...")


@tool
def list_files(path: str = ".") -> str:
    """List a directory in the project, by its path relative to the project.

    Args:
        path: The directory to list. Defaults to the project root.
    """
    return shell(f"ls -la {shlex.quote(path)}")


@tool
def read_file(path: str) -> str:
    """Read one text file in the project, by its path relative to the project.

    Args:
        path: The file to read.
    """
    return shell(f"cat {shlex.quote(path)}")


@tool
def write_file(path: str, content: str) -> str:
    """Write a text file in the project, by its path relative to the project, replacing it.

    Args:
        path: The file to write, such as out/report.md.
        content: The full text of the file.
    """
    return python(f"from pathlib import Path\nPath({path!r}).write_text({content!r})\nprint('wrote', {path!r})")


@tool
def run_command(command: str) -> str:
    """Run a command in the project directory and return its output.

    The shell implements ls, cat, grep, sed, head, tail, sort, uniq, cut, tr, wc, find, jq, and the
    usual builtins. Any other program is refused unless the policy permits it.

    Args:
        command: The shell command to run.
    """
    return shell(command)


@tool
def run_python(code: str) -> str:
    """Run a Python snippet in the project directory and return what it printed.

    It runs in Monty, a subset of Python. It imports only asyncio, base64, binascii, collections,
    copy, dataclasses, datetime, functools, itertools, json, math, os, pathlib, random, re, sys,
    time, typing, and unicodedata: no csv, no subprocess, and no third-party packages. There is no
    os.environ and no Path.resolve(). Use print() for results.

    Args:
        code: The Python source to run.
    """
    return python(code)


def main() -> int:
    # Keep the model's words in order with the tool lines when the output goes to a file.
    sys.stdout.reconfigure(line_buffering=True)
    task = " ".join(sys.argv[1:])
    if not task:
        print("usage: box run --config box.toml -- <task>", file=sys.stderr)
        return 2
    missing = [name for name in ("MODEL_ID", "AWS_REGION") if name not in os.environ]
    if missing:
        print(f"set {' and '.join(missing)} in [agent.env] in box.toml", file=sys.stderr)
        return 2
    agent = Agent(
        model=BedrockModel(
            model_id=os.environ["MODEL_ID"],
            region_name=os.environ["AWS_REGION"],
            max_tokens=16000,
        ),
        system_prompt=SYSTEM_PROMPT,
        tools=[list_files, read_file, write_file, run_command, run_python],
    )
    agent(task)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
