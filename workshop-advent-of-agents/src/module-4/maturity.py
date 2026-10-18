"""Deterministic roll-up: area scores -> layer scores -> starting layer -> 90-day roadmap.

The LLM scores areas from evidence; arithmetic and ordering rules live here, so they
are testable and never hallucinated:
  * a layer scores its WEAKEST area
  * start at the lowest layer (in structural order) that scores below Level 3
  * Foundation in days 1-30, Prevention + Detection in 31-60, Response + Alignment in 61-90
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

CHECKLIST_PATH = Path(__file__).with_name("checklist.yaml")
TARGET_LEVEL = 3


class AreaScore(BaseModel):
    area_id: str = Field(description="checklist area id, e.g. 'identity'")
    level: Literal[1, 3, 5] = Field(description="1 = manual/ad hoc, 3 = standardized in production, 5 = automated everywhere")
    evidence: str = Field(description="the concrete facts (with file references) that justify the level")
    gap: str = Field(description="what is missing to reach the next level; empty if level 5")
    next_step: str = Field(description="one concrete action on AWS/Strands to close the gap")


class Assessment(BaseModel):
    areas: list[AreaScore] = Field(description="exactly one entry per checklist area (15 in total)")
    summary: str = Field(description="two or three sentences on the estate's overall governance posture")


def load_checklist(path: Path = CHECKLIST_PATH) -> dict:
    return yaml.safe_load(path.read_text())


def area_ids(checklist: dict) -> list[str]:
    return [a["id"] for layer in checklist["layers"] for a in layer["areas"]]


def validate(assessment: Assessment, checklist: dict) -> None:
    expected, got = area_ids(checklist), [a.area_id for a in assessment.areas]
    if sorted(expected) != sorted(got):
        missing, extra = set(expected) - set(got), set(got) - set(expected)
        raise ValueError(f"assessment must score each area exactly once (missing={missing}, extra={extra})")


def layer_scores(assessment: Assessment, checklist: dict) -> dict[str, int]:
    by_area = {a.area_id: a.level for a in assessment.areas}
    return {layer["id"]: min(by_area[a["id"]] for a in layer["areas"]) for layer in checklist["layers"]}


def starting_layer(scores: dict[str, int], checklist: dict) -> str | None:
    for layer in checklist["layers"]:  # structural order: foundation first
        if scores[layer["id"]] < TARGET_LEVEL:
            return layer["id"]
    return None


def roadmap(assessment: Assessment, checklist: dict) -> list[dict]:
    """Phases with the areas below TARGET_LEVEL, in checklist order."""
    by_area = {a.area_id: a for a in assessment.areas}
    phases: dict[str, dict] = {}
    for layer in checklist["layers"]:
        phase = phases.setdefault(layer["phase"], {"phase": layer["phase"], "layers": []})
        items = [by_area[a["id"]] for a in layer["areas"] if by_area[a["id"]].level < TARGET_LEVEL]
        phase["layers"].append({"layer": layer, "items": items})
    return list(phases.values())


def render_report(assessment: Assessment, checklist: dict, model_id: str) -> str:
    scores = layer_scores(assessment, checklist)
    start = starting_layer(scores, checklist)
    by_area = {a.area_id: a for a in assessment.areas}
    titles = {layer["id"]: layer["title"] for layer in checklist["layers"]}

    lines = [
        "# Agent Governance Readiness — assessment & 90-day roadmap",
        "",
        f"Assessed by the `governance-assessor` agent ({model_id}) from deterministic evidence; "
        "layer scores and roadmap are computed by `maturity.py`.",
        "",
        f"> {assessment.summary}",
        "",
        "## Layer scores (each layer = its weakest area)",
        "",
        "| Layer | Score | Question |",
        "|---|---|---|",
    ]
    for layer in checklist["layers"]:
        marker = " ← **start here**" if layer["id"] == start else ""
        lines.append(f"| {layer['title']} | **{scores[layer['id']]}**{marker} | {layer['question']} |")

    lines += ["", "## Area scores", "", "| Layer | Area | Level | Evidence | Gap |", "|---|---|---|---|---|"]
    for layer in checklist["layers"]:
        for area in layer["areas"]:
            s = by_area[area["id"]]
            lines.append(f"| {layer['title']} | {area['title']} | {s.level} | {s.evidence} | {s.gap or '—'} |")

    lines += ["", "## 90-day roadmap", ""]
    lines.append(f"Start with **{titles[start]}**: the gateway enforces against identities that must already "
                 "exist, and detection needs governed traffic to watch." if start else
                 "Every layer is at Level 3 or above: focus on automating towards Level 5.")
    for phase in roadmap(assessment, checklist):
        lines += ["", f"### {phase['phase']}"]
        for entry in phase["layers"]:
            layer = entry["layer"]
            lines += ["", f"**{layer['title']}** — done when: {layer['done_when']}", ""]
            if not entry["items"]:
                lines.append(f"- Already at Level {TARGET_LEVEL}+; keep it there.")
            for item in entry["items"]:
                lines.append(f"- [ ] **{item.area_id}** (L{item.level} → L{TARGET_LEVEL}): {item.next_step}")
    return "\n".join(lines) + "\n"
