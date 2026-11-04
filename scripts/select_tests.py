"""Run the test suites that match the files in this change.

Markdown, images, and other documents do not select a suite.
The same rules are used locally and in CI.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE_ORDER = ("plan", "backend", "frontend")
DOCUMENT_SUFFIXES = (".md", ".markdown", ".rst", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def suites_for(paths: list[str]) -> list[str]:
    """The suite names to run, in a stable order. An empty list means this change needs no tests."""
    selected: set[str] = set()
    for path in paths:
        selected |= classify(path)
    return [name for name in SUITE_ORDER if name in selected]


def classify(path: str) -> set[str]:
    """Which suites one path affects. A Markdown file outside the corpus selects nothing."""
    name = path.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    if _is_document(name) and not _is_fixture(name):
        return set()
    if name.startswith("scripts/"):
        return {"plan"}
    if name.startswith(".github/workflows/") or name == ".gitlab-ci.yml" or name.startswith(".gitlab/"):
        return {"plan", "backend", "frontend"}
    if name.startswith("frontend/") and _frontend_code(name):
        return {"frontend"}
    if name.startswith(("backend/", "worker/")) and _python_or_requirement(name):
        return {"backend"}
    if _is_fixture(name):
        return {"backend"}
    if name == "Makefile":
        return {"plan"}
    if name.endswith(".py"):
        return {"backend"}
    return set()


def _is_document(path: str) -> bool:
    """True for Markdown, reStructuredText, and images. Those changes do not run tests."""
    return path.lower().endswith(DOCUMENT_SUFFIXES)


def _is_fixture(path: str) -> bool:
    """True for files under corpus or evaluation. Those still exercise the backend."""
    return path.startswith(("corpus/", "evaluation/"))


def _frontend_code(path: str) -> bool:
    """True for the UI source, its tests, and the Vite config."""
    return path.endswith((".js", ".jsx", ".css", ".json")) or path.endswith("vite.config.js")


def _python_or_requirement(path: str) -> bool:
    """True for backend and worker Python and their dependency lists."""
    return path.endswith((".py", ".txt", ".ini", ".toml", ".cfg"))


def changed_paths() -> list[str] | None:
    """Return changed paths. None means the diff is unknown and every suite should run."""
    if os.environ.get("GITHUB_EVENT_NAME"):
        return _github_changes()
    if os.environ.get("GITLAB_CI"):
        return _gitlab_changes()
    return _local_changes()


def _github_changes() -> list[str] | None:
    """Paths in a GitHub pull request or push. A new branch with no parent runs every suite."""
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event == "pull_request":
        base = os.environ.get("GITHUB_BASE_SHA", "")
        if not base:
            return None
        return _git("diff", "--name-only", f"{base}...HEAD")
    if event == "push":
        before = os.environ.get("GITHUB_BEFORE", "")
        if not before or set(before) == {"0"}:
            return None
        return _git("diff", "--name-only", before, "HEAD")
    return _local_changes()


def _gitlab_changes() -> list[str] | None:
    """Paths in a GitLab merge request or push. An unknown base runs every suite."""
    if os.environ.get("CI_PIPELINE_SOURCE") == "merge_request_event":
        base = os.environ.get("CI_MERGE_REQUEST_DIFF_BASE_SHA", "")
        if not base:
            return None
        return _git("diff", "--name-only", f"{base}...HEAD")
    before = os.environ.get("CI_COMMIT_BEFORE_SHA", "")
    if not before or set(before) == {"0"}:
        return None
    return _git("diff", "--name-only", before, "HEAD")


def _local_changes() -> list[str] | None:
    """Staged, unstaged, and untracked files. make test uses this."""
    found: set[str] = set()
    for args in (
        ("diff", "--name-only", "HEAD"),
        ("diff", "--name-only", "--cached"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        lines = _git(*args)
        if lines is None:
            return None
        found.update(lines)
    if found:
        return sorted(found)
    parent = _git("rev-parse", "--verify", "--quiet", "HEAD~1")
    if parent:
        committed = _git("diff", "--name-only", "HEAD~1", "HEAD")
        return [] if committed is None else committed
    return _git("ls-tree", "-r", "--name-only", "HEAD")


def _git(*args: str) -> list[str] | None:
    """Run git and return the path list, or None when git cannot answer."""
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


GITLAB_INCLUDES = {
    "plan": ".gitlab/selector.yml",
    "backend": ".gitlab/pytest.yml",
    "frontend": ".gitlab/frontend.yml",
}


def write_gitlab_child(path: str, selected: list[str]) -> None:
    """Write a child pipeline that contains only the selected suites."""
    includes = [GITLAB_INCLUDES[name] for name in SUITE_ORDER if name in selected]
    lines = ["stages:", "  - test", ""]
    if not includes:
        lines.extend(
            [
                "no-tests:",
                "  stage: test",
                "  script:",
                '    - echo "No tests to run."',
                "",
            ]
        )
    else:
        lines.append("include:")
        lines.extend(f"  - local: {item}" for item in includes)
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_suite_output(path: str, selected: list[str]) -> None:
    """Write the selected suite names as lines."""
    with open(path, "a", encoding="utf-8") as handle:
        for name in SUITE_ORDER:
            handle.write(f"{name}={'true' if name in selected else 'false'}\n")


def write_github_output(selected: list[str]) -> None:
    """Append the suite list to GITHUB_OUTPUT."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        write_suite_output(path, selected)


def run_suites(selected: list[str]) -> int:
    """Run the selected suites in this checkout and return the first non-zero status."""
    if not selected:
        print("No tests to run.")
        return 0
    code = 0
    python = ROOT / "backend" / ".venv" / "bin" / "python"
    runner = str(python if python.exists() else Path(sys.executable))
    if "plan" in selected:
        code = _run([runner, "-m", "pytest", "scripts/test_select_tests.py"], ROOT) or code
    if "backend" in selected:
        code = _run([runner, "-m", "pytest"], ROOT / "backend") or code
    if "frontend" in selected:
        code = _run(["npm", "test"], ROOT / "frontend") or code
    return code


def _option(argv: list[str], name: str) -> str | None:
    """The value after a flag in argv, if the flag is present."""
    if name not in argv:
        return None
    index = argv.index(name)
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def _run(command: list[str], cwd: Path) -> int:
    """Run one command in a directory and return its exit code."""
    print("+", " ".join(command))
    completed = subprocess.run(command, cwd=cwd)
    return completed.returncode


def main(argv: list[str]) -> int:
    """Select suites from the diff, or run them. A document-only change exits without running tests."""
    paths = changed_paths()
    selected = list(SUITE_ORDER) if paths is None else suites_for(paths)
    publish = "--github-output" in argv
    child = _option(argv, "--gitlab-child")
    dry_run = "--dry-run" in argv or publish or child is not None
    if publish:
        write_github_output(selected)
    if child:
        write_gitlab_child(child, selected)
    print(" ".join(selected) if selected else "none")
    if dry_run:
        return 0
    return run_suites(selected)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
