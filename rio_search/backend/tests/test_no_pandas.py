"""Decision #9 (docs/rio_search_plan.md): Polars, nunca pandas. `pandas` no es una
dependencia declarada; este test falla si de todas formas se puede importar (p. ej. porque
otra libreria lo arrastro transitivamente sin que nos dieramos cuenta)."""

import importlib.util

import pytest


def test_no_pandas_in_env() -> None:
    spec = importlib.util.find_spec("pandas")
    assert spec is None, (
        "pandas esta instalado en el entorno de rio_search/backend; esta prohibido "
        "(Decision #9): usar Polars. Revisar de que dependencia lo arrastra "
        "(`uv tree --package pandas` o similar) y aislarla."
    )


def test_pandas_import_actually_fails() -> None:
    with pytest.raises(ModuleNotFoundError):
        __import__("pandas")
