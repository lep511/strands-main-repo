#!/usr/bin/env bash
# Builds the Rust length converter and copies the binary
# into the skill's scripts/ directory so the agent can execute it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../../skills/rust-converter" && pwd)"

echo "Building rust_converter in release mode..."
cargo build --release --manifest-path "$SCRIPT_DIR/Cargo.toml"

echo "Copying binary to skill scripts directory..."
cp "$SCRIPT_DIR/target/release/rust_converter" "$SKILL_DIR/scripts/skill_rust_converter"
chmod +x "$SKILL_DIR/scripts/skill_rust_converter"

echo "Done. Binary available at: $SKILL_DIR/scripts/skill_rust_converter"
