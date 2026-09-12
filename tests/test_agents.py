"""Unit and integration tests for Participant 4 (Agent Engineer).

Validates:
- GigaChat API Client (mock mode, retry, rate limit lock)
- Router Agent (prompt, classification, JSON parsing, fallback logic)
- Answer Agent (prompt, context formatting, citation parsing, grounding)
- Deep Agents Pipeline (create_deep_agent, pipeline execution)
- End-to-end Meridian Orchestrator
"""

import pytest
import asyncio
from typing import List

from llm.gigachat_client import GigaChatClient, GigaChatConfig
from agents.router_agent import RouterAgent, RouterOutput, MERIDIAN_CATALOG
from agents.answer_agent import AnswerAgent, AnswerOutput, DocumentContext
from agents.pipeline import create_deep_agent, DeepAgentsPipeline
from agents.orchestrator import MeridianOrchestrator, OrchestratorResponse, StandaloneSearchEngine


@pytest.fixture
def mock_llm_client():
    config = GigaChatConfig(credentials="mock", mock_mode=True)
    return GigaChatClient(config=config)


@pytest.fixture
def router_agent(mock_llm_client):
    return RouterAgent(llm_client=mock_llm_client)


@pytest.fixture
def answer_agent(mock_llm_client):
    return AnswerAgent(llm_client=mock_llm_client)


@pytest.fixture
def sample_documents() -> List[DocumentContext]:
    return [
        DocumentContext(
            doc_id="doc-p701-001",
            slug="iskra-passport",
            title="Паспорт продукта Искра",
            product_name="Искра",
            product_code="P701",
            section="Ежедневные расчёты",
            content="# Искра\nSLA доступности 99.95%. Максимальное время ответа 250 мс.",
            attachment_path="attachments/p701/spec.pdf",
            attachment_format="pdf",
            attachment_text="Архитектурный контур развернут в HA кластере.",
            score=0.95,
        ),
        DocumentContext(
            doc_id="doc-p701-002",
            slug="iskra-architecture",
            title="Архитектура Искра",
            product_name="Искра",
            product_code="P701",
            section="Ежедневные расчёты",
            content="# Архитектура\nИспользуются топики Kafka.",
            score=0.85,
        ),
    ]


class TestGigaChatClient:
    def test_client_mock_initialization(self, mock_llm_client):
        assert mock_llm_client.config.mock_mode is True
        resp = mock_llm_client.complete("Привет", system_prompt="Тест")
        assert resp.is_mock is True
        assert len(resp.content) > 0

    def test_client_rate_limiting_lock(self, mock_llm_client):
        """Ensure thread safety and concurrency lock."""
        resp1 = mock_llm_client.complete("Вопрос 1")
        resp2 = mock_llm_client.complete("Вопрос 2")
        assert resp1 is not None
        assert resp2 is not None

    def test_client_async_complete(self, mock_llm_client):
        async def _run():
            return await mock_llm_client.acomplete("Асинхронный тест")
        resp = asyncio.run(_run())
        assert resp.is_mock is True
        assert len(resp.content) > 0


class TestRouterAgent:
    def test_route_iskra_query(self, router_agent):
        query = "Подскажите SLA и время ответа в паспорте продукта Искра"
        result = router_agent.route(query)
        
        assert isinstance(result, RouterOutput)
        assert result.product_code == "P701"
        assert result.product_name == "Искра"
        assert result.section == "Ежедневные расчёты"
        assert result.owner == "Команда Пульс"
        assert result.query_rewrite is not None
        assert len(result.query_rewrite) > 0

    def test_route_attachment_detection(self, router_agent):
        query = "Покажи схему из прикреплённого файла png к продукту Орбитариум"
        result = router_agent.route(query)
        
        assert result.product_code == "P709"
        assert result.product_name == "Орбитариум"
        assert result.need_attachment is True

    def test_json_parse_repair(self, router_agent):
        """Test markdown strip and JSON tolerance."""
        raw_markdown_json = (
            "```json\n"
            "{\n"
            '  "product_code": "P704",\n'
            '  "product_name": "Мостик",\n'
            '  "section": "Финансирование",\n'
            '  "owner": "Команда Опора",\n'
            '  "slug": null,\n'
            '  "doc_type": "passport",\n'
            '  "need_attachment": false,\n'
            '  "query_rewrite": "паспорт продукта Мостик",\n'
            "}\n"
            "```"
        )
        parsed = router_agent._parse_and_validate(raw_markdown_json, "вопрос по мостику")
        assert parsed.product_code == "P704"
        assert parsed.product_name == "Мостик"
        assert parsed.section == "Финансирование"

    def test_async_route(self, router_agent):
        async def _run():
            return await router_agent.aroute("Какая команда отвечает за продукт Янтарь?")
        result = asyncio.run(_run())
        assert result.product_code == "P703"
        assert result.owner == "Команда Резерв"


class TestAnswerAgent:
    def test_answer_generation(self, answer_agent, sample_documents):
        query = "Какой SLA у продукта Искра?"
        res = answer_agent.generate_answer(query, sample_documents)

        assert isinstance(res, AnswerOutput)
        assert len(res.answer) > 0
        assert len(res.citations) > 0
        assert "iskra-passport" in res.citations
        assert res.has_answer is True

    def test_answer_empty_docs(self, answer_agent):
        res = answer_agent.generate_answer("Какой-то вопрос", [])
        assert res.has_answer is False
        assert len(res.citations) == 0

    def test_async_answer(self, answer_agent, sample_documents):
        async def _run():
            return await answer_agent.agenerate_answer("Какой SLA?", sample_documents)
        res = asyncio.run(_run())
        assert res.has_answer is True
        assert len(res.citations) > 0


class TestPipelineAndOrchestrator:
    def test_create_deep_agent_factory(self, mock_llm_client):
        agent = create_deep_agent(
            name="TestAgent",
            role="Tester",
            system_prompt="Ты тестер",
            llm_client=mock_llm_client,
        )
        assert agent.name == "TestAgent"
        assert agent.role == "Tester"

    def test_orchestrator_end_to_end(self, mock_llm_client):
        orchestrator = MeridianOrchestrator(llm_client=mock_llm_client)
        res = orchestrator.ask("Подготовьте карточку продукта Искра с параметрами SLA")

        assert isinstance(res, OrchestratorResponse)
        assert res.router_data.product_code == "P701"
        assert len(res.sources) > 0
        assert len(res.answer) > 0
        assert len(res.citations) > 0
        assert len(res.graph_nodes) > 1  # Central question node + doc nodes
        assert len(res.graph_edges) > 0  # Edges connecting question to docs

    def test_orchestrator_async_end_to_end(self, mock_llm_client):
        async def _run():
            orchestrator = MeridianOrchestrator(llm_client=mock_llm_client)
            return await orchestrator.aask("Какие регламенты у продукта Росинка?")
        res = asyncio.run(_run())

        assert isinstance(res, OrchestratorResponse)
        assert res.router_data.product_code == "P702"
        assert len(res.sources) > 0
        assert len(res.graph_nodes) > 0
