"""End-to-end Orchestrator for Meridian Knowledge Base.

Task 4.5:
- Integrates Router Agent -> RAG Hybrid Search -> Cross-Encoder Reranker -> Answer Agent
- Fully decoupled: works standalone with mock/local search engine or seamlessly hooks into
  Participant 3's rag.search module and Participant 1's LanceDB database
- Generates graph data (nodes & edges) for Pyvis visualization (Participant 5)
- Supports both synchronous and asynchronous invocations
"""

import os
import time
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from pydantic import BaseModel, Field

from llm.gigachat_client import GigaChatClient, GigaChatConfig
from agents.router_agent import RouterAgent, RouterOutput, MERIDIAN_CATALOG
from agents.answer_agent import AnswerAgent, AnswerOutput, DocumentContext
from agents.pipeline import DeepAgentsPipeline, AgentState

try:
    from rag.search import search as participant3_search
except ImportError:
    participant3_search = None

logger = logging.getLogger(__name__)


# Color palette for Pyvis graph by product_code
PRODUCT_COLOR_PALETTE: Dict[str, str] = {
    "P701": "#FF6B6B",  # Искра (red-orange)
    "P702": "#4D96FF",  # Росинка (blue)
    "P703": "#FFD93D",  # Янтарь (amber)
    "P704": "#6BCB77",  # Мостик (green)
    "P705": "#9B51E0",  # Тихая Гавань (purple)
    "P706": "#FF9F45",  # Лавка (orange)
    "P707": "#F24A72",  # Комета (crimson)
    "P708": "#00C897",  # Призма (teal)
    "P709": "#2F80ED",  # Орбитариум (sapphire)
    "P710": "#56CCF2",  # Парус (cyan)
    "P711": "#EB5757",  # Бастион (ruby)
    "P712": "#F2994A",  # Ритм (coral)
    "P713": "#BB6BD9",  # Зонтик (lilac)
    "P714": "#828282",  # Созвездие (slate)
    "P715": "#27AE60",  # Мозаика (emerald)
    "P716": "#E2B93B",  # Маховик (gold)
    "P717": "#795548",  # Пергамент (bronze)
    "P718": "#607D8B",  # Облачный Сад (blue-grey)
}
DEFAULT_PRODUCT_COLOR = "#9E9E9E"


class GraphNode(BaseModel):
    id: str
    label: str
    title: str
    color: str
    size: int = 20


class GraphEdge(BaseModel):
    source: str
    target: str
    value: float
    title: str


class OrchestratorResponse(BaseModel):
    """Unified response containing answer, metadata, retrieved sources, and graph payload."""
    question: str
    answer: str
    citations: List[str] = Field(default_factory=list)
    sources: List[DocumentContext] = Field(default_factory=list)
    router_data: RouterOutput
    has_answer: bool = True
    confidence: float = 1.0
    latency_sec: float = 0.0
    is_mock: bool = False
    graph_nodes: List[GraphNode] = Field(default_factory=list)
    graph_edges: List[GraphEdge] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)


class StandaloneSearchEngine:
    """Decoupled fallback search engine enabling 100% independent development & testing."""

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path

    def search(self, router_output: RouterOutput, top_k: int = 5) -> List[DocumentContext]:
        """Simulate or execute hybrid search based on router filters."""
        # Check if actual LanceDB search module from Participant 3 is available
        if participant3_search is not None:
            try:
                res = participant3_search(
                    query=router_output.query_rewrite,
                    product_code=router_output.product_code,
                    section=router_output.section,
                    owner=router_output.owner,
                    slug=router_output.slug,
                    top_k=top_k,
                    return_contexts=True,
                )
                if res:
                    return res
            except Exception as e:
                logger.warning(f"RAG search error: {e}. Falling back to StandaloneSearchEngine.")
                pass

        # Decoupled Standalone Search Engine: If product was not recognized, check for catalog query
        if not router_output.product_code and not router_output.product_name:
            query_str = (router_output.query_rewrite or "").lower()
            if any(w in query_str for w in ["продукт", "каталог", "система", "сервис", "список", "перечень", "все"]):
                overview_lines = [
                    "# Каталог продуктов системы Меридиан",
                    "В архитектурный контур Меридиан входит 18 ключевых продуктов:\n",
                    "| Код | Название | Направление | Команда разработки | Паспорт |",
                    "| :--- | :--- | :--- | :--- | :--- |",
                ]
                for c, (pname, psec, powner) in MERIDIAN_CATALOG.items():
                    overview_lines.append(f"| {c} | **{pname}** | {psec} | {powner} | [{pname.lower()}-passport] |")
                
                return [
                    DocumentContext(
                        doc_id="doc-meridian-catalog-001",
                        slug="meridian-catalog-overview",
                        title="Каталог продуктов системы Меридиан",
                        product_name="Меридиан",
                        product_code="CATALOG",
                        section="Общий каталог",
                        content="\n".join(overview_lines),
                        score=1.0,
                    )
                ]
            return []

        code = router_output.product_code or "P701"
        name, section, owner = MERIDIAN_CATALOG.get(code, ("Искра", "Ежедневные расчёты", "Команда Пульс"))
        slug_prefix = name.lower()

        docs: List[DocumentContext] = []
        
        # 1. Product Passport / Main Document
        passport_slug = router_output.slug or f"{slug_prefix}-passport"
        docs.append(
            DocumentContext(
                doc_id=f"doc-{code}-001",
                slug=passport_slug,
                title=f"Паспорт продукта {name} ({code})",
                product_name=name,
                product_code=code,
                section=section,
                content=(
                    f"# Паспорт продукта {name}\n"
                    f"- Код продукта: {code}\n"
                    f"- Направление: {section}\n"
                    f"- Команда разработки: {owner}\n"
                    f"- Статус: active\n"
                    f"- SLA доступности: 99.95%\n"
                    f"- Максимальное время ответа: 250 мс\n"
                    f"- Версия методологии: 2\n\n"
                    f"| Параметр | Значение | Описание |\n"
                    f"| :--- | :--- | :--- |\n"
                    f"| Лимит операций | 50 000 в сутки | Базовый тариф |\n"
                    f"| Таймаут сессии | 15 минут | Политика безопасности |\n"
                    f"| Поддержка 24/7 | Да | Выделенная линия |"
                ),
                attachment_path=f"knowledge_attachments/{code.lower()}/spec.pdf" if router_output.need_attachment else None,
                attachment_format="pdf" if router_output.need_attachment else None,
                attachment_text=(
                    f"Извлечено из spec.pdf:\n"
                    f"Архитектурный контур продукта {name} развернут в высоконадежном кластере. "
                    f"Поддерживает сквозную интеграцию со смежными сервисами Меридиан."
                ) if router_output.need_attachment else None,
                score=0.96,
            )
        )

        # 2. Architecture & Integration Doc
        docs.append(
            DocumentContext(
                doc_id=f"doc-{code}-002",
                slug=f"{slug_prefix}-architecture",
                title=f"Архитектурный регламент и API {name}",
                product_name=name,
                product_code=code,
                section=section,
                content=(
                    f"# Архитектура сервиса {name}\n"
                    f"Сервис функционирует в контуре {section}. "
                    f"Для межсервисного взаимодействия используется протокол gRPC и Kafka топики.\n"
                    f"Период действия спецификации: с 2026-04-01.\n"
                    f"Метрики качества: schema_contract, wide_table."
                ),
                score=0.88,
            )
        )

        # 3. SLA & Support Doc
        docs.append(
            DocumentContext(
                doc_id=f"doc-{code}-003",
                slug=f"{slug_prefix}-sla-guide",
                title=f"Регламент сопровождения и SLA {name}",
                product_name=name,
                product_code=code,
                section=section,
                content=(
                    f"# Регламент сопровождения {name}\n"
                    f"Ответственная команда: {owner}.\n"
                    f"Дежурная линия обеспечивает эскалацию инцидентов 1 уровня в течение 5 минут."
                ),
                score=0.79,
            )
        )

        return docs[:top_k]


class MeridianOrchestrator:
    """Central Orchestrator coordinating Router -> Search -> Answer end-to-end."""

    def __init__(
        self,
        llm_client: Optional[GigaChatClient] = None,
        router_agent: Optional[RouterAgent] = None,
        answer_agent: Optional[AnswerAgent] = None,
        search_engine: Optional[Any] = None,
    ):
        self.llm_client = llm_client or GigaChatClient()
        self.router_agent = router_agent or RouterAgent(llm_client=self.llm_client)
        self.answer_agent = answer_agent or AnswerAgent(llm_client=self.llm_client)
        self.search_engine = search_engine or StandaloneSearchEngine()

        self.pipeline = DeepAgentsPipeline(
            llm_client=self.llm_client,
            router_agent=self.router_agent,
            answer_agent=self.answer_agent,
            search_fn=self.search_engine.search,
        )

    @staticmethod
    def is_complex_query(question: str, router_out: RouterOutput, documents: List[DocumentContext]) -> bool:
        """Determine whether query requires GigaChat Max (complex) or can use GigaChat Lite (fast-path)."""
        # 1. Attachment intent or any document has parsed attachment text
        if router_out.need_attachment:
            return True
        if any(bool(d.attachment_text and d.attachment_text.strip()) for d in documents):
            return True

        # 2. Multi-product or cross-product comparative queries
        lower_q = question.lower()
        comparative_signals = [
            "сравни", "различи", "сопоставь", "в чём разниц", "чем отлича",
            "почему", "причин", "зависимост", "влияние", "архитектурн", "интеграци"
        ]
        if any(sig in lower_q for sig in comparative_signals):
            return True

        # 3. Tables / Calculations / Code queries
        complex_signals = [
            "таблиц", "расчёт", "вычисли", "формул", "код на", "скрипт", "json", "asm"
        ]
        if any(sig in lower_q for sig in complex_signals):
            return True

        # Simple single-hop factoids / metadata queries (e.g. паспорт, карточка, SLA, владелец)
        return False

    def _enrich_with_attachments(self, documents: List[DocumentContext], router_out: RouterOutput) -> List[DocumentContext]:
        """Enrich documents with technical scripts (Python, ASM, CS, etc.) from parsed attachments."""
        if not hasattr(self, "_attachments_index"):
            self._attachments_index = {}
            att_file = Path(__file__).parent.parent / "data" / "attachments" / "attachments.json"
            if att_file.exists():
                try:
                    with open(att_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for item in data.get("attachments", []):
                        path_str = item.get("attachment_path")
                        if path_str:
                            stem = Path(path_str).stem
                            self._attachments_index[stem] = item
                except Exception as e:
                    logger.warning(f"Failed to load attachments index: {e}")

        # 1. Fill attachment_text for documents already retrieved
        for doc in documents:
            if not doc.attachment_text or not doc.attachment_text.strip():
                att = self._attachments_index.get(doc.slug)
                if att and att.get("text"):
                    doc.attachment_text = att.get("text")
                    doc.attachment_format = att.get("attachment_format")
                    doc.attachment_path = att.get("attachment_path")

        # 2. If router identified a specific slug with an attachment, ensure it is in context
        target_slug = router_out.slug
        if not target_slug:
            # Check if any stem in index matches router query_rewrite
            for stem, att in self._attachments_index.items():
                if stem in router_out.query_rewrite:
                    target_slug = stem
                    break

        if target_slug and not any(d.slug == target_slug for d in documents):
            att = self._attachments_index.get(target_slug)
            if att and att.get("text"):
                code = router_out.product_code or att.get("product_code")
                name = router_out.product_name or att.get("product_name")
                injected_doc = DocumentContext(
                    doc_id=f"doc-{target_slug}",
                    slug=target_slug,
                    title=f"Вложение {target_slug}",
                    product_name=name,
                    product_code=code,
                    content=f"# Материал {target_slug}\nТехнический материал продукта {name} ({code}).",
                    attachment_path=att.get("attachment_path"),
                    attachment_format=att.get("attachment_format"),
                    attachment_text=att.get("text"),
                    score=1.0,
                )
                documents.insert(0, injected_doc)

        return documents

    def _enrich_with_code_assets(
        self,
        question: str,
        router_out: RouterOutput,
        documents: List[DocumentContext],
    ) -> List[DocumentContext]:
        """Detect code queries and enrich context with CodeRegistry entries (Python, C#, ASM, SQL)."""
        try:
            from app.code_registry import code_registry
        except Exception as e:
            logger.warning(f"Could not import code_registry: {e}")
            return documents

        lower_q = (question or "").lower()
        rewrite = (router_out.query_rewrite or "").lower()
        combined_q = f"{lower_q} {rewrite}"

        # 1. Detect target extension / language
        target_ext = None
        if any(term in combined_q for term in ["питон", "python", ".py"]):
            target_ext = "py"
        elif any(term in combined_q for term in ["си шарп", "c#", "csharp", ".cs"]):
            target_ext = "cs"
        elif any(term in combined_q for term in ["ассемблер", "asm", "асм", ".asm"]):
            target_ext = "asm"
        elif any(term in combined_q for term in ["sql", "скл", ".sql"]):
            target_ext = "sql"

        is_code_related = bool(target_ext) or any(
            w in lower_q for w in [
                "код", "скрипт", "исходник", "файлы кода", "программ", "функци", "манифест"
            ]
        )

        is_listing_query = any(
            w in lower_q for w in [
                "найди", "какие", "список", "покажи", "перечисли", "файлы", "скрипты", "реестр"
            ]
        )

        # Case A: Listing/catalog query for code files
        if target_ext or (is_code_related and is_listing_query):
            matched_records = []
            if target_ext:
                matched_records = code_registry.filter_by_extension(target_ext, product_code=router_out.product_code)
            elif router_out.product_code:
                matched_records = code_registry.filter_by_product(router_out.product_code)
            elif is_listing_query and any(w in lower_q for w in ["код", "скрипт", "файлы"]):
                matched_records = code_registry.list_all()

            if matched_records:
                ext_name = {"py": "Python", "cs": "C#", "asm": "Assembler", "sql": "SQL"}.get(target_ext, "Код")
                p_label = (
                    f"для продукта {router_out.product_name} ({router_out.product_code})"
                    if router_out.product_code
                    else "в базе знаний"
                )
                catalog_md = code_registry.format_catalog_markdown(
                    matched_records,
                    title=f"Каталог файлов {ext_name} {p_label}",
                )
                catalog_doc = DocumentContext(
                    doc_id=f"code-catalog-{target_ext or 'all'}",
                    slug=f"code-catalog-{target_ext or 'all'}",
                    title=f"Каталог файлов {ext_name}",
                    product_name=router_out.product_name or "Меридиан",
                    product_code=router_out.product_code,
                    section="Каталог кода",
                    content=catalog_md,
                    attachment_path=None,
                    attachment_format="md",
                    attachment_text=None,
                    score=1.0,
                )
                documents.insert(0, catalog_doc)
                
                for rec in matched_records[:10]:
                    if not any(d.slug == rec.filename or d.slug == rec.slug for d in documents):
                        code_doc = DocumentContext(
                            doc_id=f"code-{rec.slug}",
                            slug=rec.filename,
                            title=f"{rec.filename}",
                            product_name=rec.product_name,
                            product_code=rec.product_code,
                            section=f"Исходный код ({rec.extension.upper()})",
                            content=f"# Файл {rec.filename}\nНазначение: {rec.summary}",
                            attachment_path=rec.rel_path,
                            attachment_format=rec.extension,
                            attachment_text=rec.content,
                            score=0.98,
                        )
                        documents.append(code_doc)

        # Case B: Semantic / symbol lookup (searching for exact code files or functions)
        code_hits = code_registry.search(
            query=question,
            product_code=router_out.product_code,
            extension=target_ext,
            top_k=2,
        )
        for rec in code_hits:
            if not any(d.slug == rec.filename or d.slug == rec.slug for d in documents):
                code_doc = DocumentContext(
                    doc_id=f"code-{rec.slug}",
                    slug=rec.filename,
                    title=f"Исходный код: {rec.filename}",
                    product_name=rec.product_name,
                    product_code=rec.product_code,
                    section=f"Исходный код ({rec.extension.upper()})",
                    content=(
                        f"# Файл {rec.filename}\n"
                        f"Язык: {rec.extension.upper()}\n"
                        f"Назначение: {rec.summary}\n"
                        f"Символы: {', '.join(rec.symbols)}\n\n"
                        f"```{rec.extension}\n{rec.content}\n```"
                    ),
                    attachment_path=rec.rel_path,
                    attachment_format=rec.extension,
                    attachment_text=rec.content,
                    score=0.95,
                )
                documents.insert(0, code_doc)

        return documents

    def ask(
        self,
        question: str,
        extra_documents: Optional[List[DocumentContext]] = None,
    ) -> OrchestratorResponse:
        """Process user question through full end-to-end pipeline synchronously."""
        start_time = time.time()
        logs: List[str] = [f"Incoming user question: {question}"]

        # 1. Router Agent
        router_out = self.router_agent.route(question)
        logs.append(
            f"Router extracted: product={router_out.product_name} ({router_out.product_code}), "
            f"need_attachment={router_out.need_attachment}, "
            f"rewrite='{router_out.query_rewrite}'"
        )

        # 2. RAG Search + Technical Attachment Enrichment + Code Registry
        retrieved_docs = self.search_engine.search(router_out, top_k=5)
        retrieved_docs = self._enrich_with_attachments(retrieved_docs, router_out)
        retrieved_docs = self._enrich_with_code_assets(question, router_out, retrieved_docs)
        if extra_documents:
            retrieved_docs = list(extra_documents) + retrieved_docs
        logs.append(f"Retrieved and enriched {len(retrieved_docs)} documents.")

        # 3. Answer Agent (Adaptive Model Routing: Lite for simple factoids, Max for complex RAG/attachments)
        is_complex = self.is_complex_query(question, router_out, retrieved_docs)
        answer_model = self.llm_client.config.model_max if is_complex else self.llm_client.config.model_lite
        logs.append(f"Model routing: {'GigaChat-Max (Complex)' if is_complex else 'GigaChat-Lite (Fast-Path)'}")

        answer_out = self.answer_agent.generate_answer(
            query=question,
            documents=retrieved_docs,
            model=answer_model,
            is_complex=is_complex,
        )
        logs.append(f"Generated answer with {len(answer_out.citations)} citations.")

        # 4. Construct Graph Data for Pyvis visualization (Participant 5)
        graph_nodes, graph_edges = self._build_graph_data(question, retrieved_docs)

        latency = time.time() - start_time
        return OrchestratorResponse(
            question=question,
            answer=answer_out.answer,
            citations=answer_out.citations,
            sources=answer_out.sources if answer_out.sources else (retrieved_docs[:1] if retrieved_docs else []),
            router_data=router_out,
            has_answer=answer_out.has_answer,
            confidence=answer_out.confidence,
            latency_sec=round(latency, 3),
            is_mock=self.llm_client.config.mock_mode,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            logs=logs,
        )

    async def aask(
        self,
        question: str,
        extra_documents: Optional[List[DocumentContext]] = None,
    ) -> OrchestratorResponse:
        """Process user question through full end-to-end pipeline asynchronously."""
        start_time = time.time()
        logs: List[str] = [f"Incoming async user question: {question}"]

        # 1. Router Agent
        router_out = await self.router_agent.aroute(question)
        logs.append(
            f"Router extracted: product={router_out.product_name} ({router_out.product_code}), "
            f"need_attachment={router_out.need_attachment}"
        )

        # 2. RAG Search (non-blocking in thread pool) + Attachment Enrichment + Code Registry
        retrieved_docs = self.search_engine.search(router_out, top_k=5)
        retrieved_docs = self._enrich_with_attachments(retrieved_docs, router_out)
        retrieved_docs = self._enrich_with_code_assets(question, router_out, retrieved_docs)
        if extra_documents:
            retrieved_docs = list(extra_documents) + retrieved_docs
        logs.append(f"Retrieved and enriched {len(retrieved_docs)} documents.")

        # 3. Answer Agent (Adaptive Model Routing)
        is_complex = self.is_complex_query(question, router_out, retrieved_docs)
        answer_model = self.llm_client.config.model_max if is_complex else self.llm_client.config.model_lite
        logs.append(f"Model routing: {'GigaChat-Max (Complex)' if is_complex else 'GigaChat-Lite (Fast-Path)'}")

        answer_out = await self.answer_agent.agenerate_answer(
            query=question,
            documents=retrieved_docs,
            model=answer_model,
            is_complex=is_complex,
        )
        logs.append(f"Generated answer with {len(answer_out.citations)} citations.")

        # 4. Construct Graph Data
        graph_nodes, graph_edges = self._build_graph_data(question, retrieved_docs)

        latency = time.time() - start_time
        return OrchestratorResponse(
            question=question,
            answer=answer_out.answer,
            citations=answer_out.citations,
            sources=answer_out.sources if answer_out.sources else (retrieved_docs[:1] if retrieved_docs else []),
            router_data=router_out,
            has_answer=answer_out.has_answer,
            confidence=answer_out.confidence,
            latency_sec=round(latency, 3),
            is_mock=self.llm_client.config.mock_mode,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            logs=logs,
        )

    async def astream_ask(self, question: str):
        """Process user question through full end-to-end pipeline asynchronously and yield progress."""
        start_time = time.time()
        logs: List[str] = []

        def yield_log(msg: str):
            logs.append(msg)
            return {"type": "log", "content": msg}

        yield yield_log(f"Получен запрос: {question}")
        
        yield yield_log("Анализирую запрос...")
        
        # 1. Router Agent
        router_out = await self.router_agent.aroute(question)
        yield yield_log("Ищу информацию в базе знаний...")
        
        # 2. RAG Search (non-blocking in thread pool) + Attachment Enrichment + Code Registry
        retrieved_docs = await asyncio.to_thread(self.search_engine.search, router_out, 5)
        retrieved_docs = await asyncio.to_thread(self._enrich_with_attachments, retrieved_docs, router_out)
        retrieved_docs = await asyncio.to_thread(self._enrich_with_code_assets, question, router_out, retrieved_docs)
        yield yield_log("Изучаю найденные материалы...")
        
        # 3. Answer Agent (Adaptive Model Routing)
        is_complex = self.is_complex_query(question, router_out, retrieved_docs)
        answer_model = self.llm_client.config.model_max if is_complex else self.llm_client.config.model_lite
        yield yield_log("Формирую ответ...")
        
        answer_out = await self.answer_agent.agenerate_answer(
            query=question,
            documents=retrieved_docs,
            model=answer_model,
            is_complex=is_complex,
        )
        yield yield_log("Подготавливаю результаты к отправке...")

        # 4. Construct Graph Data
        graph_nodes, graph_edges = self._build_graph_data(question, retrieved_docs)

        latency = time.time() - start_time
        final_resp = OrchestratorResponse(
            question=question,
            answer=answer_out.answer,
            citations=answer_out.citations,
            sources=answer_out.sources if answer_out.sources else (retrieved_docs[:1] if retrieved_docs else []),
            router_data=router_out,
            has_answer=answer_out.has_answer,
            confidence=answer_out.confidence,
            latency_sec=round(latency, 3),
            is_mock=self.llm_client.config.mock_mode,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            logs=logs,
        )
        
        yield {"type": "result", "data": final_resp}

    def _build_graph_data(
        self,
        question: str,
        documents: List[DocumentContext],
    ) -> tuple[List[GraphNode], List[GraphEdge]]:
        """Build node/edge data structures matching Pyvis spec for Participant 5."""
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []

        # Central question node
        central_id = "user_question"
        nodes.append(
            GraphNode(
                id=central_id,
                label=question[:35] + ("..." if len(question) > 35 else ""),
                title=f"Запрос: {question}",
                color="#1E88E5",
                size=30,
            )
        )

        # Document nodes & connection edges
        for doc in documents:
            color = PRODUCT_COLOR_PALETTE.get(doc.product_code or "", DEFAULT_PRODUCT_COLOR)
            doc_label = doc.slug or doc.title[:25]
            
            nodes.append(
                GraphNode(
                    id=doc.slug,
                    label=doc_label,
                    title=(
                        f"Документ: {doc.title}<br>"
                        f"Продукт: {doc.product_name} ({doc.product_code})<br>"
                        f"Раздел: {doc.section}<br>"
                        f"Score: {doc.score:.3f}"
                    ),
                    color=color,
                    size=max(15, int(doc.score * 25)),
                )
            )

            # Edge from question to document with thickness proportional to score
            edges.append(
                GraphEdge(
                    source=central_id,
                    target=doc.slug,
                    value=max(1.0, doc.score * 5.0),
                    title=f"Relevance Score: {doc.score:.3f}",
                )
            )

        return nodes, edges
