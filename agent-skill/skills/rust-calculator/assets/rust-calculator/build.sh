#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cargo build --release --manifest-path "$SCRIPT_DIR/Cargo.toml"

cp "$SCRIPT_DIR/target/release/rust_calculator" "$SKILL_ROOT/scripts/skill_rust_calculator"
chmod +x "$SKILL_ROOT/scripts/skill_rust_calculator"

rm -rf "$SCRIPT_DIR/target"
