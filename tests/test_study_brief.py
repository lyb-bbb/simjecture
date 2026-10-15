"""Study brief input compatibility and validation without provider calls."""

import pytest

from conjecture_solver.web.workspace import Workspace, load


@pytest.fixture
def study(tmp_path):
    workspace = Workspace(tmp_path / ".workspace")
    project = workspace.create({"name": "Brief validation"})
    payload = {
        "question": "Does the method preserve positivity?",
        "success_criteria": "Record a counterexample or qualified evidence.",
        "constraints": "Use ordinary Python.",
        "hours": 24,
        "completion_policy": "answer",
        "allow_solver_development": False,
    }
    workspace.save_brief(project["id"], payload)
    return workspace, project["id"], payload


@pytest.mark.parametrize("field", ["success_criteria", "constraints"])
def test_brief_text_lists_preserve_content_and_settings(study, field):
    workspace, project, payload = study
    items = ["Check positivity: α ≥ 0.", "Keep the original\nmultiline requirement."]
    brief = workspace.save_brief(project, payload | {field: items})
    assert brief[field] == "Check positivity: α ≥ 0.\n\nKeep the original\nmultiline requirement."
    assert brief["hours"] == 24
    assert brief["allow_solver_development"] is False
    assert brief["completion_policy"] == "answer"
    assert load(workspace.directory(project) / "project.json")["brief"] == brief
    assert items == ["Check positivity: α ≥ 0.", "Keep the original\nmultiline requirement."]


@pytest.mark.parametrize("field", ["success_criteria", "constraints"])
@pytest.mark.parametrize("as_list", [False, True])
def test_brief_limit_applies_to_normalized_text_and_preserves_previous_brief(study, field, as_list):
    workspace, project, payload = study
    boundary = ["α" * 10000, "b" * 9998]
    value = boundary if as_list else "\n\n".join(boundary)
    saved = workspace.save_brief(project, payload | {field: value})
    assert len(saved[field]) == 20000
    excessive = [boundary[0], boundary[1] + "!"] if as_list else value + "!"
    with pytest.raises(ValueError, match=rf"{field} must contain at most 20000 characters"):
        workspace.save_brief(project, payload | {field: excessive})
    assert load(workspace.directory(project) / "project.json")["brief"] == saved


@pytest.mark.parametrize("field", ["success_criteria", "constraints"])
@pytest.mark.parametrize("value", [None, 42, True, {"criterion": "text"}, ["text", 42], [["text"]]])
def test_brief_rejects_non_text_values_without_replacing_saved_brief(study, field, value):
    workspace, project, payload = study
    path = workspace.directory(project) / "project.json"
    previous = path.read_bytes()
    with pytest.raises(ValueError, match=rf"{field} must be text or a list of text items"):
        workspace.save_brief(project, payload | {field: value})
    assert path.read_bytes() == previous


def test_brief_keeps_question_text_only(study):
    workspace, project, payload = study
    with pytest.raises(ValueError, match="question must be text"):
        workspace.save_brief(project, payload | {"question": ["A question"]})


def test_brief_empty_lists_preserve_required_and_optional_fields(study):
    workspace, project, payload = study
    assert workspace.save_brief(project, payload | {"constraints": []})["constraints"] == ""
    for criteria in ([], ["", "  "]):
        with pytest.raises(
            ValueError, match="Specify the question and what evidence will answer it"
        ):
            workspace.save_brief(project, payload | {"success_criteria": criteria})
