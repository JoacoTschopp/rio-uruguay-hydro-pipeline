# rio_search/backend

Backend Python de Rio_Search (`docs/rio_search_plan.md`). Proyecto `uv` independiente, Python 3.12,
arquitectura Onion + DDD (`rio_search/domain`, `application`, `infrastructure`, `interfaces`).

## Setup

```
uv sync
```

## Tests (offline por defecto)

```
uv run pytest
```

Los tests marcados `@pytest.mark.integration` tocan Databricks/MLflow real y no corren por defecto:

```
uv run pytest -m integration
```

## CLI

```
uv run rio-search --help
```
