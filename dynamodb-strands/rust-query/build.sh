#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/../agent/skills/dynamodb-query" && pwd)"

echo "Building dynamodb_query in release mode..."
cargo build --release --manifest-path "$SCRIPT_DIR/Cargo.toml"

echo "Copying binary to skill scripts directory..."
cp "$SCRIPT_DIR/target/release/dynamodb_query" "$SKILL_DIR/scripts/skill_dynamodb_query"
chmod +x "$SKILL_DIR/scripts/skill_dynamodb_query"

echo "Done. Binary available at: $SKILL_DIR/scripts/skill_dynamodb_query"
