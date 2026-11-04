"""The suite selector ignores documents and keeps code changes."""

import os

from scripts.select_tests import changed_paths, classify, suites_for, write_gitlab_child


def test_markdown_and_images_do_not_select_a_suite() -> None:
    assert suites_for(["README.md", "docs/guide.markdown", "notes.rst", "assets/logo.png"]) == []
    assert classify("DECISIONS.md") == set()


def test_corpus_markdown_still_runs_the_backend() -> None:
    assert suites_for(["corpus/hx-200-brakes.md", "README.md"]) == ["backend"]
    assert "backend" in classify("evaluation/questions.json")


def test_code_selects_only_its_suite() -> None:
    assert suites_for(["frontend/src/AskPage.jsx"]) == ["frontend"]
    assert suites_for(["backend/app/api/v1/documents.py"]) == ["backend"]
    assert suites_for(["worker/tasks.py"]) == ["backend"]
    assert suites_for(["scripts/select_tests.py"]) == ["plan"]


def test_a_mixed_change_runs_each_affected_suite() -> None:
    assert suites_for(
        ["README.md", "frontend/src/api.js", "backend/tests/test_download.py"]
    ) == ["backend", "frontend"]


def test_workflow_changes_run_every_suite() -> None:
    assert suites_for([".github/workflows/ci.yml"]) == ["plan", "backend", "frontend"]
    assert suites_for([".gitlab-ci.yml", ".gitlab/pytest.yml"]) == ["plan", "backend", "frontend"]


def test_unknown_diff_runs_every_suite(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_BEFORE", "0" * 40)
    assert changed_paths() is None


def test_pull_request_uses_the_base_sha(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_BASE_SHA", "")
    assert changed_paths() is None
    monkeypatch.setenv("GITHUB_BASE_SHA", "abc123")

    def fake_git(*args: str):
        assert args == ("diff", "--name-only", "abc123...HEAD")
        return ["README.md", "frontend/src/App.jsx"]

    monkeypatch.setattr("scripts.select_tests._git", fake_git)
    assert changed_paths() == ["README.md", "frontend/src/App.jsx"]
    assert os.environ["GITHUB_EVENT_NAME"] == "pull_request"


def test_gitlab_merge_request_uses_the_diff_base(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("CI_PIPELINE_SOURCE", "merge_request_event")
    monkeypatch.setenv("CI_MERGE_REQUEST_DIFF_BASE_SHA", "")
    assert changed_paths() is None
    monkeypatch.setenv("CI_MERGE_REQUEST_DIFF_BASE_SHA", "abc123")

    def fake_git(*args: str):
        assert args == ("diff", "--name-only", "abc123...HEAD")
        return ["README.md"]

    monkeypatch.setattr("scripts.select_tests._git", fake_git)
    assert changed_paths() == ["README.md"]


def test_gitlab_child_includes_only_the_selected_suites(tmp_path) -> None:
    child = tmp_path / "child.yml"
    write_gitlab_child(str(child), ["frontend"])
    text = child.read_text()
    assert "local: .gitlab/frontend.yml" in text
    assert "pytest.yml" not in text
    assert "selector.yml" not in text

    write_gitlab_child(str(child), [])
    assert 'echo "No tests to run."' in child.read_text()


def test_gitlab_first_push_runs_every_suite(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("CI_PIPELINE_SOURCE", "push")
    monkeypatch.setenv("CI_COMMIT_BEFORE_SHA", "0" * 40)
    assert changed_paths() is None
    monkeypatch.setenv("CI_COMMIT_BEFORE_SHA", "def456")

    def fake_git(*args: str):
        assert args == ("diff", "--name-only", "def456", "HEAD")
        return ["backend/app/main.py"]

    monkeypatch.setattr("scripts.select_tests._git", fake_git)
    assert changed_paths() == ["backend/app/main.py"]
