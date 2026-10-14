#!/bin/sh
# Prints one line per policy decision this box recorded: verdict, action, what it was about, and
# the rule that decided it. Pass --deny to print only the refusals.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
records="$here/state/private/telemetry/records.jsonl"
[ -f "$records" ] || { echo "no decision log yet at $records: run the box first" >&2; exit 1; }
only=${1:-}

jq -r --arg only "$only" '.resourceLogs[]?.scopeLogs[].logRecords[]
  | (.attributes | map({(.key): .value}) | add) as $a
  | select($a["strands.box.policy.verdict"])
  | select($only != "--deny" or $a["strands.box.policy.verdict"].stringValue == "deny")
  | [$a["strands.box.policy.verdict"].stringValue, $a["strands.box.policy.action"].stringValue,
     ($a["file.path"].stringValue // $a["server.address"].stringValue
      // ($a["process.command_args"].arrayValue.values | map(.stringValue) | join(" "))
      // $a["strands.box.policy.resource"].stringValue),
     ($a["strands.box.policy.rule"].stringValue // "default-deny")]
  | @tsv' "$records"
