#!/bin/sh
# Points box.toml and policy.dw at this directory, builds Box from source into box-core/, installs
# requirements.txt into runtime/lib, beside this file, for the host's Python 3.13, makes tmp/, and
# seeds the sample project in workspace/. The box reads runtime/lib and never writes it.
#
# Why a plain `--target` directory and not a virtual environment: Box refuses a grant or a command
# that is a symbolic link, and a venv's bin/python3 is one. So box.toml runs the real interpreter,
# /usr/bin/python3.13, and agent.py puts runtime/lib on sys.path itself.
set -eu

# -P resolves symbolic links, which Box refuses in a path.
here=$(cd "$(dirname "$0")" && pwd -P)

# box.toml names this directory by its full path, and policy.dw by the form Box shows, with "~" for
# your home. If the directory has moved, point both files at where it is now.
was=$(sed -n 's#^box_dir = "\(.*\)/state"$#\1#p' "$here/box.toml")
was_short=$(sed -n 's#^  context\.input\.path == "\(.*\)/workspace" ||$#\1#p' "$here/policy.dw")
[ -n "$was" ] && [ -n "$was_short" ] || { echo "no path to this directory in box.toml or policy.dw" >&2; exit 1; }
case $here in "$HOME"/*) short="~${here#"$HOME"}" ;; *) short=$here ;; esac
if [ "$was" != "$here" ] || [ "$was_short" != "$short" ]; then
  sed -i "s#$was#$here#g" "$here/box.toml"
  sed -i "s#$was_short#$short#g" "$here/policy.dw"
  echo "pointed box.toml and policy.dw at $here"
fi

# Box: the `box` binary, and the two helpers it expects in the same directory, sock-alias and
# contain-trampoline. The clone is deleted once the binaries are copied out; a clone left by a
# failed build is reused on the next run. An existing box-core/box is kept: delete box-core/ to
# rebuild.
core="$here/box-core"
src="$here/box-src"
if [ ! -x "$core/box" ]; then
  command -v git >/dev/null || { echo "git is not on PATH" >&2; exit 1; }
  command -v cargo >/dev/null || { echo "cargo is not on PATH: see https://rustup.rs" >&2; exit 1; }
  [ -d "$src" ] || git clone --depth 1 https://github.com/strands-agents/box.git "$src"
  # CARGO_TARGET_DIR pins the output to box-src/target, where the copies below look for it.
  CARGO_TARGET_DIR="$src/target" cargo build --release --manifest-path "$src/Cargo.toml" \
    -p strands-box -p strands-box-containment
  mkdir -p "$core"
  cp "$src/target/release/strands-box" "$core/box"
  cp "$src/target/release/strands-box-sock-alias" \
    "$src/target/release/strands-box-contain-trampoline" "$core/"
  rm -rf "$src"
  echo "built Box into $core"
fi

python=${PYTHON:-/usr/bin/python3.13}
[ -x "$python" ] || { echo "no Python at $python: run 'sudo dnf install python3.13', or set PYTHON" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is not on PATH: see https://docs.astral.sh/uv/" >&2; exit 1; }

# --compile-bytecode writes the .pyc files now, because the agent runs with -B and can't write them.
uv pip install --quiet --python "$python" --target "$here/runtime/lib" --compile-bytecode \
  -r "$here/requirements.txt"
mkdir -p "$here/tmp"

# The sample project the agent works on. Existing files are left alone.
ws="$here/workspace"
mkdir -p "$ws/out"
[ -f "$ws/README.md" ] || cat > "$ws/README.md" <<'EOF'
# Inventory service

A small service that tracks stock for a hardware shop. `inventory.csv` holds the current counts,
one row per item. Restock any item whose quantity falls below its reorder level.
EOF
[ -f "$ws/inventory.csv" ] || cat > "$ws/inventory.csv" <<'EOF'
sku,item,quantity,reorder_level
H-100,hammer,14,10
S-220,screwdriver set,3,8
W-310,wrench,22,10
T-405,tape measure,6,6
P-512,pliers,0,5
EOF
# A stand-in secret, so the policy's no_env rule has something to refuse.
[ -f "$ws/.env" ] || printf 'INVENTORY_API_KEY=not-a-real-key-just-a-demo\n' > "$ws/.env"

echo "installed the Strands Agents SDK into $here/runtime/lib for $("$python" --version)"
echo "sample project in $ws"
