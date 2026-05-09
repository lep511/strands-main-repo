---
name: rust-converter
description: Length unit converter powered by a Rust binary. Converts between metric (km, m, cm, mm) and imperial (mi, yd, ft, in) units.
when_to_use: When the user asks to convert length or distance units, e.g. kilometers to miles, feet to meters, inches to centimeters.
argument-hint: [conversion-json]
allowed-tools: Bash(echo * | ${CLAUDE_SKILL_DIR}/scripts/skill_rust_converter) Read
---

## Binary check

!`test -x ${CLAUDE_SKILL_DIR}/scripts/skill_rust_converter && echo "Binary ready" || echo "ERROR: binary not found"`

## Usage

Pipe JSON to the binary via stdin:

```bash
echo '{"value": 10, "from": "kilometer", "to": "mile"}' | ${CLAUDE_SKILL_DIR}/scripts/skill_rust_converter
```

## Supported units

| Unit | JSON value |
|------|-----------|
| Meter | `meter` |
| Kilometer | `kilometer` |
| Centimeter | `centimeter` |
| Millimeter | `millimeter` |
| Mile | `mile` |
| Yard | `yard` |
| Foot | `foot` |
| Inch | `inch` |

## Response

```json
{"success": true, "result": 6.21371, "from_unit": "km", "to_unit": "mi", "error": null}
```

## Instructions

1. Identify the value, source unit, and target unit from the user's request.
2. Build the JSON input with `value`, `from`, and `to` fields.
3. Run: `echo '<json>' | ${CLAUDE_SKILL_DIR}/scripts/skill_rust_converter`
4. Present the result clearly with both units.

For full API details, see [references/API.md](references/API.md).
