#!/usr/bin/env bash
# Build (the first time) and run dogwood-server, the Dogwood Local Engine daemon
# that local_engine_chat.py talks to. The server stays in the foreground; stop it
# with Ctrl-C. Its event history is durable, so it survives a restart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_URL="https://github.com/dogwood-policy/dogwood-local-engine.git"
MIN_RUST="1.85"  # the crates use edition 2024

STATE_DIR="${DOGWOOD_DIR:-$HOME/.dogwood-chat}"  # the chat's default --dir
SRC_DIR="${DOGWOOD_SRC:-$HOME/.cache/dogwood-local-engine}"
REBUILD=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dir DIR] [--rebuild]

  --dir DIR   state directory: durable store and sockets (default: $STATE_DIR)
  --rebuild   pull the latest dogwood-local-engine and rebuild before starting

Environment:
  DOGWOOD_DIR         same as --dir
  DOGWOOD_SRC         where the source is cloned (default: $SRC_DIR)
  DOGWOOD_SERVER_BIN  run this dogwood-server binary instead of building one
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) STATE_DIR="${2:?--dir needs a directory}"; shift 2 ;;
    --rebuild) REBUILD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

rust_help() {
  cat >&2 <<EOF
ERROR: $1

dogwood-server is written in Rust: building it needs cargo and rustc ${MIN_RUST} or newer.
Install the toolchain with rustup (https://rustup.rs):

  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  . "\$HOME/.cargo/env"    # or open a new terminal

An older toolchain installed with rustup is upgraded with: rustup update stable
Then run this script again.
EOF
  exit 1
}

require_rust() {
  # rustup installs into ~/.cargo/bin; pick it up even if this shell's PATH lacks it.
  if ! command -v cargo >/dev/null 2>&1 && [ -f "$HOME/.cargo/env" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
  fi
  command -v cargo >/dev/null 2>&1 || rust_help "cargo not found: Rust is not installed."
  command -v rustc >/dev/null 2>&1 || rust_help "rustc not found: the Rust installation is incomplete."

  local version
  version="$(rustc --version | awk '{print $2}')"
  if [ "$(printf '%s\n' "$MIN_RUST" "$version" | sort -V | head -n1)" != "$MIN_RUST" ]; then
    rust_help "rustc $version is too old."
  fi
  echo "==> Using $(cargo --version)"
}

build_server() {
  require_rust
  command -v git >/dev/null 2>&1 || { echo "ERROR: git is required to fetch $REPO_URL" >&2; exit 1; }

  if [ ! -d "$SRC_DIR/.git" ]; then
    echo "==> Cloning $REPO_URL into $SRC_DIR"
    mkdir -p "$(dirname "$SRC_DIR")"
    git clone --depth 1 "$REPO_URL" "$SRC_DIR"
  elif [ "$REBUILD" -eq 1 ]; then
    echo "==> Updating $SRC_DIR"
    git -C "$SRC_DIR" pull --ff-only
  fi

  echo "==> Building dogwood-server (the first build takes a few minutes)"
  cargo build --release -p dogwood-server --manifest-path "$SRC_DIR/Cargo.toml"
}

if [ -n "${DOGWOOD_SERVER_BIN:-}" ]; then
  BIN="$DOGWOOD_SERVER_BIN"
  [ -x "$BIN" ] || { echo "ERROR: DOGWOOD_SERVER_BIN=$BIN is not an executable" >&2; exit 1; }
else
  BIN="$SRC_DIR/target/release/dogwood-server"
  if [ ! -x "$BIN" ] || [ "$REBUILD" -eq 1 ]; then
    build_server
  fi
fi

# A second server on the same directory would fight over the store and sockets.
if "$BIN" --dir "$STATE_DIR" ping >/dev/null 2>&1; then
  echo "==> dogwood-server is already running for $STATE_DIR"
  exit 0
fi

cat <<EOF
==> Starting dogwood-server for $STATE_DIR
    In another terminal, start the chat:
      cd $(dirname "$SCRIPT_DIR") && uv run python dogwood/local_engine_chat.py --dir $STATE_DIR

EOF
exec "$BIN" --dir "$STATE_DIR" run
