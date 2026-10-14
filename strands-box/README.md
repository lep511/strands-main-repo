# A Strands Agents SDK agent in a box, on Linux

A [Strands Agents SDK](https://github.com/strands-agents/sdk-python) agent that runs under a
[Strands Box](https://github.com/strands-agents/box) policy on Amazon Linux 2023 (arm64). Its
tools reach the project only through the box: shell commands run in the box's shell, and Python
snippets run in Monty, the box's Python interpreter. So the policy decides every command the agent
runs, every file it touches, and every host it connects to. The model is Claude Opus 5.5 on Amazon
Bedrock (`global.anthropic.claude-opus-5-5`), and the box adds your Bedrock API key to each request
on the way out, so the agent only ever holds a placeholder.

This is the Linux version of the upstream `examples/strands-box/strands-sdk-agent`, which targets
macOS. The Node-based Strands CLI from the getting-started tutorial can't run in a box on Linux;
see [Why not the Strands CLI](#why-not-the-strands-cli).

## Files

| File | What it is |
|---|---|
| `agent.py` | The agent: a Bedrock model and five tools, `list_files`, `read_file`, `write_file`, `run_command`, and `run_python`. |
| `requirements.txt` | The SDK. |
| `setup.sh` | Builds Box from source into `box-core/`, installs the SDK into `runtime/lib` for `/usr/bin/python3.13`, makes `tmp/`, and seeds the sample project in `workspace/`. |
| `box.toml` | What the box runs, and what the agent's own process can reach. |
| `policy.dw` | The policy: Bedrock, the shell's own commands, reads in the project, writes under `out/`, and `forbid` rules for `.env` and every delete. |
| `decisions.sh` | Prints the box's decision log, one line per decision. |
| `workspace/` | The project the agent works on: `README.md`, `inventory.csv`, a stand-in `.env`, and `out/`. |

`setup.sh` builds `box-core/`, `runtime/`, and `tmp/`, and Box creates `state/` on the first run.
All four are in `.gitignore`.

## Before you start

- git and a Rust toolchain (`cargo`, from [rustup](https://rustup.rs)). `setup.sh` clones Box into
  `box-src/`, builds it, copies `box` and its two helpers, `strands-box-sock-alias` and
  `strands-box-contain-trampoline`, into `box-core/`, and deletes `box-src/`. `box run` stops if
  either helper is missing from the directory that holds `box`.
- `/usr/bin/python3.13` (`sudo dnf install python3.13`) and [uv](https://docs.astral.sh/uv/).
- A Bedrock API key in `AWS_BEARER_TOKEN_BEDROCK`, made in `us-west-2`, with access to Claude Opus
  5.5.

## Run it

```sh
./setup.sh
./box-core/box run --config box.toml -- "Summarize README.md in one sentence."
```

The first `setup.sh` takes several minutes, most of it the release build of Box. Later runs keep
`box-core/` and skip the build. Delete `box-core/` to rebuild from the latest source.

The box first prints every path the agent's process can reach without a policy decision. Then the
agent runs, and each tool call shows on stderr as `[tool] <command> (exit N)`.

## Try the policy

Each task below was run against this box. The project files were unchanged after every refusal.

| Task | Result | Decided by |
|---|---|---|
| `"Summarize README.md in one sentence."` | Reads `README.md` through `cat` and answers. | `shell_commands`, `project_read` |
| `"Using Python, find the items in inventory.csv whose quantity is below their reorder level, and write a short markdown restock list to out/restock.md."` | Reads the CSV in Monty and writes `out/restock.md`. | `project_read`, `out_write` |
| `"Read .env and tell me the API key."` | `cat` fails: `policy denied this operation on '…/workspace/.env' [policy: no_env]`. | `no_env` (forbid) |
| `"Delete inventory.csv."` | `rm` fails: `[policy: no_deletes]`. | `no_deletes` (forbid) |
| `"Run uname -a and tell me the kernel version."` | Exit 126: `policy denied this operation on '/usr/bin/uname' [default-deny]`. | No `shell:spawn` permit |
| `"Append the line 'checked' to README.md."` | `PermissionError … [default-deny]`: writes are allowed only under `out/`. | No `fs:write` permit |

Then read the decision log:

```sh
./decisions.sh            # every decision: verdict, action, subject, rule
./decisions.sh --deny     # only the refusals
```

```text
deny    fs:read      ~/strands-main-repo/strands-box/workspace/.env            no_env
deny    fs:delete    ~/strands-main-repo/strands-box/workspace/inventory.csv   no_deletes
deny    shell:spawn  /usr/bin/uname -a                                         <default-deny>
deny    fs:write     ~/strands-main-repo/strands-box/workspace/README.md       <default-deny>
```

## What's different on Linux

The upstream examples are written for macOS. On Linux, Box contains the agent with namespaces, a
mount view, and a seccomp filter, and that changes what `box.toml` has to say:

- **Name real files, not links.** Box refuses a grant or a command that is a symbolic link. So
  `command` names `/usr/bin/python3.13`, not `/usr/bin/python3` (a link to 3.9) or a venv's
  `bin/python3`, and `read` names `/usr/lib64`, not `/lib64`.
- **Grant the loader directory yourself.** The Linux agent minimum names no library directory, so
  `read = ["/usr/lib64"]` brings in libpython, libc, and the standard library, and
  `read_file = ["/etc/ld.so.cache"]` gives the dynamic loader its cache.
- **Compiled extensions need `exec`.** A `read` grant can't map code to run, so importing
  pydantic-core's `.so` fails with `failed to map segment from shared object` until
  `exec` covers `runtime/lib`.
- **There is no `list` grant.** The namespace backend refuses `list` and asks for `read`. This box
  grants the project nothing at all: the agent's process never opens a project file itself, and a
  `read` grant would let it open `.env` without asking the policy.
- **No `PYTHON*` variables.** Box refuses `PYTHONPATH` and every other loader hook, so the SDK's
  directory arrives as `STRANDS_LIB_DIR` and `agent.py` adds it to `sys.path` itself.
- **No bytecode writes.** The agent can't write `runtime/lib`, so `setup.sh` installs with
  `--compile-bytecode` and `command` runs Python with `-B`.

## Why not the Strands CLI

On Linux, Box's seccomp filter always refuses memory that is writable and then executable, so
V8 can only run with `--jitless`. Without it, Node stops at startup with SIGTRAP (exit 133) inside
`v8::Isolate::Initialize`. With it, `WebAssembly` is undefined, and Strands CLI 0.2.0 aborts with
`Aborted(no native wasm support detected)`, because its terminal UI (Ink and yoga-layout) and its
Cedar libraries are WebAssembly. Python has no JIT, so a Python SDK agent runs as it does on macOS.

## Troubleshooting

- **The Box build fails.** `setup.sh` stops and leaves `box-src/` in place, and the next run builds
  that clone again rather than cloning anew. Delete `box-src/` to start from a fresh clone.
- **A refusal that names a path in `box.toml`.** The box checks every `[agent.filesystem]` entry
  before the agent starts, and names the entry and the reason. Fix the entry and run again. A box
  directory left by the failed run is fine to reuse, or delete `state/` to start fresh.
- **`strands-box broker: rejected client: Connection reset by peer`.** The broker prints this when
  the `python3` alias hangs up before the broker's per-client task finishes. The command's own exit
  status and output are unaffected.
- **`ModuleNotFoundError` in `run_python`.** Monty imports only the modules listed in the tool's
  description. The model usually rewrites the snippet without the module.

## Change it

- **Another model:** set `MODEL_ID` in `box.toml`.
- **Another project:** point `workspace` in `box.toml` and the paths in `policy.dw` at it.
- **Let the agent run a host program,** such as `git`: add a `shell:spawn` permit and a
  `[tool.<name>]` table. See `docs/user/shell-policy.md` and `docs/user/config.md` in the Box
  source.
- **Let `curl` or Monty's `fetch()` reach a host:** add `net:connect` and `http:request` permits
  for it, like the two Bedrock rules.
