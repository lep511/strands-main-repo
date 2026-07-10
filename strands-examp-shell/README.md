<div align="center">
  <div>
    <a href="https://strandsagents.com">
      <img src="https://strandsagents.com/latest/assets/logo-github.svg" alt="Strands Agents" width="55px" height="105px">
    </a>
  </div>

  <h1>Strands Shell Examples</h1>
  <h2>Practical examples of sandboxed shell usage for AI agents.</h2>
</div>

---

## Examples

| File | What it demonstrates |
|------|---------------------|
| `main.py` | Credential injection with [mem0](https://mem0.ai) API, `allowed_urls` network restrictions, and `env` seeding |
| `example_commands.py` | Text processing, JSON with jq, Lua scripting, pipelines, redirections, find + xargs |

## Setup

```bash
uv sync
```

Create a `.env` file with your API keys:

```bash
MEM0_API_KEY=your-mem0-api-key
```

## Run

```bash
uv run main.py
uv run example_commands.py
```

## What's covered

### `main.py` — Credentials & Network Access

- **Credential injection** via `env` — pass API tokens into the sandbox without exposing them in command output
- **`allowed_urls`** — restrict the sandbox to only reach specific API domains
- **mem0 API** — add and search memories using `curl` inside the sandbox
- **Network restrictions** — requests to non-allowed URLs are blocked (exit code 6)

```python
shell = strands_shell.Shell(
    allowed_urls=["https://api.mem0.ai/"],
    env={"MEM0_AUTH": f"Token {api_key}"},
    timeout=15.0,
)

shell.write_file("/tmp/payload.json", json.dumps(data).encode())
result = shell.run(
    "curl -X POST https://api.mem0.ai/v3/memories/add/ "
    "-H 'Content-Type: application/json' "
    "-H \"Authorization: $MEM0_AUTH\" "
    "-d \"$(cat /tmp/payload.json)\""
)
```

### `example_commands.py` — Shell Commands & Scripting

- **Text processing**: `grep`, `sed`, `cut`, `sort`, `wc`
- **JSON**: `jq` filters, selects, transforms
- **Shell language**: `for` loops, `if/elif/else`, `case`, functions, here-docs, command substitution
- **Lua scripting**: CSV parsing, log analysis with `lua -e`
- **Pipelines**: multi-stage `|` chains, `>` and `>>` redirections
- **Find + xargs**: file discovery and batch processing

```python
shell = strands_shell.Shell(timeout=30.0)

shell.write_file("/tmp/data/config.json", config_bytes)
result = shell.run("cat /tmp/data/config.json | jq '[.endpoints[] | select(.rate_limit > 50)]'")
```

## Key concepts

| Concept | Description |
|---------|-------------|
| `Bind` | Maps a host directory into the sandbox VFS. `mode="copy"` snapshots at construction; `mode="direct"` passes through live |
| `allowed_urls` | Only these URL prefixes can be reached by `curl`. Everything else is blocked |
| `env` | Seed environment variables into the sandbox. Useful for auth headers |
| `Limits` | Resource caps: max output, max file size, max inodes |
| `timeout` | Per-command wall-clock limit in seconds |
| `write_file` / `read_file` | Direct VFS access without shell commands |

## Limitations

- **No native binaries** — `cargo`, `rustc`, `python`, `node` etc. cannot run inside the sandbox
- **Regex** — uses Rust `regex` crate; no backreferences, lookaround, or `grep -P`
- **`curl`** — no `--max-time`, `--retry`, `-F`, or cookie jar
- **`jq`** — backed by `jaq`; no `--arg`, `--argjson`, or `inputs`

See the [full command reference](https://strandsagents.com/docs/user-guide/shell/commands/) for supported flags and known gaps.

## Links

- [Documentation](https://strandsagents.com/docs/user-guide/shell/)
- [Configuration](https://strandsagents.com/docs/user-guide/shell/configuration/)
- [Security Model](https://strandsagents.com/docs/user-guide/shell/security/)
- [Strands Shell repo](https://github.com/strands-agents/shell)
