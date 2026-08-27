"""Tests de `infrastructure.tracking.params.flatten_params` (Fase 2, docs/rio_search_plan.md
§3.5: "Params: la config YAML aplanada (model.hidden_size, sequence.lookback_days, ...)")."""

from __future__ import annotations

from rio_search.infrastructure.tracking.params import flatten_params


def test_flattens_nested_dicts_with_dotted_keys() -> None:
    data = {"model": {"name": "bilstm", "params": {"hidden_size": 64}}, "sequence": {"lookback_days": 60}}
    out = flatten_params(data)
    assert out == {
        "model.name": "bilstm",
        "model.params.hidden_size": "64",
        "sequence.lookback_days": "60",
    }


def test_lists_are_joined_with_commas() -> None:
    out = flatten_params({"dataset": {"horizons": [1, 2, 3, 7, 14]}})
    assert out["dataset.horizons"] == "1,2,3,7,14"


def test_none_becomes_empty_string() -> None:
    out = flatten_params({"model": {"params": {}}, "note": None})
    assert out["note"] == ""


def test_empty_dict_produces_no_params() -> None:
    assert flatten_params({}) == {}
