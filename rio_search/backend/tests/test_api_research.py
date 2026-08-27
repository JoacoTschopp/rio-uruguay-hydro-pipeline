"""Tests offline de los endpoints `/api/research/*` (Fase 7, docs/rio_search_plan.md §3.9, §3.10):
`ApiDependencies` propio y minimo (no reusa el fixture `client` de `test_api.py` a proposito --
importarlo bajo el mismo nombre de parametro dispara F811 en `ruff`, ver docstring de
`_client_fixture` mas abajo) con los mismos `Fake*` de Research que ya cubre `test_api.py`, mas
stand-ins triviales para el resto de `ApiDependencies` (irrelevantes para estos endpoints, nunca
invocados por ellos)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rio_search.application.experiments.compare_runs import CompareRuns
from rio_search.application.experiments.get_run_detail import GetRunDetail
from rio_search.application.experiments.list_runs import ListRuns
from rio_search.application.experiments.list_searches import ListSearches
from rio_search.application.predictions.backtest_recent import BacktestRecent
from rio_search.application.predictions.promote_champion import PromoteChampion
from rio_search.application.research.add_document import AddDocument
from rio_search.application.research.export_bibtex import ExportBibtex
from rio_search.application.research.tag_document import TagDocument
from rio_search.application.research.update_note import UpdateNote
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.interfaces.api.dependencies import ApiDependencies
from rio_search.interfaces.api.main import create_app
from tests.test_api import (
    FakeBibliographyExporter,
    FakeChampionStore,
    FakeDocumentStore,
    FakeForecastRepository,
    FakeJobRunner,
    FakeReader,
    FakeSnapshotSync,
)

BASE_PATH = "/Users/test@example.com/rio_search"


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    """`ApiDependencies` propio (no toca Databricks/MLflow real, §5): solo `document_store`
    tiene datos reales de prueba -- el resto de puertos son fakes vacios, suficientes para
    construir `ApiDependencies` sin ejercitarse (ningun test de este archivo pega a
    `/api/runs`/`/api/jobs`/`/api/champions`/`/api/forecasts`)."""
    experiments_dir = tmp_path / "configs" / "experiments"
    experiments_dir.mkdir(parents=True)
    reader = FakeReader([])
    list_runs = ListRuns(reader=reader, base_path=BASE_PATH)
    feature_catalog = FeatureCatalog(groups=())
    champion_store = FakeChampionStore()
    forecast_repository = FakeForecastRepository()
    document_store = FakeDocumentStore()
    deps = ApiDependencies(
        reader=reader,
        list_runs=list_runs,
        list_searches=ListSearches(list_runs=list_runs),
        get_run_detail=GetRunDetail(reader=reader),
        compare_runs=CompareRuns(reader=reader),
        job_runner=FakeJobRunner(),
        experiments_dir=experiments_dir,
        snapshot_sync=FakeSnapshotSync(),
        feature_catalog=feature_catalog,
        promote_champion=PromoteChampion(reader=reader, store=champion_store, model_alias=None),
        champion_store=champion_store,
        forecast_repository=forecast_repository,
        backtest_recent=BacktestRecent(
            forecast_repository=forecast_repository, dataset_repository=None
        ),
        document_store=document_store,
        add_document=AddDocument(store=document_store),
        update_note=UpdateNote(store=document_store),
        tag_document=TagDocument(store=document_store),
        export_bibtex=ExportBibtex(store=document_store, exporter=FakeBibliographyExporter()),
        references_bib_path=tmp_path / "thesis" / "common" / "references.bib",
    )
    return TestClient(create_app(deps=deps))


def _create_document(
    client: TestClient,
    title: str = "Long Short-Term Memory",
    authors: str = "Hochreiter, S.;Schmidhuber, J.",
    year: int = 1997,
    type_: str = "paper",
    venue: str | None = "Neural Computation",
    tags: str = "lstm,deep-learning",
    slug: str | None = None,
    with_file: bool = False,
):
    data = {
        "title": title,
        "authors": authors,
        "year": str(year),
        "type": type_,
        "tags": tags,
    }
    if venue is not None:
        data["venue"] = venue
    if slug is not None:
        data["slug"] = slug
    files = None
    if with_file:
        files = {"file": ("paper.pdf", b"%PDF-1.4 contenido de prueba", "application/pdf")}
    return client.post("/api/research/documents", data=data, files=files)


def test_create_document_returns_201_with_document_and_empty_note(client: TestClient) -> None:
    response = _create_document(client)
    assert response.status_code == 201
    body = response.json()
    assert body["document"]["slug"] == "long-short-term-memory-1997"
    assert body["document"]["authors"] == ["Hochreiter, S.", "Schmidhuber, J."]
    assert body["document"]["tags"] == ["lstm", "deep-learning"]
    assert body["note"]["sections"] == {}
    assert body["note"]["links"] == []


def test_create_document_with_file_sets_file_field(client: TestClient) -> None:
    response = _create_document(client, slug="con-pdf", with_file=True)
    assert response.status_code == 201
    assert response.json()["document"]["file"] == "documents/con-pdf.pdf"


def test_create_document_invalid_type_returns_400(client: TestClient) -> None:
    response = _create_document(client, type_="not-a-type")
    assert response.status_code == 400


def test_create_document_duplicate_slug_returns_400(client: TestClient) -> None:
    _create_document(client, slug="dup")
    response = _create_document(client, slug="dup", title="Otro título")
    assert response.status_code == 400


def test_list_documents_returns_created_documents(client: TestClient) -> None:
    _create_document(client, slug="doc-a", title="A")
    _create_document(client, slug="doc-b", title="B")
    response = client.get("/api/research/documents")
    assert response.status_code == 200
    slugs = {d["slug"] for d in response.json()["documents"]}
    assert slugs == {"doc-a", "doc-b"}


def test_get_document_detail(client: TestClient) -> None:
    _create_document(client, slug="doc-x")
    response = client.get("/api/research/documents/doc-x")
    assert response.status_code == 200
    assert response.json()["document"]["slug"] == "doc-x"


def test_get_document_detail_missing_returns_404(client: TestClient) -> None:
    response = client.get("/api/research/documents/no-existe")
    assert response.status_code == 404


def test_update_tags_replaces_tag_set(client: TestClient) -> None:
    _create_document(client, slug="doc-tags", tags="viejo")
    response = client.put("/api/research/documents/doc-tags/tags", json={"tags": "nuevo,otro"})
    assert response.status_code == 200
    assert response.json()["tags"] == ["nuevo", "otro"]


def test_update_tags_missing_document_returns_404(client: TestClient) -> None:
    response = client.put("/api/research/documents/no-existe/tags", json={"tags": "x"})
    assert response.status_code == 404


def test_update_note_persists_sections_and_links(client: TestClient) -> None:
    _create_document(client, slug="doc-note")
    response = client.put(
        "/api/research/documents/doc-note/notes",
        json={
            "sections": {"methodology": "Se usa BiLSTM.", "results": "Supera persistencia."},
            "links": [{"kind": "decision", "ref": "041"}, {"kind": "run", "ref": "bilstm-v9"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sections"]["methodology"] == "Se usa BiLSTM."
    assert {"kind": "decision", "ref": "041"} in body["links"]
    assert {"kind": "run", "ref": "bilstm-v9"} in body["links"]

    detail = client.get("/api/research/documents/doc-note").json()
    assert detail["note"]["sections"]["results"] == "Supera persistencia."


def test_update_note_invalid_link_kind_returns_400(client: TestClient) -> None:
    _create_document(client, slug="doc-bad-link")
    response = client.put(
        "/api/research/documents/doc-bad-link/notes",
        json={"sections": {}, "links": [{"kind": "not-a-kind", "ref": "1"}]},
    )
    assert response.status_code == 400


def test_update_note_missing_document_returns_404(client: TestClient) -> None:
    response = client.put("/api/research/documents/no-existe/notes", json={"sections": {}})
    assert response.status_code == 404


def test_get_document_file_returns_content(client: TestClient) -> None:
    _create_document(client, slug="doc-with-file", with_file=True)
    response = client.get("/api/research/documents/doc-with-file/file")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 contenido de prueba"
    assert response.headers["content-type"] == "application/pdf"


def test_get_document_file_missing_returns_404(client: TestClient) -> None:
    _create_document(client, slug="doc-without-file")
    response = client.get("/api/research/documents/doc-without-file/file")
    assert response.status_code == 404


def test_export_bibtex_writes_file_and_returns_summary(client: TestClient, tmp_path) -> None:
    _create_document(client, slug="export-a", title="Export A")
    _create_document(client, slug="export-b", title="Export B")

    response = client.post("/api/research/export-bib")
    assert response.status_code == 200
    body = response.json()
    assert body["entry_count"] == 2
    assert set(body["keys"]) == {"export-a", "export-b"}
    assert body["output_path"]
