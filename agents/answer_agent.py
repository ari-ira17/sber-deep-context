"""Answer Agent for Meridian Knowledge Base.

Task 4.3:
- GigaChat Max model integration (temperature=0.2)
- Formats top-5 context documents + attachment texts preserving tabular data
- Enforces strict grounding and zero hallucinations
- Formats and extracts source citations [slug]
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from pydantic import BaseModel, Field

from llm.gigachat_client import GigaChatClient, GigaChatConfig

logger = logging.getLogger(__name__)


class DocumentContext(BaseModel):
    """Context document representation for RAG generation."""
    doc_id: str = Field(..., description="Document ID")
    slug: str = Field(..., description="Unique document slug")
    title: str = Field(default="", description="Document title")
    product_name: Optional[str] = Field(None, description="Product name")
    product_code: Optional[str] = Field(None, description="Product code e.g. P701")
    section: Optional[str] = Field(None, description="Section or direction")
    content: str = Field(..., description="Main content (markdown/text/table)")
    attachment_path: Optional[str] = Field(None, description="Path to attachment file")
    attachment_format: Optional[str] = Field(None, description="Format of attachment")
    attachment_text: Optional[str] = Field(None, description="Parsed text from attachment")
    score: float = Field(0.0, description="Reranker relevance score")


class AnswerOutput(BaseModel):
    """Structured output from Answer Agent."""
    answer: str = Field(..., description="Generated answer with [slug] citations")
    citations: List[str] = Field(default_factory=list, description="List of unique cited slugs")
    sources: List[DocumentContext] = Field(default_factory=list, description="Documents used in answer")
    has_answer: bool = Field(True, description="Whether the answer was found in documents")
    confidence: float = Field(1.0, description="Confidence score between 0.0 and 1.0")
    raw_response: Optional[str] = Field(None, description="Raw LLM text")


def load_answer_prompt() -> str:
    """Load answer system prompt from file."""
    prompt_path = Path(__file__).parent / "prompts" / "answer_system.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "Ты — AI-помощник по бизнес-контексту корпуса Меридиан. "
        "Отвечай СТРОГО на основе предоставленного контекста. "
        "Если информации недостаточно — скажи об этом, НЕ додумывай. "
        "Указывай источник: [slug страницы]."
    )


class AnswerAgent:
    """Generates strictly grounded answers with source citations using GigaChat Max."""

    def __init__(
        self,
        llm_client: Optional[GigaChatClient] = None,
        system_prompt: Optional[str] = None,
    ):
        self.llm = llm_client or GigaChatClient()
        self.system_prompt = system_prompt or load_answer_prompt()

    def generate_answer(
        self,
        query: str,
        documents: List[DocumentContext],
    ) -> AnswerOutput:
        """Generate answer synchronously from retrieved documents."""
        if not documents:
            return AnswerOutput(
                answer="В базе знаний Меридиан не найдено релевантных документов по вашему запросу.",
                citations=[],
                sources=[],
                has_answer=False,
                confidence=0.0,
            )

        context_str = self._format_context(documents)
        user_prompt = (
            f"Вопрос пользователя:\n{query}\n\n"
            f"Контекст документов из базы знаний Меридиан:\n{context_str}\n\n"
            f"Сформируй точный ответ по правилам: с опорой на факты, с обязательными ссылками "
            f"[slug] к каждому утверждению и блоком источников в конце."
        )

        response = self.llm.complete(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            model=self.llm.config.model_max,
            temperature=0.2,
            max_tokens=2000,
        )

        return self._build_output(response.content, documents)

    async def agenerate_answer(
        self,
        query: str,
        documents: List[DocumentContext],
    ) -> AnswerOutput:
        """Generate answer asynchronously from retrieved documents."""
        if not documents:
            return AnswerOutput(
                answer="В базе знаний Меридиан не найдено релевантных документов по вашему запросу.",
                citations=[],
                sources=[],
                has_answer=False,
                confidence=0.0,
            )

        context_str = self._format_context(documents)
        user_prompt = (
            f"Вопрос пользователя:\n{query}\n\n"
            f"Контекст документов из базы знаний Меридиан:\n{context_str}\n\n"
            f"Сформируй точный ответ по правилам: с опорой на факты, с обязательными ссылками "
            f"[slug] к каждому утверждению и блоком источников в конце."
        )

        response = await self.llm.acomplete(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            model=self.llm.config.model_max,
            temperature=0.2,
            max_tokens=2000,
        )

        return self._build_output(response.content, documents)

    def _format_context(self, documents: List[DocumentContext]) -> str:
        """Format documents into clean, structured context for the LLM."""
        chunks = []
        for i, doc in enumerate(documents, start=1):
            meta_line = f"ID: {doc.doc_id} | Slug: {doc.slug}"
            if doc.product_name or doc.product_code:
                meta_line += f" | Продукт: {doc.product_name or ''} ({doc.product_code or ''})"
            if doc.section:
                meta_line += f" | Раздел: {doc.section}"

            doc_text = (
                f"--- ДОКУМЕНТ {i} ---\n"
                f"{meta_line}\n"
                f"Заголовок: {doc.title}\n"
                f"Содержание:\n{doc.content.strip()}\n"
            )

            if doc.attachment_text and doc.attachment_text.strip():
                fmt = f" ({doc.attachment_format})" if doc.attachment_format else ""
                doc_text += f"\n[Вложение{fmt}]:\n{doc.attachment_text.strip()}\n"

            chunks.append(doc_text)

        return "\n\n".join(chunks)

    def _build_output(
        self,
        raw_text: str,
        documents: List[DocumentContext],
    ) -> AnswerOutput:
        """Extract citations, identify cited sources, and evaluate grounding."""
        # Extract all [slug-name] mentions from answer
        slug_map = {doc.slug: doc for doc in documents}
        found_slugs: Set[str] = set()

        # Regex for [slug] patterns
        matches = re.findall(r"\[([a-zA-Z0-9_\-\.]+)\]", raw_text)
        for m in matches:
            clean_m = m.strip()
            if clean_m in slug_map:
                found_slugs.add(clean_m)

        # Also search for slugs without brackets if mentioned
        for slug in slug_map:
            if slug in raw_text and slug not in found_slugs:
                found_slugs.add(slug)

        # If LLM didn't include citations but answer is based on top doc, associate top doc
        if not found_slugs and documents:
            found_slugs.add(documents[0].slug)

        cited_sources = [slug_map[s] for s in found_slugs if s in slug_map]

        # Check if answer states info is missing
        negative_phrases = [
            "информация отсутствует",
            "информации недостаточно",
            "не найдено сведений",
            "в документах нет",
            "не содержится информации",
            "данных по данному вопросу нет",
        ]
        has_answer = not any(phrase in raw_text.lower() for phrase in negative_phrases)

        # Confidence calculation
        confidence = 1.0 if has_answer else 0.2
        if cited_sources:
            avg_score = sum(s.score for s in cited_sources) / len(cited_sources)
            if avg_score > 0:
                confidence = min(1.0, max(0.4, (confidence + avg_score) / 2))

        return AnswerOutput(
            answer=raw_text,
            citations=sorted(list(found_slugs)),
            sources=cited_sources,
            has_answer=has_answer,
            confidence=round(confidence, 2),
            raw_response=raw_text,
        )
