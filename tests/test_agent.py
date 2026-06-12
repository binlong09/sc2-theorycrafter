"""Agent tool-layer tests — the deterministic bridge between the LLM and the DB.

These don't call an LLM (that needs a live Ollama/Claude). They pin that the tools
dispatch correctly, return grounded numbers, and fail safely — so whichever model
sits on top is constrained to verified data.
"""

import pytest

from sc2tc.db import build
from sc2tc.agent.tools import TOOLS, dispatch


@pytest.fixture(scope="module", autouse=True)
def _db():
    build()  # ensure the DB exists for the tool calls


def test_compute_breakpoint_tool():
    out = dispatch("compute_breakpoint",
                   {"attacker": "Zealot", "defender": "Zergling", "atk_upgrade": 1})
    assert "two-shot" in out and "2 attack cycle" in out

def test_get_unit_stats_tool_is_grounded():
    out = dispatch("get_unit_stats", {"unit_name": "Ghost"})
    assert "hp 100" in out and "ground 20" in out  # engine-sourced 5.0.16 values
    assert "source:" in out

def test_get_unit_stats_resolves_nickname_and_shows_air():
    out = dispatch("get_unit_stats", {"unit_name": "muta"})
    assert out.startswith("Mutalisk") and "anti-air" in out and "flyer" in out

def test_simulate_build_order_tool():
    out = dispatch("simulate_build_order",
                   {"build_order": ["Pylon", "Gateway"], "race": "Protoss"})
    assert "Gateway" in out and "start 8 workers" in out

def test_list_units_tool():
    out = dispatch("list_units", {"race": "Protoss"})
    assert "Zealot" in out and "Immortal" in out

def test_list_upgrades_tool():
    out = dispatch("list_upgrades", {"race": "Protoss"})
    assert "ProtossGroundWeaponsLevel1" in out and "Forge" in out

def test_upgrade_timing_via_build_order():
    out = dispatch("simulate_build_order", {
        "build_order": ["Pylon", "Assimilator", "Forge", "ProtossGroundWeaponsLevel1"],
        "race": "Protoss"})
    assert "ProtossGroundWeaponsLevel1" in out  # the upgrade actually scheduled


# --- safety: tools fail without crashing (so the model can recover) ----------

def test_unknown_unit_returns_message_not_crash():
    out = dispatch("get_unit_stats", {"unit_name": "Nonexistron"})
    assert "No unit" in out

def test_no_attack_unit_returns_error_string():
    out = dispatch("compute_breakpoint", {"attacker": "Overlord", "defender": "Marine"})
    assert out.startswith("ERROR")

def test_unknown_tool_name():
    assert dispatch("frobnicate", {}).startswith("ERROR: unknown tool")

def test_bad_arguments_handled():
    assert dispatch("get_unit_stats", {"wrong_arg": "x"}).startswith("ERROR")


# --- registry well-formed (both backends adapt these) ------------------------

def test_router_keeps_simple_queries_local():
    from sc2tc.agent.agent import route
    for q in ("does +1 zealot two-shot a zergling?", "earliest +1 attack?", "ghost stats?"):
        backend, _model, _why = route(q)
        assert backend == "ollama"

def test_router_escalates_ambiguous_builds():
    from sc2tc.agent.agent import route
    for q in ("earliest 4 gate warp gate all-in?", "fastest +1 on 2 bases with 6 warp gates?"):
        backend, model, _why = route(q)
        assert backend == "claude" and model == "claude-opus-4-8"


def test_tool_registry_shape():
    for t in TOOLS:
        assert {"name", "description", "parameters", "fn"} <= set(t)
        assert t["parameters"]["type"] == "object"
        assert callable(t["fn"])
