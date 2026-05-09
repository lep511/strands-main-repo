#!/usr/bin/env bash
# Builds the Rust financial calculator and copies the binary
# into the skill's scripts/ directory so the agent can execute it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../../skills/rust-calculator" && pwd)"

echo "Building rust_calculator in release mode..."
cargo build --release --manifest-path "$SCRIPT_DIR/Cargo.toml"

echo "Copying binary to skill scripts directory..."
cp "$SCRIPT_DIR/target/release/rust_calculator" "$SKILL_DIR/scripts/skill_rust_calculator"
chmod +x "$SKILL_DIR/scripts/skill_rust_calculator"

echo "Done. Binary available at: $SKILL_DIR/scripts/skill_rust_calculator"
