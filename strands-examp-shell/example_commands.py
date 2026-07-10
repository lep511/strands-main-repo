"""Strands Shell example: command inventory and shell language features.

Demonstrates text processing (grep, sed, sort, cut, wc), file management,
JSON processing with jq, Lua scripting, pipelines, loops, conditionals,
functions, and here-docs — all running inside a sandboxed shell.
"""

import strands_shell


def main():
    shell = strands_shell.Shell(timeout=30.0)

    # Seed sample data via file I/O
    shell.write_file("/tmp/data/users.csv", b"""id,name,email,role
1,Alice,alice@example.com,admin
2,Bob,bob@example.com,developer
3,Charlie,charlie@example.com,developer
4,Diana,diana@example.com,designer
5,Eve,eve@example.com,admin
""")

    shell.write_file("/tmp/data/logs.txt", b"""2026-07-10 08:01:12 INFO  server started on port 8080
2026-07-10 08:05:33 WARN  high memory usage: 85%
2026-07-10 08:12:45 ERROR connection timeout to database
2026-07-10 08:13:01 INFO  retry connection attempt 1
2026-07-10 08:13:05 INFO  database connection restored
2026-07-10 08:20:00 ERROR disk space critical: /var/log at 95%
2026-07-10 08:25:10 WARN  request latency above threshold: 2.3s
2026-07-10 08:30:00 INFO  health check passed
""")

    shell.write_file("/tmp/data/config.json", b"""{
  "app": "strands-demo",
  "version": "1.2.0",
  "features": {
    "auth": true,
    "cache": true,
    "debug": false
  },
  "endpoints": [
    {"path": "/api/users", "method": "GET", "rate_limit": 100},
    {"path": "/api/posts", "method": "POST", "rate_limit": 50},
    {"path": "/api/health", "method": "GET", "rate_limit": 1000}
  ]
}
""")

    # === Text Processing ===
    print("=" * 60)
    print("=== Text Processing ===")
    print("=" * 60)

    print("\n--- grep: find errors in logs ---")
    result = shell.run("grep ERROR /tmp/data/logs.txt")
    print(result.stdout)

    print("--- grep -c: count warnings and errors ---")
    result = shell.run("grep -c ERROR /tmp/data/logs.txt")
    errors = result.stdout.strip()
    result = shell.run("grep -c WARN /tmp/data/logs.txt")
    warnings = result.stdout.strip()
    print(f"  Errors: {errors}, Warnings: {warnings}")

    print("\n--- sed: extract timestamps from errors ---")
    result = shell.run("grep ERROR /tmp/data/logs.txt | sed 's/ ERROR.*//'")
    print(result.stdout)

    print("--- cut: extract names from CSV ---")
    result = shell.run("tail -n +2 /tmp/data/users.csv | cut -d, -f2")
    print(result.stdout)

    print("--- sort: sort users by role ---")
    result = shell.run("tail -n +2 /tmp/data/users.csv | sort -t, -k4")
    print(result.stdout)

    print("--- wc: line counts ---")
    result = shell.run("wc -l /tmp/data/logs.txt /tmp/data/users.csv")
    print(result.stdout)

    # === JSON Processing with jq ===
    print("=" * 60)
    print("=== JSON Processing (jq) ===")
    print("=" * 60)

    print("\n--- Extract app version ---")
    result = shell.run("cat /tmp/data/config.json | jq '.version'")
    print(f"  Version: {result.stdout.strip()}")

    print("\n--- List endpoint paths ---")
    result = shell.run("cat /tmp/data/config.json | jq '.endpoints[].path'")
    print(result.stdout)

    print("--- Filter endpoints with rate_limit > 50 ---")
    result = shell.run(
        "cat /tmp/data/config.json | jq '[.endpoints[] | select(.rate_limit > 50)]'"
    )
    print(result.stdout)

    print("--- Transform: build summary object ---")
    result = shell.run(
        "cat /tmp/data/config.json | jq '{name: .app, ver: .version, endpoint_count: (.endpoints | length)}'"
    )
    print(result.stdout)

    # === Shell Language Features ===
    print("=" * 60)
    print("=== Shell Language Features ===")
    print("=" * 60)

    print("\n--- for loop: process each user ---")
    result = shell.run("""
for name in $(tail -n +2 /tmp/data/users.csv | cut -d, -f2); do
  echo "Processing user: $name"
done
""")
    print(result.stdout)

    print("--- while loop + conditionals ---")
    result = shell.run("""
errors=$(grep -c ERROR /tmp/data/logs.txt)
warnings=$(grep -c WARN /tmp/data/logs.txt)
total=$((errors + warnings))
if [ $total -gt 3 ]; then
  echo "ALERT: $total issues found ($errors errors, $warnings warnings)"
else
  echo "OK: only $total issues found"
fi
""")
    print(result.stdout)

    print("--- functions ---")
    result = shell.run("""
classify_log() {
  local level=$(echo "$1" | cut -d' ' -f3)
  case $level in
    ERROR) echo "CRITICAL: $1" ;;
    WARN)  echo "ATTENTION: $1" ;;
    *)     echo "OK: $1" ;;
  esac
}

classify_log "2026-07-10 08:12:45 ERROR connection timeout"
classify_log "2026-07-10 08:05:33 WARN high memory"
classify_log "2026-07-10 08:30:00 INFO health check"
""")
    print(result.stdout)

    print("--- here-doc: generate a script ---")
    result = shell.run("""
cat << 'EOF' > /tmp/data/report.sh
#!/bin/sh
echo "=== System Report ==="
echo "Errors: $(grep -c ERROR /tmp/data/logs.txt)"
echo "Warnings: $(grep -c WARN /tmp/data/logs.txt)"
echo "Users: $(tail -n +2 /tmp/data/users.csv | wc -l)"
echo "Admins: $(grep admin /tmp/data/users.csv | wc -l)"
EOF
. /tmp/data/report.sh
""")
    print(result.stdout)

    # === Lua Scripting ===
    print("=" * 60)
    print("=== Lua Scripting ===")
    print("=" * 60)

    print("\n--- Lua: parse CSV and compute stats ---")
    result = shell.run("""lua -e '
local roles = {}
local f = io.open("/tmp/data/users.csv", "r")
f:read("*l")  -- skip header
for line in f:lines() do
  local role = line:match("[^,]+,[^,]+,[^,]+,(.+)")
  roles[role] = (roles[role] or 0) + 1
end
f:close()

print("Role distribution:")
for role, count in pairs(roles) do
  print(string.format("  %-12s %d", role, count))
end
'""")
    print(result.stdout)

    print("--- Lua: analyze log severity ---")
    result = shell.run("""lua -e '
local severity = {INFO=0, WARN=0, ERROR=0}
local f = io.open("/tmp/data/logs.txt", "r")
for line in f:lines() do
  for level, _ in pairs(severity) do
    if line:find(level) then
      severity[level] = severity[level] + 1
    end
  end
end
f:close()

print("Log severity summary:")
print(string.format("  INFO:  %d", severity.INFO))
print(string.format("  WARN:  %d", severity.WARN))
print(string.format("  ERROR: %d", severity.ERROR))

local total = severity.INFO + severity.WARN + severity.ERROR
local error_pct = (severity.ERROR / total) * 100
print(string.format("  Error rate: %.1f%%", error_pct))
'""")
    print(result.stdout)

    # === Pipelines and Redirections ===
    print("=" * 60)
    print("=== Pipelines and Redirections ===")
    print("=" * 60)

    print("\n--- Complex pipeline: developer email list ---")
    result = shell.run(
        "grep developer /tmp/data/users.csv | cut -d, -f2,3 | sed 's/,/ </' | sed 's/$/>/' | sort"
    )
    print(result.stdout)

    print("--- Redirect: build filtered log ---")
    shell.run("grep -v INFO /tmp/data/logs.txt > /tmp/data/alerts.txt")
    result = shell.run("cat /tmp/data/alerts.txt")
    print(result.stdout)

    print("--- Append redirect ---")
    shell.run("echo '---' >> /tmp/data/alerts.txt")
    shell.run("echo 'Generated by strands-shell' >> /tmp/data/alerts.txt")
    result = shell.run("cat /tmp/data/alerts.txt")
    print(result.stdout)

    # === Find and Xargs ===
    print("=" * 60)
    print("=== Find and Xargs ===")
    print("=" * 60)

    shell.run("mkdir -p /tmp/project/src")
    shell.run("mkdir -p /tmp/project/tests")
    shell.write_file("/tmp/project/src/main.py", b"# main\nimport os\n")
    shell.write_file("/tmp/project/src/utils.py", b"# utils\nimport json\n")
    shell.write_file("/tmp/project/tests/test_main.py", b"# test\nimport pytest\n")
    shell.write_file("/tmp/project/README.md", b"# Project\n")

    print("\n--- find: list Python files ---")
    result = shell.run("find /tmp/project -name '*.py' -type f")
    print(result.stdout)

    print("--- find + xargs: count lines in all Python files ---")
    result = shell.run("find /tmp/project -name '*.py' -type f | xargs wc -l")
    print(result.stdout)

    print("--- find + xargs: find files containing 'import' ---")
    result = shell.run("find /tmp/project -name '*.py' -type f | xargs grep -l 'import'")
    print(result.stdout)

    print("Done.")


if __name__ == "__main__":
    main()
