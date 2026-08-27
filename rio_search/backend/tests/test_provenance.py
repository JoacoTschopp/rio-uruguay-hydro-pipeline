"""Tests de `GitProvenance` (Decision #11, docs/rio_search_plan.md §3.13).

Corren contra un repo git temporal y aislado (no el repo real) para poder controlar el
estado sucio/limpio de forma determinista."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rio_search.infrastructure.provenance.git_provenance import GitProvenance


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, f"{' '.join(cmd)} fallo: {result.stderr}"


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    _run(["git", "init", "-q"], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    _run(["git", "config", "user.name", "Test"], cwd=tmp_path)
    (tmp_path / "rio_search").mkdir()
    (tmp_path / "rio_search" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "other_dir").mkdir()
    (tmp_path / "other_dir" / "bar.py").write_text("y = 2\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=tmp_path)
    _run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path)
    return tmp_path


def test_capture_on_clean_tree(fake_repo: Path) -> None:
    provenance = GitProvenance(repo_root=fake_repo).capture()

    assert len(provenance.git_sha) == 40
    assert provenance.git_dirty is False
    assert provenance.uncommitted_patch == ""
    assert provenance.github_url == (
        "https://github.com/JoacoTschopp/rio-uruguay-hydro-pipeline/tree/"
        f"{provenance.git_sha}/rio_search"
    )


def test_capture_marks_dirty_when_rio_search_changes(fake_repo: Path) -> None:
    (fake_repo / "rio_search" / "foo.py").write_text("x = 2\n", encoding="utf-8")

    provenance = GitProvenance(repo_root=fake_repo).capture()

    assert provenance.git_dirty is True
    assert "foo.py" in provenance.uncommitted_patch


def test_capture_ignores_changes_outside_scope(fake_repo: Path) -> None:
    (fake_repo / "other_dir" / "bar.py").write_text("y = 3\n", encoding="utf-8")

    provenance = GitProvenance(repo_root=fake_repo).capture()

    assert provenance.git_dirty is False
    assert provenance.uncommitted_patch == ""


def test_as_tags_has_fixed_keys(fake_repo: Path) -> None:
    tags = GitProvenance(repo_root=fake_repo).capture().as_tags()
    assert set(tags.keys()) == {"git_sha", "git_branch", "git_remote", "git_dirty", "github_url"}


def test_ensure_clean_raises_when_dirty(fake_repo: Path) -> None:
    (fake_repo / "rio_search" / "foo.py").write_text("x = 2\n", encoding="utf-8")
    provenance = GitProvenance(repo_root=fake_repo).capture()
    with pytest.raises(RuntimeError):
        provenance.ensure_clean()


def test_ensure_clean_ok_when_clean(fake_repo: Path) -> None:
    provenance = GitProvenance(repo_root=fake_repo).capture()
    provenance.ensure_clean()  # no debe lanzar
