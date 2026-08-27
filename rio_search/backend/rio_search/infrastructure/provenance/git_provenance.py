"""Captura procedencia del codigo con `git` (Decision #11, docs/rio_search_plan.md §3.13).

Usa `subprocess` sobre el `git` del sistema (no `gitpython`: no esta en las dependencias
declaradas de Fase 0). El scope de "sucio" y del patch es `rio_search/`, no el repo entero.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from rio_search.domain.experiments.code_provenance import GITHUB_REPO_URL, CodeProvenance


def _discover_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"No se encontro un repo git subiendo desde {start}")


class GitProvenance:
    """Implementa `application.ports.git_provenance.GitProvenancePort`."""

    def __init__(self, repo_root: Path | None = None, scope: str = "rio_search") -> None:
        self._repo_root = repo_root or _discover_repo_root(Path(__file__).resolve())
        self._scope = scope

    def capture(self) -> CodeProvenance:
        sha = self._run(["git", "rev-parse", "HEAD"])
        branch = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        remote = self._run(["git", "remote", "get-url", "origin"], allow_fail=True) or None
        status = self._run(["git", "status", "--porcelain", "--", self._scope], allow_fail=True)
        dirty = bool(status.strip())
        patch = self._run(["git", "diff", "HEAD", "--", self._scope], allow_fail=True)
        github_url = f"{GITHUB_REPO_URL}/tree/{sha}/{self._scope}"
        return CodeProvenance(
            git_sha=sha,
            git_branch=branch,
            git_remote=remote,
            git_dirty=dirty,
            github_url=github_url,
            uncommitted_patch=patch,
        )

    def _run(self, cmd: list[str], allow_fail: bool = False) -> str:
        result = subprocess.run(
            cmd, cwd=self._repo_root, capture_output=True, text=True, timeout=30, check=False
        )
        if result.returncode != 0:
            if allow_fail:
                return ""
            raise RuntimeError(f"`{' '.join(cmd)}` fallo: {result.stderr.strip()}")
        return result.stdout.strip()
