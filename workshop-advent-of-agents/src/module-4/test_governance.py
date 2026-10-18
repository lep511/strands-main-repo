"""Deterministic tests for the maturity roll-up, the registry and the Response controls.

    uv run --group dev pytest src/module-4 -v
"""

import shutil
from types import SimpleNamespace

import pytest

import estate_registry
import evidence
from governance_controls import RegistryGate
from maturity import AreaScore, Assessment, area_ids, layer_scores, load_checklist, roadmap, starting_layer, validate

CHECKLIST = load_checklist()


def make_assessment(**levels: int) -> Assessment:
    return Assessment(
        areas=[AreaScore(area_id=a, level=levels.get(a, 3), evidence="e", gap="g", next_step=f"fix {a}")
               for a in area_ids(CHECKLIST)],
        summary="s",
    )


class TestMaturity:
    def test_checklist_has_fifteen_areas_in_five_layers(self):
        assert len(CHECKLIST["layers"]) == 5
        assert len(area_ids(CHECKLIST)) == 15

    def test_layer_scores_its_weakest_area(self):
        scores = layer_scores(make_assessment(identity=5, inventory=1, infrastructure=5), CHECKLIST)
        assert scores["foundation"] == 1
        assert scores["prevention"] == 3

    def test_start_at_lowest_layer_below_three_in_structural_order(self):
        # Response is weaker than Prevention, but Prevention comes first structurally.
        scores = layer_scores(make_assessment(circuit_breakers=1, containment=1, playbooks=1), CHECKLIST)
        assert starting_layer(scores, CHECKLIST) == "prevention"

    def test_no_start_layer_when_everything_is_at_three(self):
        assert starting_layer(layer_scores(make_assessment(), CHECKLIST), CHECKLIST) is None

    def test_roadmap_phases_and_items(self):
        phases = roadmap(make_assessment(identity=1, audit=1, drift=1), CHECKLIST)
        assert [p["phase"] for p in phases] == ["Days 1-30", "Days 31-60", "Days 61-90"]
        items = {p["phase"]: [i.area_id for e in p["layers"] for i in e["items"]] for p in phases}
        assert items == {"Days 1-30": ["identity"], "Days 31-60": ["audit"], "Days 61-90": ["drift"]}

    def test_validate_rejects_missing_or_duplicate_areas(self):
        a = make_assessment()
        a.areas = a.areas[1:] + [a.areas[1]]
        with pytest.raises(ValueError, match="exactly once"):
            validate(a, CHECKLIST)

    def test_levels_other_than_1_3_5_are_rejected(self):
        with pytest.raises(ValueError):
            AreaScore(area_id="identity", level=2, evidence="e", gap="g", next_step="n")


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "agent_registry.yaml"
    shutil.copy(estate_registry.REGISTRY_PATH, path)
    return {"path": path, "state_path": tmp_path / "state.json"}


class TestRegistryAndContainment:
    def test_revoke_and_restore(self, registry):
        assert estate_registry.status("inbox-assistant", **registry) == "active"
        estate_registry.set_status("inbox-assistant", "revoked", "test", **registry)
        assert estate_registry.status("inbox-assistant", **registry) == "revoked"
        assert estate_registry.status("adlc-day1", **registry) == "active"  # only one agent contained
        estate_registry.set_status("inbox-assistant", "active", **registry)
        assert estate_registry.status("inbox-assistant", **registry) == "active"

    def test_unknown_agent_cannot_be_revoked(self, registry):
        with pytest.raises(KeyError):
            estate_registry.set_status("ghost", "revoked", **registry)

    def test_gate_refuses_revoked_and_unregistered_agents(self, registry):
        estate_registry.set_status("inbox-assistant", "revoked", **registry)
        for agent_id in ("inbox-assistant", "shadow-agent"):
            gate = RegistryGate(agent_id, **registry)
            inv = SimpleNamespace(cancel=False)
            call = SimpleNamespace(cancel_tool=False, tool_use={"name": "send_email"})
            gate.check_invocation(inv)
            gate.check_tool(call)
            assert inv.cancel.startswith("Invocation refused") and call.cancel_tool.startswith("Tool call refused")

    def test_gate_lets_active_agents_through(self, registry):
        inv = SimpleNamespace(cancel=False)
        RegistryGate("adlc-day1", **registry).check_invocation(inv)
        assert inv.cancel is False

    def test_discovery_finds_registered_agents_and_flags_shadow_ones(self, tmp_path):
        src = tmp_path / "src"
        (src / "module-1").mkdir(parents=True)
        (src / "rogue").mkdir()
        (src / "module-1" / "a.py").write_text("agent = Agent(name='x')\n")
        (src / "rogue" / "b.py").write_text("def f():\n    return Agent()\n")
        (src / "rogue" / "test_b.py").write_text("agent = Agent()\n")
        (src / "rogue" / "build" / "package").mkdir(parents=True)
        (src / "rogue" / "build" / "package" / "vendored.py").write_text("agent = Agent()\n")
        found = estate_registry.discover_agent_sources(src)
        assert [f.rsplit("/", 1)[-1] for f in found] == ["a.py", "b.py"]


@pytest.mark.parametrize("area_id", area_ids(CHECKLIST))
def test_every_area_has_an_evidence_collector(area_id):
    facts = evidence.collect(area_id)["facts"]
    assert facts and all(isinstance(f, str) for f in facts)
