---
season: 3
season_name: "Season 3 — October 2026 (Autumn / Halloween Edition)"
day: 14
title: "Skill Scanning: Block Poisoned Skills Before Agents Use Them"
summary: "Scan agent skills in CI/CD to block hidden prompt injections and data exfiltration before publishing to Agent Registry."
tags: ["Phase 3: Supply Chain", "Governance", "Supply Chain", "Tools"]
canonical_url: "https://adventofagents.com/2026/10/14"
markdown_url: "https://adventofagents.com/2026/10/14.md"
video_url: "https://www.youtube.com/embed/9A-CzJNxZp0"
primary_video:
  title: "Day 14: Supply-Chain Safety: Tool & Skill Verification"
  creator_name: "Christine Sizemore"
  duration: "7:38"
  video_url: "https://www.youtube.com/embed/9A-CzJNxZp0"
companion_videos:
  - id: "s3-d14-owain-lewis-supply-chain"
    title: "How I Code With AI Agents (Spec-Driven Development) + Oct 12 Google Cloud Production Agents"
    creator_name: "Owain Lewis"
    creator_handle: "@OwainLewis"
    creator_url: "https://www.youtube.com/@OwainLewis"
    duration: "32:45"
    video_url: "https://www.youtube.com/embed/RhaF4LVAVng"
    watch_url: "https://www.youtube.com/watch?v=RhaF4LVAVng"
    invitation_headline: "Enforce strict spec-driven contracts on third-party skills and MCP servers"
---

# 🔍 Day 14: Skill Scanning: Block Poisoned Skills Before Agents Use Them

> **Season 3 — October 2026 (Autumn / Halloween Edition)** · [Interactive Web View](https://adventofagents.com/2026/10/14?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day14) · [Raw Markdown](https://adventofagents.com/2026/10/14.md?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day14)

**Summary:** Scan agent skills in CI/CD to block hidden prompt injections and data exfiltration before publishing to Agent Registry.

## 🧭 Community Perspective & Companion Deep Dive

- **[Featured Perspective: Spec-Driven AI Agent Engineering & Cloud Run Production Stack (@OwainLewis)](https://www.youtube.com/watch?v=RhaF4LVAVng)** by **Owain Lewis** (@OwainLewis · 32:45) — See how Owain Lewis applies spec-driven development and schema pinning (`RhaF4LVAVng`), paired with his brand-new October 12, 2026 Google Cloud tutorial on hardening production ADK agents on Cloud Run + Cloud SQL PostgreSQL + Secret Manager.

**Day 14 of Google's Advent of Agents — Season 3**

Imagine pulling a helpful community weather skill or MCP server from GitHub to speed up a Friday release, unaware that line 40 of its `SKILL.md` hides a prompt override instructing your agent to read environment secrets and POST them to an external webhook.

Unlike traditional software packages, an agent skill mixes executable scripts with natural-language instructions that steer the model's reasoning loop directly. Standard dependency scanners (`pip-audit`, `npm audit`) only flag known CVEs in published libraries, leaving your runtime completely blind to freshly authored prompt injections or credential-harvesting scripts.

**How It Works**

While Day 13 isolated untrusted code at runtime inside a sandbox, supply-chain verification stops malicious skills in CI/CD before an agent ever loads them. By adding **NVIDIA SkillSpector** to your pull request checks and publishing only passing skills to **Google Cloud Agent Registry**, you ensure agents across any framework only discover and run verified tools:

![Agent Skill Supply-Chain Verification Gate](/s03/s3-day14-supply-chain-verification.png)

- **Static AST, YARA & LLM Scan**: **NVIDIA SkillSpector** runs static code analysis (Python AST, taint tracking, and YARA rules) alongside an LLM semantic pass to catch credential harvesting in scripts and hidden prompt overrides in `SKILL.md`.
- **Domain Lockfile & Integrity Digest**: A capability lockfile (`sat.lock`) restricts outbound network calls to an explicit domain allowlist, while an Agent Software Bill of Materials (`asbom.json`) pins SHA-256 hashes for every file.
- **Publish to Agent Registry**: Only skills that pass with zero high or critical findings are published to **Agent Registry**, ensuring your **Agent Runtime** only discovers and executes vetted tools.

**Resources:**

- [Register Skills in Agent Registry](https://g.dev/cloud/adventofagents-season3-docs-agent-registry-register-skills)
- [30-Second Local Kata Repository (advent-agents-supplychain-simple)](https://g.dev/cloud/adventofagents-season3-day14-demo)
- [Full CI/CD + Google Cloud Agent Registry Repository (sec-agent-advent-supplychain-sec)](https://g.dev/cloud/adventofagents-season3-day14-cicd-demo)
- [NVIDIA SkillSpector Open-Source Scanner](https://github.com/nvidia/skillspector?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day14)

## Code & Commands

### Verify a Clean vs. Poisoned Skill in 60 Seconds

```python
# Day 14: Verify a clean skill vs. a poisoned skill in under 60 seconds.
# Quickstart (copy-paste into your terminal):
#   git clone https://github.com/Cybersizemore/advent-agents-supplychain-simple.git
#   cd advent-agents-supplychain-simple && ./demo-simple.sh
#
# Full Enterprise CI/CD + Google Cloud Agent Registry repo:
#   https://github.com/Cybersizemore/sec-agent-advent-supplychain-sec

import json, subprocess, sys, tempfile
from pathlib import Path

DEFAULT_AGENT_MODEL = "gemini-3.8-flash"

def verify_skill(skill_dir: str) -> bool:
    """Concept 1: Run SkillSpector to scan SKILL.md and scripts before Agent Registry publish."""
    skill_path = Path(skill_dir).resolve()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = Path(tmp.name)

    try:
        proc = subprocess.run(
            ["skillspector", "scan", str(skill_path), "--format", "json", "--output", str(report_path)],
            capture_output=True, text=True, check=False,
        )
        report_text = report_path.read_text(encoding="utf-8").strip()
        if not report_text:
            print(f"[ERROR] SkillSpector failed to generate report: {proc.stderr.strip()}", file=sys.stderr)
            return False
        report = json.loads(report_text)
    finally:
        report_path.unlink(missing_ok=True)

    # Concept 2: Block HIGH/CRITICAL supply-chain threats before Agent Registry publication
    findings = report.get("findings", [])
    blockers = [f for f in findings if f.get("severity") in ("CRITICAL", "HIGH")]

    print(f"\n=== Scanning: {skill_path.name} ({report.get('verdict', 'UNKNOWN')}) ===")
    for f in blockers:
        loc = f.get("location", {})
        print(f"  [BLOCKED] [{f['severity']}] {f['rule_id']}: {f['message']}")
        print(f"            File: {loc.get('file')} (Line {loc.get('line')})")

    if blockers:
        print(f"[FAIL] {len(blockers)} HIGH/CRITICAL supply-chain threats blocked.")
        return False

    print(f"[PASS] Zero HIGH/CRITICAL findings. Verified for Agent Registry ({DEFAULT_AGENT_MODEL}).")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 verify_skill.py <path-to-skill>")
    sys.exit(0 if verify_skill(sys.argv[1]) else 1)
```

## Resources & Links

- **#1 Featured Cross-Promotion: [Featured Perspective: Spec-Driven AI Agent Engineering & Cloud Run Production Stack (@OwainLewis)](https://www.youtube.com/watch?v=RhaF4LVAVng)** — Owain Lewis walks through spec-driven agent architecture (`RhaF4LVAVng`) alongside his Oct 12, 2026 Google Cloud production ADK deployment guide.
- **[Register Skills in Agent Registry](https://g.dev/cloud/adventofagents-season3-docs-agent-registry-register-skills)** — Package a SKILL.md bundle and register it in Agent Registry to govern, version, and share skills across agents.
- **[30-Second Local Kata: Agent Skill Verification](https://g.dev/cloud/adventofagents-season3-day14-demo)** — Run the local SkillSpector verification gate against clean and poisoned skills in under 30 seconds.
- **[Full CI/CD Gate + Google Cloud Agent Registry Pipeline](https://g.dev/cloud/adventofagents-season3-day14-cicd-demo)** — End-to-end GitHub Actions security gate, sat.lock allowlist, ASBOM generator, and Agent Registry publisher.
- **[NVIDIA SkillSpector Open-Source Scanner](https://github.com/nvidia/skillspector?utm_source=adventofagents&utm_medium=markdown&utm_campaign=adventofagents_s3_2026&utm_content=day14)** — Static AST, YARA, and LLM semantic scanner for detecting prompt injection and exfiltration in agent skills.
