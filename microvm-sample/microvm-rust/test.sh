#!/bin/bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_NAME="microvm-rust-app"
IMAGE_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:microvm-image:${IMAGE_NAME}"
EXECUTION_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/MicroVMExecutionRole"
IMAGE_VERSION="${1:-$(aws lambda-microvms get-microvm-image \
  --image-identifier "${IMAGE_ARN}" \
  --query 'latestActiveImageVersion' --output text 2>/dev/null || echo "1.0")}"

PASSED=0
FAILED=0

pass() { echo "  [PASS] $1"; PASSED=$((PASSED + 1)); }
fail() { echo "  [FAIL] $1"; FAILED=$((FAILED + 1)); }

cleanup() {
  if [[ -n "${MICROVM_ID:-}" ]]; then
    echo ""
    echo "==> Cleaning up: terminating MicroVM ${MICROVM_ID}..."
    aws lambda-microvms terminate-microvm --microvm-identifier "${MICROVM_ID}" &>/dev/null || true
  fi
}
trap cleanup EXIT

echo "============================================"
echo " Lambda MicroVM Integration Test"
echo "============================================"
echo ""
echo "  Image:   ${IMAGE_ARN}"
echo "  Version: ${IMAGE_VERSION}"
echo ""

# --- Step 1: Run the MicroVM ---
echo "==> Step 1: Running MicroVM..."
RUN_RESPONSE=$(aws lambda-microvms run-microvm \
  --image-identifier "${IMAGE_ARN}" \
  --image-version "${IMAGE_VERSION}" \
  --execution-role-arn "${EXECUTION_ROLE_ARN}" \
  --idle-policy '{"maxIdleDurationSeconds":900,"suspendedDurationSeconds":300,"autoResumeEnabled":true}' \
  --maximum-duration-in-seconds 28800)

MICROVM_ID=$(echo "${RUN_RESPONSE}" | jq -r '.microvmId')
ENDPOINT=$(echo "${RUN_RESPONSE}" | jq -r '.endpoint')

if [[ -n "${MICROVM_ID}" && "${MICROVM_ID}" != "null" ]]; then
  pass "MicroVM created: ${MICROVM_ID}"
else
  fail "Failed to create MicroVM"
  exit 1
fi

echo "  Endpoint: ${ENDPOINT}"
echo ""

# --- Step 2: Wait for MicroVM to be ready ---
echo "==> Step 2: Waiting for MicroVM to be ready..."
MAX_WAIT=60
ELAPSED=0
while [[ ${ELAPSED} -lt ${MAX_WAIT} ]]; do
  TOKEN=$(aws lambda-microvms create-microvm-auth-token \
    --microvm-identifier "${MICROVM_ID}" \
    --expiration-in-minutes 5 \
    --allowed-ports '[{"port":8080}]' \
    --query 'authToken."X-aws-proxy-auth"' --output text 2>/dev/null) || true

  if [[ -n "${TOKEN}" && "${TOKEN}" != "None" ]]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
      "https://${ENDPOINT}/health" \
      -H "X-aws-proxy-auth: ${TOKEN}" \
      -H "X-aws-proxy-port: 8080" 2>/dev/null) || true
    if [[ "${HTTP_CODE}" == "200" ]]; then
      break
    fi
  fi

  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

if [[ ${ELAPSED} -lt ${MAX_WAIT} ]]; then
  pass "MicroVM ready in ${ELAPSED}s"
else
  fail "MicroVM did not become ready within ${MAX_WAIT}s"
  exit 1
fi
echo ""

# --- Step 3: Test root endpoint ---
echo "==> Step 3: Testing GET / ..."
RESPONSE=$(curl -s "https://${ENDPOINT}/" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

MESSAGE=$(echo "${RESPONSE}" | jq -r '.message' 2>/dev/null)
INSTANCE_ID=$(echo "${RESPONSE}" | jq -r '.instance_id' 2>/dev/null)

if [[ "${MESSAGE}" == "Hello from Rust MicroVM!" ]]; then
  pass "Root endpoint returned correct message"
else
  fail "Root endpoint returned unexpected message: ${MESSAGE}"
fi

if [[ -n "${INSTANCE_ID}" && "${INSTANCE_ID}" != "null" ]]; then
  pass "Root endpoint returned instance_id: ${INSTANCE_ID}"
else
  fail "Root endpoint missing instance_id"
fi
echo ""

# --- Step 4: Test health endpoint ---
echo "==> Step 4: Testing GET /health ..."
HEALTH_RESPONSE=$(curl -s "https://${ENDPOINT}/health" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

STATUS=$(echo "${HEALTH_RESPONSE}" | jq -r '.status' 2>/dev/null)

if [[ "${STATUS}" == "running" ]]; then
  pass "Health endpoint reports status: running"
else
  fail "Health endpoint unexpected status: ${STATUS}"
fi
echo ""

# --- Step 5: Test memory endpoint ---
echo "==> Step 5: Testing GET /memory ..."
MEMORY_RESPONSE=$(curl -s "https://${ENDPOINT}/memory" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

MEM_TOTAL=$(echo "${MEMORY_RESPONSE}" | jq -r '.total_kb' 2>/dev/null)
MEM_AVAILABLE=$(echo "${MEMORY_RESPONSE}" | jq -r '.available_kb' 2>/dev/null)
MEM_USED=$(echo "${MEMORY_RESPONSE}" | jq -r '.used_kb' 2>/dev/null)
MEM_PERCENT=$(echo "${MEMORY_RESPONSE}" | jq -r '.usage_percent' 2>/dev/null)

if [[ "${MEM_TOTAL}" != "null" && -n "${MEM_TOTAL}" && "${MEM_TOTAL}" -gt 0 ]]; then
  pass "Memory endpoint returned total_kb: ${MEM_TOTAL}"
else
  fail "Memory endpoint missing or invalid total_kb"
fi

if [[ "${MEM_AVAILABLE}" != "null" && -n "${MEM_AVAILABLE}" && "${MEM_AVAILABLE}" -gt 0 ]]; then
  pass "Memory endpoint returned available_kb: ${MEM_AVAILABLE}"
else
  fail "Memory endpoint missing or invalid available_kb"
fi

if [[ "${MEM_USED}" != "null" && -n "${MEM_USED}" ]]; then
  pass "Memory endpoint returned used_kb: ${MEM_USED}"
else
  fail "Memory endpoint missing used_kb"
fi

if [[ "${MEM_PERCENT}" != "null" && -n "${MEM_PERCENT}" ]]; then
  pass "Memory usage percent: ${MEM_PERCENT}%"
else
  fail "Memory endpoint missing usage_percent"
fi
echo ""

# --- Step 6: Test weather endpoint (basic) ---
echo "==> Step 6: Testing GET /weather (Berlin, hourly temperature)..."
WEATHER_RESPONSE=$(curl -s "https://${ENDPOINT}/weather?latitude=52.52&longitude=13.41" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

W_LAT=$(echo "${WEATHER_RESPONSE}" | jq -r '.latitude' 2>/dev/null)
W_HOURLY_COUNT=$(echo "${WEATHER_RESPONSE}" | jq -r '.hourly.temperature_2m | length' 2>/dev/null)

if [[ "${W_LAT}" != "null" && -n "${W_LAT}" ]]; then
  pass "Weather endpoint returned latitude: ${W_LAT}"
else
  fail "Weather endpoint missing latitude"
fi

if [[ "${W_HOURLY_COUNT}" -ge 24 ]]; then
  pass "Weather endpoint returned ${W_HOURLY_COUNT} hourly data points"
else
  fail "Weather endpoint returned insufficient hourly data: ${W_HOURLY_COUNT}"
fi
echo ""

# --- Step 7: Test weather endpoint (current conditions) ---
echo "==> Step 7: Testing GET /weather (New York, current conditions)..."
WEATHER_CURRENT=$(curl -s "https://${ENDPOINT}/weather?latitude=40.71&longitude=-74.01&current=temperature_2m,wind_speed_10m&timezone=auto&forecast_days=1" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

CURRENT_TEMP=$(echo "${WEATHER_CURRENT}" | jq -r '.current.temperature_2m' 2>/dev/null)
CURRENT_WIND=$(echo "${WEATHER_CURRENT}" | jq -r '.current.wind_speed_10m' 2>/dev/null)
CURRENT_TZ=$(echo "${WEATHER_CURRENT}" | jq -r '.timezone' 2>/dev/null)

if [[ "${CURRENT_TEMP}" != "null" && -n "${CURRENT_TEMP}" ]]; then
  pass "Current temperature returned: ${CURRENT_TEMP} C"
else
  fail "Current temperature missing"
fi

if [[ "${CURRENT_WIND}" != "null" && -n "${CURRENT_WIND}" ]]; then
  pass "Current wind speed returned: ${CURRENT_WIND} km/h"
else
  fail "Current wind speed missing"
fi

if [[ "${CURRENT_TZ}" == *"America"* ]]; then
  pass "Timezone auto-resolved: ${CURRENT_TZ}"
else
  fail "Timezone not resolved correctly: ${CURRENT_TZ}"
fi
echo ""

# --- Step 8: Test weather endpoint (daily forecast) ---
echo "==> Step 8: Testing GET /weather (Madrid, daily forecast)..."
WEATHER_DAILY=$(curl -s "https://${ENDPOINT}/weather?latitude=40.42&longitude=-3.70&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto&forecast_days=3" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

DAILY_DAYS=$(echo "${WEATHER_DAILY}" | jq -r '.daily.time | length' 2>/dev/null)
DAILY_MAX=$(echo "${WEATHER_DAILY}" | jq -r '.daily.temperature_2m_max[0]' 2>/dev/null)

if [[ "${DAILY_DAYS}" == "3" ]]; then
  pass "Daily forecast returned 3 days"
else
  fail "Daily forecast expected 3 days, got: ${DAILY_DAYS}"
fi

if [[ "${DAILY_MAX}" != "null" && -n "${DAILY_MAX}" ]]; then
  pass "Daily max temperature returned: ${DAILY_MAX} C"
else
  fail "Daily max temperature missing"
fi
echo ""

# --- Step 9: Test weather endpoint (fahrenheit) ---
echo "==> Step 9: Testing GET /weather (temperature unit: fahrenheit)..."
WEATHER_F=$(curl -s "https://${ENDPOINT}/weather?latitude=25.76&longitude=-80.19&current=temperature_2m&temperature_unit=fahrenheit&timezone=auto" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

F_UNIT=$(echo "${WEATHER_F}" | jq -r '.current_units.temperature_2m' 2>/dev/null)
F_TEMP=$(echo "${WEATHER_F}" | jq -r '.current.temperature_2m' 2>/dev/null)

if [[ "${F_UNIT}" == "°F" ]]; then
  pass "Fahrenheit unit confirmed in response"
else
  fail "Expected °F unit, got: ${F_UNIT}"
fi

if [[ "${F_TEMP}" != "null" && -n "${F_TEMP}" ]]; then
  pass "Fahrenheit temperature returned: ${F_TEMP} F"
else
  fail "Fahrenheit temperature missing"
fi
echo ""

# --- Step 10: Test weather endpoint (error handling) ---
echo "==> Step 10: Testing GET /weather (invalid request - missing params)..."
WEATHER_ERR=$(curl -s -o /dev/null -w "%{http_code}" \
  "https://${ENDPOINT}/weather" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080")

if [[ "${WEATHER_ERR}" == "400" || "${WEATHER_ERR}" == "422" ]]; then
  pass "Missing params returns error status: ${WEATHER_ERR}"
else
  fail "Expected 400/422 for missing params, got: ${WEATHER_ERR}"
fi
echo ""

# --- Step 11: Test MCP server (initialize) ---
echo "==> Step 11: Testing MCP server initialize (port 8081)..."
MCP_TOKEN=""
MCP_TOKEN=$(aws lambda-microvms create-microvm-auth-token \
  --microvm-identifier "${MICROVM_ID}" \
  --expiration-in-minutes 5 \
  --allowed-ports '[{"port":8081}]' \
  --query 'authToken."X-aws-proxy-auth"' --output text) || true

if [[ -z "${MCP_TOKEN}" || "${MCP_TOKEN}" == "None" ]]; then
  fail "Could not create MCP auth token for port 8081"
  echo ""
  echo "==> Skipping MCP tests (steps 12-13)..."
  echo ""
else

MCP_INIT=""
MCP_INIT=$(curl -s --max-time 10 -X POST "https://${ENDPOINT}/mcp" \
  -H "X-aws-proxy-auth: ${MCP_TOKEN}" \
  -H "X-aws-proxy-port: 8081" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}') || true

MCP_VERSION=$(echo "${MCP_INIT}" | grep -o '"protocolVersion":"[^"]*"' | head -1 | cut -d'"' -f4)

if [[ "${MCP_VERSION}" == "2025-11-25" ]]; then
  pass "MCP server initialized with protocol version: ${MCP_VERSION}"
else
  fail "MCP server initialization failed, got: ${MCP_INIT:-<timeout>}"
fi
echo ""

# --- Step 12: Test MCP server (list tools) ---
echo "==> Step 12: Testing MCP tools/list..."
MCP_TOOLS=""
MCP_TOOLS=$(curl -s --max-time 10 -X POST "https://${ENDPOINT}/mcp" \
  -H "X-aws-proxy-auth: ${MCP_TOKEN}" \
  -H "X-aws-proxy-port: 8081" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}') || true

HAS_GET_WEATHER=$(echo "${MCP_TOOLS}" | grep -c '"get_weather"' 2>/dev/null || echo "0")
HAS_HOURLY=$(echo "${MCP_TOOLS}" | grep -c '"get_hourly_forecast"' 2>/dev/null || echo "0")

if [[ "${HAS_GET_WEATHER}" -ge 1 ]]; then
  pass "MCP tool 'get_weather' available"
else
  fail "MCP tool 'get_weather' not found"
fi

if [[ "${HAS_HOURLY}" -ge 1 ]]; then
  pass "MCP tool 'get_hourly_forecast' available"
else
  fail "MCP tool 'get_hourly_forecast' not found"
fi
echo ""

# --- Step 13: Test MCP server (call tool) ---
echo "==> Step 13: Testing MCP tools/call (get_weather for Tokyo)..."
MCP_CALL=""
MCP_CALL=$(curl -s --max-time 15 -X POST "https://${ENDPOINT}/mcp" \
  -H "X-aws-proxy-auth: ${MCP_TOKEN}" \
  -H "X-aws-proxy-port: 8081" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_weather","arguments":{"latitude":35.68,"longitude":139.69,"forecast_days":1}}}') || true

HAS_WEATHER_DATA=$(echo "${MCP_CALL}" | grep -c "Current Conditions" 2>/dev/null || echo "0")
HAS_SOURCE=$(echo "${MCP_CALL}" | grep -c "Open-Meteo" 2>/dev/null || echo "0")

if [[ "${HAS_WEATHER_DATA}" -ge 1 ]]; then
  pass "MCP get_weather returned weather data"
else
  fail "MCP get_weather did not return weather data"
fi

if [[ "${HAS_SOURCE}" -ge 1 ]]; then
  pass "MCP response includes Open-Meteo source attribution"
else
  fail "MCP response missing source attribution"
fi
echo ""

fi  # end MCP_TOKEN check

# --- Step 14: Test suspend ---
echo "==> Step 14: Testing suspend..."
aws lambda-microvms suspend-microvm --microvm-identifier "${MICROVM_ID}" &>/dev/null

sleep 5
STATE=$(aws lambda-microvms get-microvm --microvm-identifier "${MICROVM_ID}" \
  --query 'state' --output text 2>/dev/null)

if [[ "${STATE}" == "SUSPENDED" ]]; then
  pass "MicroVM suspended successfully"
else
  fail "Expected SUSPENDED, got: ${STATE}"
fi
echo ""

# --- Step 15: Test resume ---
echo "==> Step 15: Testing resume..."
aws lambda-microvms resume-microvm --microvm-identifier "${MICROVM_ID}" &>/dev/null

sleep 5
TOKEN=$(aws lambda-microvms create-microvm-auth-token \
  --microvm-identifier "${MICROVM_ID}" \
  --expiration-in-minutes 5 \
  --allowed-ports '[{"port":8080}]' \
  --query 'authToken."X-aws-proxy-auth"' --output text)

HEALTH_AFTER_RESUME=$(curl -s "https://${ENDPOINT}/health" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080" 2>/dev/null)

STATUS_AFTER=$(echo "${HEALTH_AFTER_RESUME}" | jq -r '.status' 2>/dev/null)

if [[ "${STATUS_AFTER}" == "running" ]]; then
  pass "MicroVM resumed and responding"
else
  fail "After resume, health status: ${STATUS_AFTER}"
fi
echo ""

# --- Step 16: Test auto-resume via ingress (if suspended again) ---
echo "==> Step 16: Testing auto-resume via ingress..."
aws lambda-microvms suspend-microvm --microvm-identifier "${MICROVM_ID}" &>/dev/null
sleep 5

TOKEN=$(aws lambda-microvms create-microvm-auth-token \
  --microvm-identifier "${MICROVM_ID}" \
  --expiration-in-minutes 5 \
  --allowed-ports '[{"port":8080}]' \
  --query 'authToken."X-aws-proxy-auth"' --output text)

AUTO_RESUME_RESPONSE=$(curl -s --max-time 30 "https://${ENDPOINT}/health" \
  -H "X-aws-proxy-auth: ${TOKEN}" \
  -H "X-aws-proxy-port: 8080" 2>/dev/null) || true

AUTO_STATUS=$(echo "${AUTO_RESUME_RESPONSE}" | jq -r '.status' 2>/dev/null) || true

if [[ "${AUTO_STATUS}" == "running" ]]; then
  pass "Auto-resume via ingress traffic works"
else
  fail "Auto-resume did not work, status: ${AUTO_STATUS}"
fi
echo ""

# --- Step 17: Terminate ---
echo "==> Step 17: Terminating MicroVM..."
aws lambda-microvms terminate-microvm --microvm-identifier "${MICROVM_ID}" &>/dev/null

sleep 3
STATE=$(aws lambda-microvms get-microvm --microvm-identifier "${MICROVM_ID}" \
  --query 'state' --output text 2>/dev/null)

if [[ "${STATE}" == "TERMINATED" || "${STATE}" == "TERMINATING" ]]; then
  pass "MicroVM terminated"
else
  fail "Expected TERMINATED/TERMINATING, got: ${STATE}"
fi

MICROVM_ID=""
echo ""

# --- Summary ---
echo "============================================"
echo " Results: ${PASSED} passed, ${FAILED} failed"
echo "============================================"

if [[ ${FAILED} -gt 0 ]]; then
  exit 1
fi
