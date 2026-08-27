"""Procedencia del codigo de una corrida (Decision #11, docs/rio_search_plan.md §3.13).

El SHA del commit es la referencia durable; la rama es comodidad para navegar. Sin
dependencias del proyecto (regla de `domain`): quien lo captura de verdad es
`infrastructure.provenance.git_provenance`.
"""

from __future__ import annotations

from dataclasses import dataclass

GITHUB_REPO_URL = "https://github.com/JoacoTschopp/rio-uruguay-hydro-pipeline"


@dataclass(frozen=True, slots=True)
class CodeProvenance:
    git_sha: str
    git_branch: str
    git_remote: str | None
    git_dirty: bool
    github_url: str
    uncommitted_patch: str = ""

    def as_tags(self) -> dict[str, str]:
        """Tags `rio_search.git_*` de §3.13."""
        return {
            "git_sha": self.git_sha,
            "git_branch": self.git_branch,
            "git_remote": self.git_remote or "",
            "git_dirty": "true" if self.git_dirty else "false",
            "github_url": self.github_url,
        }

    def ensure_clean(self) -> None:
        """`provenance.require_clean_git: true` (corridas que van a la tesis, §3.13):
        la busqueda se niega a arrancar con arbol sucio."""
        if self.git_dirty:
            raise RuntimeError(
                "provenance.require_clean_git=true pero rio_search/ tiene cambios sin commitear "
                f"(git_sha={self.git_sha}). Commiteá o pasá require_clean_git=false para explorar."
            )
