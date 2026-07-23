# Rust MicroVM on AWS Lambda

A Rust HTTP server running on AWS Lambda MicroVMs using [Axum](https://github.com/tokio-rs/axum). Unlike traditional Lambda functions, this runs as a long-lived process inside a Firecracker microVM with snapshot-based resume, suspend/resume lifecycle, and a dedicated HTTPS endpoint.

## Architecture

```
                     Internet
                        │
                        │ HTTPS (puertos 8080 / 8081)
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Lambda MicroVM                             │
│                                                                     │
│  ┌───────────────────┐   ┌───────────────────┐   ┌────────────────┐ │
│  │     REST API      │   │    MCP Server     │   │ Hooks Server   │ │
│  │  (Axum :8080)     │   │   (rmcp :8081)    │   │ (Axum :9000)   │ │
│  ├───────────────────┤   ├───────────────────┤   ├────────────────┤ │
│  │ GET  /            │   │ POST /mcp         │   │ GET  /ready    │ │
│  │ GET  /health      │   │  • get_weather    │   │ POST /validate │ │
│  │ GET  /memory      │   │  • get_hourly...  │   │ POST /run      │ │
│  │ GET  /weather     │   │                   │   │ POST /resume   │ │
│  │                   │   │                   │   │ POST /suspend  │ │
│  │                   │   │                   │   │ POST /terminate│ │
│  └───────────────────┘   └───────────────────┘   └────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

- **Port 8080** - REST API server exposed to clients via the MicroVM endpoint.
- **Port 8081** - MCP server (Streamable HTTP) for AI agent tool integration.
- **Port 9000** - Lifecycle hooks server called internally by the Lambda platform.

## Prerequisites

- AWS CLI v2 configured with credentials
- Rust toolchain (for local development)
- `jq` (used by scripts)

## Quick Start

```bash
# 1. Create IAM roles (only needed once)
./setup-iam.sh

# 2. Wait ~10 seconds for IAM propagation, then deploy
./deploy.sh

# 3. Once the image state is CREATED, run a MicroVM
./run.sh

# 4. Run the full integration test suite
./test.sh
```

## Project Structure

```
microvm-rust/
├── src/
│   ├── lib.rs         # Public library crate: exports types and handlers for tests
│   ├── main.rs        # Binary entrypoint: REST API + MCP server + hooks (3 ports)
│   ├── mcp.rs         # MCP server: WeatherMcpServer with get_weather and get_hourly_forecast tools
│   ├── mcp_server.rs  # Standalone MCP binary (stdio transport, for local/CLI use)
│   ├── hooks.rs       # Lifecycle hooks: ready, validate, run, resume, suspend, terminate
│   └── weather.rs     # Open-Meteo API client and REST weather endpoint handler
├── tests/
│   ├── health_test.rs # Integration tests for GET /health
│   ├── hooks_test.rs  # Integration tests for all lifecycle hooks
│   └── weather_test.rs# Integration tests for GET /weather (calls Open-Meteo)
├── Cargo.toml         # Dependencies: axum, tokio, serde, reqwest, rmcp, schemars, tracing
├── Cargo.lock
├── Dockerfile         # Multi-stage build on public.ecr.aws/lambda/microvms:al2023-minimal
├── setup-iam.sh       # Creates MicroVMBuildRole and MicroVMExecutionRole
├── deploy.sh          # Packages, uploads to S3, and creates the MicroVM image
├── run.sh             # Launches a MicroVM and prints auth/curl instructions
└── test.sh            # Full integration test on a live MicroVM (REST + MCP + lifecycle)
```

## Scripts

### setup-iam.sh

Creates the two IAM roles required by Lambda MicroVMs:

| Role | Purpose | Permissions |
|------|---------|-------------|
| `MicroVMBuildRole` | Assumed during image build | S3 read on artifact bucket, CloudWatch Logs |
| `MicroVMExecutionRole` | Assumed at runtime by the MicroVM | CloudWatch Logs |

Both roles include `aws:SourceAccount` condition to prevent confused deputy attacks.

### deploy.sh

1. Checks if the S3 artifact bucket exists (prompts to create if not)
2. Zips the project (Dockerfile, Cargo.toml, Cargo.lock, src/)
3. Uploads to S3
4. If the image already exists, creates a new version (`update-microvm-image`)
5. If it's the first deploy, creates the image (`create-microvm-image`)

### run.sh

Launches a MicroVM from the built image and prints the `curl` command to call it.

By default uses the latest active image version. Accepts an optional override: `./run.sh 1.0`

### test.sh

By default uses the latest active image version. Accepts an optional override: `./test.sh 1.0`

Runs a full integration test covering:

1. MicroVM creation
2. Readiness check (polling until responsive)
3. `GET /` - verifies message and instance ID
4. `GET /health` - verifies running status
5. `GET /memory` - verifies memory info response
6. `GET /weather` - hourly, current, daily, fahrenheit, error handling
7. MCP server initialize (port 8081)
8. MCP tools/list - verifies both tools available
9. MCP tools/call - calls get_weather and validates response
10. Explicit suspend and state verification
11. Explicit resume and response verification
12. Auto-resume via ingress traffic
13. Termination and cleanup

Automatically terminates the MicroVM on exit (even on failure).

## Testing

The project uses Cargo's standard testing conventions with integration tests in the `tests/` directory.

```bash
# Run all tests
cargo test

# Run a specific test file
cargo test --test health_test
cargo test --test hooks_test
cargo test --test weather_test

# Run a single test by name
cargo test weather_valid_request_returns_200

# Run with output (useful for debugging)
cargo test -- --nocapture
```

### Test Architecture

| File | Tests | What it covers |
|------|-------|----------------|
| `tests/health_test.rs` | 3 | HTTP 200, initial state, running state with microvm_id |
| `tests/hooks_test.rs` | 8 | Each hook individually + full lifecycle sequence |
| `tests/weather_test.rs` | 8 | Missing/invalid params, hourly, current, daily, fahrenheit, forecast_days |

Tests use `tower::ServiceExt::oneshot` to invoke Axum handlers directly without starting a real TCP server. The weather tests make real HTTP calls to the Open-Meteo API to validate end-to-end behavior.

The crate is split into `lib.rs` (public API) and `main.rs` (binary) following Cargo best practices, which allows integration tests to import types and handlers as an external dependency.

### Live Integration Test

For end-to-end testing against a deployed MicroVM (lifecycle, networking, auth tokens):

```bash
./test.sh
```

This deploys a real MicroVM and tests all endpoints plus suspend/resume/auto-resume/terminate.

## Endpoints

### GET /

Returns a hello message with the MicroVM instance ID.

```json
{
  "message": "Hello from Rust MicroVM!",
  "instance_id": "microvm-251b394f-f8aa-3b8a-8e51-26018f15e96e"
}
```

### GET /health

Returns the current application state.

```json
{
  "status": "running",
  "microvm_id": "microvm-251b394f-f8aa-3b8a-8e51-26018f15e96e"
}
```

### GET /memory

Returns system memory information from the MicroVM.

```json
{
  "total_kb": 1048576,
  "available_kb": 812032,
  "used_kb": 236544,
  "usage_percent": 22.56
}
```

| Field | Description |
|-------|-------------|
| `total_kb` | Total physical memory in KB |
| `available_kb` | Available memory in KB |
| `used_kb` | Used memory in KB (total - available) |
| `usage_percent` | Memory usage as a percentage |

### GET /weather

Proxies weather data from the [Open-Meteo API](https://open-meteo.com/en/docs). Requires `latitude` and `longitude` query parameters.

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `latitude` | Yes | - | WGS84 latitude (-90 to 90) |
| `longitude` | Yes | - | WGS84 longitude (-180 to 180) |
| `hourly` | No | `temperature_2m` | Comma-separated hourly variables |
| `daily` | No | - | Comma-separated daily variables (requires `timezone`) |
| `current` | No | - | Comma-separated current condition variables |
| `temperature_unit` | No | `celsius` | `celsius` or `fahrenheit` |
| `wind_speed_unit` | No | `kmh` | `kmh`, `ms`, `mph`, or `kn` |
| `timezone` | No | - | Timezone name (e.g. `auto`, `America/New_York`) |
| `forecast_days` | No | 7 | Number of forecast days (0-16) |

**Examples:**

```bash
# Hourly temperature for Berlin (default)
curl "<endpoint>/weather?latitude=52.52&longitude=13.41"

# Current weather for New York
curl "<endpoint>/weather?latitude=40.71&longitude=-74.01&current=temperature_2m,wind_speed_10m&timezone=auto"

# 3-day forecast with multiple hourly variables for Tokyo
curl "<endpoint>/weather?latitude=35.68&longitude=139.69&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m&forecast_days=3"

# Daily min/max temperature and precipitation for Madrid
curl "<endpoint>/weather?latitude=40.42&longitude=-3.70&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"

# Temperature in Fahrenheit for Miami
curl "<endpoint>/weather?latitude=25.76&longitude=-80.19&current=temperature_2m,apparent_temperature&temperature_unit=fahrenheit&timezone=auto"
```

**Response (current weather example):**

```json
{
  "latitude": 40.710335,
  "longitude": -73.99308,
  "elevation": 51.0,
  "generationtime_ms": 0.05,
  "utc_offset_seconds": -14400,
  "timezone": "America/New_York",
  "timezone_abbreviation": "EDT",
  "current": {
    "time": "2026-07-21T14:00",
    "interval": 900,
    "temperature_2m": 28.2,
    "wind_speed_10m": 19.2
  },
  "current_units": {
    "time": "iso8601",
    "interval": "seconds",
    "temperature_2m": "°C",
    "wind_speed_10m": "km/h"
  }
}
```

**Available hourly variables (most common):**

`temperature_2m`, `relative_humidity_2m`, `dew_point_2m`, `apparent_temperature`, `precipitation`, `rain`, `snowfall`, `snow_depth`, `weather_code`, `cloud_cover`, `wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m`, `visibility`, `pressure_msl`, `surface_pressure`

**Available daily variables:**

`temperature_2m_max`, `temperature_2m_min`, `precipitation_sum`, `rain_sum`, `snowfall_sum`, `precipitation_probability_max`, `weather_code`, `sunrise`, `sunset`, `wind_speed_10m_max`, `wind_gusts_10m_max`, `uv_index_max`

**Error response:**

```json
{
  "error": true,
  "reason": "Open-Meteo API error (400 Bad Request): ..."
}
```

## MCP Server (Port 8081)

The MicroVM also exposes a [Model Context Protocol](https://modelcontextprotocol.io/) server on port 8081 using Streamable HTTP transport. This allows AI agents and MCP clients to invoke weather tools directly.

**Endpoint:** `POST /mcp` on port 8081

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `get_weather` | Current conditions + daily forecast for a location |
| `get_hourly_forecast` | Hour-by-hour temperature, humidity, wind, and conditions |

### Connecting from a MCP Client

```bash
# Get auth token for port 8081
TOKEN=$(aws lambda-microvms create-microvm-auth-token \
  --microvm-identifier microvm-... \
  --expiration-in-minutes 30 \
  --allowed-ports '[{"port":8081}]' \
  --query 'authToken."X-aws-proxy-auth"' --output text)

# Initialize MCP session
curl -X POST "https://<endpoint>/mcp" \
  -H "X-aws-proxy-auth: $TOKEN" \
  -H "X-aws-proxy-port: 8081" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"my-client","version":"1.0"}}}'

# Call a tool
curl -X POST "https://<endpoint>/mcp" \
  -H "X-aws-proxy-auth: $TOKEN" \
  -H "X-aws-proxy-port: 8081" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_weather","arguments":{"latitude":52.52,"longitude":13.41}}}'
```

### Standalone MCP Server (stdio)

A standalone binary is also available for local use with Claude Desktop or other stdio-based MCP clients:

```bash
cargo build --release --bin weather-mcp
```

Configure in Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "weather": {
      "command": "/path/to/weather-mcp"
    }
  }
}
```

## Lifecycle Hooks

The hooks server listens on port 9000 at the path prefix `/aws/lambda-microvms/runtime/v1/`.

| Hook | When | What it does |
|------|------|--------------|
| `/ready` | Image build, before snapshot | Signals the app is fully initialized |
| `/validate` | After snapshot, on test run | Confirms the snapshot is valid |
| `/run` | After MicroVM starts from snapshot | Receives `runHookPayload` with `microvmId`, generates per-instance entropy |
| `/resume` | After SUSPENDED to RUNNING | Updates state to running |
| `/suspend` | Before RUNNING to SUSPENDED | Updates state to suspended |
| `/terminate` | Before termination | Updates state to terminating |

## Snapshot Safety

This project follows MicroVM snapshot best practices:

- Uses `rand::OsRng` (backed by `getrandom`) for entropy, which is safe across snapshot resume since the kernel reseeds on restore.
- Per-instance state is generated in the `/run` hook (post-snapshot), not at build time.
- No TCP connections are established during build that would be invalid after resume.

## Deploying a New Version

```bash
# Update your code, then:
aws lambda-microvms update-microvm-image \
  --image-identifier arn:aws:lambda:us-east-1:<account>:microvm-image:microvm-rust-app \
  --base-image-arn arn:aws:lambda:us-east-1:aws:microvm-image:al2023-1 \
  --build-role-arn arn:aws:iam::<account>:role/MicroVMBuildRole \
  --code-artifact '{"uri":"s3://<bucket>/microvm-images/microvm-rust-app/artifact.zip"}'
```

## Manual Lifecycle Control

```bash
# Get auth token
TOKEN=$(aws lambda-microvms create-microvm-auth-token \
  --microvm-identifier microvm-... \
  --expiration-in-minutes 30 \
  --allowed-ports '[{"port":8080}]' \
  --query 'authToken."X-aws-proxy-auth"' --output text)

# Call the endpoint
curl "https://<endpoint>/" \
  -H "X-aws-proxy-auth: $TOKEN" \
  -H "X-aws-proxy-port: 8080"

# Suspend / Resume / Terminate
aws lambda-microvms suspend-microvm   --microvm-identifier microvm-...
aws lambda-microvms resume-microvm    --microvm-identifier microvm-...
aws lambda-microvms terminate-microvm --microvm-identifier microvm-...
```

## Key Differences from Traditional Lambda

| | Lambda Function | Lambda MicroVM |
|---|---|---|
| Runtime | Event handler invoked per request | Long-lived HTTP server |
| Max duration | 15 minutes | 8 hours |
| State | Stateless between invocations | In-memory state preserved across suspend/resume |
| Networking | No inbound connections | Dedicated HTTPS endpoint with port routing |
| Isolation | Firecracker microVM per execution env | Firecracker microVM per instance |
| Scaling | Automatic per-request | Explicit RunMicrovm calls |
| Cold start | Function init on cold start | Snapshot resume (near-instant) |
