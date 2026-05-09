# Rust Converter API Reference

## Binary

- **Name**: `skill_rust_converter`
- **Location**: `scripts/skill_rust_converter`
- **Interface**: Reads JSON from stdin, writes JSON to stdout

## Input Schema

| Field | Type   | Required | Description                         |
|-------|--------|----------|-------------------------------------|
| value | float  | yes      | The numeric value to convert (must be >= 0) |
| from  | string | yes      | Source unit (see supported units)   |
| to    | string | yes      | Target unit (see supported units)   |

## Supported Units

| Unit       | JSON value     | Abbreviation |
|------------|---------------|--------------|
| Meter      | `meter`       | m            |
| Kilometer  | `kilometer`   | km           |
| Centimeter | `centimeter`  | cm           |
| Millimeter | `millimeter`  | mm           |
| Mile       | `mile`        | mi           |
| Yard       | `yard`        | yd           |
| Foot       | `foot`        | ft           |
| Inch       | `inch`        | in           |

## Conversion Method

All conversions use meters as the intermediate unit:
1. Convert source value to meters
2. Convert meters to target unit

## Output Schema

| Field     | Type           | Description                              |
|-----------|----------------|------------------------------------------|
| success   | boolean        | Whether the conversion succeeded         |
| result    | float | null   | The converted value (on success)         |
| from_unit | string | null  | Abbreviation of the source unit          |
| to_unit   | string | null  | Abbreviation of the target unit          |
| error     | string | null  | Error message (on failure)               |

## Error Cases

- Invalid JSON input
- Negative value
- Unknown unit name

## Examples

```json
// 10 kilometers to miles
{"value": 10, "from": "kilometer", "to": "mile"}
// -> {"success": true, "result": 6.21371, "from_unit": "km", "to_unit": "mi", "error": null}

// 6 feet to meters
{"value": 6, "from": "foot", "to": "meter"}
// -> {"success": true, "result": 1.8288, "from_unit": "ft", "to_unit": "m", "error": null}

// 12 inches to centimeters
{"value": 12, "from": "inch", "to": "centimeter"}
// -> {"success": true, "result": 30.48, "from_unit": "in", "to_unit": "cm", "error": null}
```
