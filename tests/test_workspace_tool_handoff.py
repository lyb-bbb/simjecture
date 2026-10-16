"""Scientific tool selections survive drafting and reach the frozen study contract."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from conjecture_solver.mvp_skills import MVPCapabilityInstallation
from conjecture_solver.research_service import put
from conjecture_solver.web.application import SimjectureWebApplication
from conjecture_solver.web.workspace import Workspace, load


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / ".workspace")
    workspace.__dict__["execution"] = {"backend": "process-cooperative"}
    project = workspace.create({"name": "Solver study"})
    descriptors = tmp_path / "capabilities"
    descriptors.mkdir()
    cards = []
    for name in ("flash", "other"):
        runtime = tmp_path / name
        runtime.mkdir()
        runner = runtime / "runner"
        runner.write_text("#!/usr/bin/sh\nexit 0\n")
        runner.chmod(0o755)
        descriptor = descriptors / f"{name}.json"
        put(descriptor, {
            "runtime_root": str(runtime),
            "executable": "runner",
            "manifest": {
                "name": name + "-fixture",
                "version": "1",
                "description": "Test instrument",
                "skill": "flash-mhd",
                "executable_kind": "test",
            },
        })
        cards.append({
            "id": name, "name": name, "installed": True, "path": str(descriptor),
        })
    monkeypatch.setattr(workspace, "catalogue", lambda: cards)
    payload = {
        "question": "Test the declared solver.",
        "success_criteria": "A qualified trajectory.",
        "constraints": "Keep the forcing fixed.",
        "hours": 24,
    }
    return workspace, project["id"], payload, cards


@pytest.mark.parametrize("empty_instrument", [False, True])
def test_redraft_preserves_tool_selection(handoff, empty_instrument):
    workspace, project, payload, cards = handoff
    original = workspace.save_brief(project, payload | {"instrument": "flash"})
    redraft = payload | {"question": "A revised hypothesis."}
    if empty_instrument:
        redraft["instrument"] = ""  # The built-in drafting tool's default.
    saved = workspace.save_brief(project, redraft)
    assert saved["capability_directory"] == cards[0]["path"]
    assert saved["instrument"] == original["instrument"] == "flash"


def test_redraft_preserves_direct_descriptor_selection_after_restart(handoff):
    workspace, project, payload, cards = handoff
    workspace.save_brief(project, payload | {"capability_directory": cards[0]["path"]})
    restarted = Workspace(workspace.root)
    assert restarted.save_brief(project, payload)["capability_directory"] == cards[0]["path"]


def test_explicit_selection_can_replace_or_clear_inherited_instrument(handoff):
    workspace, project, payload, cards = handoff
    workspace.save_brief(project, payload | {"instrument": "flash"})
    replaced = workspace.save_brief(project, payload | {"capability_directory": cards[1]["path"]})
    assert replaced["capability_directory"] == cards[1]["path"]
    assert "instrument" not in replaced
    cleared = workspace.save_brief(project, payload | {"capability_directory": ""})
    assert cleared["capability_directory"] == ""
    assert workspace.save_brief(project, payload)["capability_directory"] == ""


def test_browser_save_of_unchanged_selection_preserves_declared_instrument(handoff):
    workspace, project, payload, cards = handoff
    workspace.save_brief(project, payload | {"instrument": "flash"})
    saved = workspace.save_brief(project, payload | {"capability_directory": cards[0]["path"]})
    assert saved["instrument"] == "flash"


def test_continuation_selection_is_only_used_without_a_saved_brief(handoff):
    workspace, project, payload, cards = handoff
    path = workspace.directory(project) / "project.json"
    record = load(path)
    record["continuation_draft"] = {"capability_directory": cards[0]["path"]}
    put(path, record)
    assert workspace.save_brief(project, payload)["capability_directory"] == cards[0]["path"]
    workspace.save_brief(project, payload | {"capability_directory": ""})
    assert workspace.save_brief(project, payload)["capability_directory"] == ""


@pytest.mark.parametrize("override", ["", "other"])
def test_launch_rejects_missing_or_wrong_declared_instrument(handoff, monkeypatch, override):
    from conjecture_solver import study_launch

    workspace, project, payload, cards = handoff
    workspace.save_brief(project, payload | {"instrument": "flash"})
    monkeypatch.setattr(workspace, "project_connection", lambda _: {
        "backend": "codex", "model": "fixture",
    })
    monkeypatch.setattr(
        study_launch, "materialize_native",
        lambda _: pytest.fail("Invalid instrument must fail before study materialization"),
    )
    selected = cards[1]["path"] if override else ""
    app = SimjectureWebApplication(runs_root=workspace.root.parent)
    with pytest.raises(ValueError, match="declared instrument"):
        workspace.launch(project, {
            "request_key": "wrong-tool", "capability_directory": selected,
        }, app)
    directory = workspace.directory(project)
    assert not (directory / "studies").exists()
    assert load(directory / "project.json")["studies"] == []


def test_redrafted_tool_reaches_frozen_execution_contract(handoff, monkeypatch):
    from conjecture_solver import execution, mvp_launch

    workspace, project, payload, cards = handoff
    workspace.save_brief(project, payload | {"instrument": "flash"})
    workspace.save_brief(project, payload)
    monkeypatch.setattr(workspace, "project_connection", lambda _: {
        "backend": "codex", "model": "fixture",
    })
    monkeypatch.setattr(execution, "require_execution_backend", lambda _: {"available": True})
    monkeypatch.setattr(
        mvp_launch, "start_managed_campaign", lambda _: SimpleNamespace(close=lambda: None)
    )
    app = SimjectureWebApplication(runs_root=workspace.root.parent)
    result = workspace.launch(project, {"request_key": "correct-tool"}, app)
    root = Path(result["path"])
    manifest = load(root / "research.json")
    installation = MVPCapabilityInstallation.read(cards[0]["path"])
    assert manifest["capability_hashes"] == {"flash-fixture": installation.contract_hash}
    assert load(root / "study-launch.json")["request"]["capability_directory"]
    assert load(root / "project-brief.json")["instrument"] == "flash"


def test_unknown_instrument_does_not_replace_saved_selection(handoff):
    workspace, project, payload, _ = handoff
    workspace.save_brief(project, payload | {"instrument": "flash"})
    path = workspace.directory(project) / "project.json"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="registered research capability"):
        workspace.save_brief(project, payload | {"instrument": "missing"})
    assert path.read_bytes() == before
