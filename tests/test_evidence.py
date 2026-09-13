"""Unit tests for Evidence Inspector and EvidenceService."""

import pytest
from fastapi.testclient import TestClient

from app.evidence import EvidenceService, parse_table_data, format_code_with_lines
from app.main import app


@pytest.fixture
def evidence_svc():
    return EvidenceService()


@pytest.fixture
def test_client():
    return TestClient(app)


def test_evidence_service_loaded(evidence_svc):
    assert len(evidence_svc.by_slug) > 0
    assert "iskra-passport" in evidence_svc.by_slug
    assert "P701" in evidence_svc.by_product


def test_evidence_get_passport(evidence_svc):
    ev = evidence_svc.get_evidence("iskra-passport")
    assert ev is not None
    assert ev["slug"] == "iskra-passport"
    assert ev["product_code"] == "P701"
    assert ev["product_name"] == "Искра"
    assert ev["section"] == "Ежедневные расчёты"
    assert ev["methodology_version"] == 2
    assert ev["attachment"] is not None
    assert ev["attachment"]["format"] == "ASM"


def test_evidence_table_parsing():
    sample_csv = "col1;col2;col3\nval1;val2;val3\nval4;val5;val6"
    table = parse_table_data(sample_csv)
    assert table is not None
    assert table["headers"] == ["col1", "col2", "col3"]
    assert len(table["rows"]) == 2
    assert table["rows"][0] == ["val1", "val2", "val3"]

    sample_md_table = "| Name | Role |\n| --- | --- |\n| Alex | Lead |\n| Bob | Dev |"
    md_table = parse_table_data(sample_md_table)
    assert md_table is not None
    assert md_table["headers"] == ["Name", "Role"]
    assert len(md_table["rows"]) == 2


def test_format_code_with_lines():
    code = "mov eax, 1\nret"
    formatted = format_code_with_lines(code, lang="asm")
    assert "line-num" in formatted
    assert "mov eax, 1" in formatted


def test_evidence_citation_enhancement(evidence_svc):
    raw_html = "<p>Для продукта Искра [iskra-passport] определен SLA.</p>"
    enhanced = evidence_svc.enhance_citations(raw_html, active_citations=["iskra-passport"])
    assert "evidence-pill" in enhanced
    assert "openEvidenceInspector('iskra-passport')" in enhanced
    assert "iskra-passport" in enhanced


def test_endpoint_evidence_drawer(test_client):
    res = test_client.get("/evidence/drawer/iskra-passport")
    assert res.status_code == 200
    assert "evidence-content-inner" in res.text
    assert "P701" in res.text
    assert "Текст регламента" in res.text


def test_endpoint_evidence_drawer_404(test_client):
    res = test_client.get("/evidence/drawer/non-existent-random-slug-999")
    assert res.status_code == 404
    assert "Первоисточник не найден" in res.text


def test_endpoint_evidence_api(test_client):
    res = test_client.get("/api/evidence/iskra-passport")
    assert res.status_code == 200
    data = res.json()
    assert data["slug"] == "iskra-passport"
    assert data["product_code"] == "P701"
    assert "doc_html" in data
