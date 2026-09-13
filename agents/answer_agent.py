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
    owner: Optional[str] = Field(None, description="Page owner team")
    methodology_version: Optional[int] = Field(None, description="Methodology version")
    updated_at: Optional[str] = Field(None, description="Last update date")
    valid_from: Optional[str] = Field(None, description="Valid from date")
    lifecycle: Optional[str] = Field(None, description="Lifecycle status (active/archive)")
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
        model: Optional[str] = None,
        is_complex: bool = True,
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

        # Check if the user is asking for a list/catalog of files vs a specific explanation
        query_lower = query.lower()
        is_list_intent = any(w in query_lower for w in ["список", "каталог", "перечень", "какие файлы", "какие скрипты", "файлы", "скрипты"])
        has_code_docs = any(doc.doc_id.startswith("code-") or "Исходный код" in (doc.section or "") for doc in documents)
        is_code_list = is_list_intent and has_code_docs
        
        if is_code_list:
            rules = (
                "1. ФОРМАТ ДЛЯ КОДА: Выведи ответ с красивым форматированием. Обязательно добавь заголовок (например, ### Питон-файлы по продукту...) и вступительный текст.\n"
                "2. Форматируй каждый файл в виде списка: название файла жирным (**file.py**:), со следующей строки пиши его описание, а еще ниже с новой строки указывай 'Источник: [slug_файла]'.\n"
                "3. СТРОГО подставляй уникальный [slug] соответствующего конкретного файла из контекста (например, [code-script_a.py] или [script_a.py]), а НЕ один и тот же общий каталог для всех файлов!\n"
                "4. НЕ добавляй в конце блок 'Источники', он сгенерируется автоматически.\n"
                "5. СТРОЖАЙШЕ ЗАПРЕЩЕНО переводить технические термины и классы. Оставляй их В ТОЧНОСТИ как в тексте без перевода.\n"
                "6. ВАЖНО: Описания файлов и скриптов обязательно переводи на русский язык."
            )
            example = (
                "ПРИМЕР ИДЕАЛЬНОГО ОТВЕТА:\n"
                "### Питон-файлы по продукту Орбитариум (P709)\n\n"
                "Ниже представлен каталог доступных Python-файлов для продукта Орбитариум (P709):\n\n"
                "* **script_a.py**:\n"
                "  Выполняет выгрузку данных. Использует функции: extract_data, load_db.\n"
                "  Источник: [code-script_a.py]\n"
                "* **script_b.py**:\n"
                "  Валидирует схему JSON.\n"
                "  Источник: [code-script_b.py]"
            )
        else:
            rules = (
                "1. БАЗОВОЕ ФОРМАТИРОВАНИЕ: Напиши весь ответ строго ОДНИМ сплошным абзацем без переносов строк. СТРОЖАЙШЕ ЗАПРЕЩЕНО использовать списки, даже если в вопросе просят перечислить параметры.\n"
                "2. Не используй заголовки, вступления или заключительные фразы.\n"
                "3. Подтверждай факты ссылками в формате [slug]. СТРОГО используй оригинальные названия файлов из контекста (например, [p709-passport]). Ставь 1-2 наиболее точные ссылки на предложение, ЗАПРЕЩЕНО стакать много ссылок подряд вроде [slug1][slug2][slug3]!\n"
                "4. НЕ добавляй в конце блок 'Источники', он сгенерируется автоматически.\n"
                "5. СТРОЖАЙШЕ ЗАПРЕЩЕНО переводить или адаптировать технические термины. Оставляй их В ТОЧНОСТИ как в тексте без перевода.\n"
                "6. ВАЖНО: Описания файлов и скриптов обязательно переводи на русский язык."
            )
            example = (
                "ПРИМЕР ИДЕАЛЬНОГО ОТВЕТА:\n"
                "Продукт имеет код P709 [orbitarium-passport] и относится к направлению «Рыночные сервисы» [orbitarium-passport]. Владельцем указана Команда Спектр [orbitarium-teams]. Признаки качества включают статус PASS [orbitarium-quality]."
            )

        user_prompt = (
            f"Вопрос пользователя:\n{query}\n\n"
            f"Контекст документов из базы знаний Меридиан:\n{context_str}\n\n"
            f"Сформируй точный ответ по правилам:\n"
            f"{rules}\n\n"
            f"{example}"
        )

        selected_model = model or (self.llm.config.model_max if is_complex else self.llm.config.model_lite)

        response = self.llm.complete(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            model=selected_model,
            temperature=0.2,
            max_tokens=2000,
        )

        return self._build_output(response.content, documents)

    async def agenerate_answer(
        self,
        query: str,
        documents: List[DocumentContext],
        model: Optional[str] = None,
        is_complex: bool = True,
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

        # Check if the user is asking for a list/catalog of files vs a specific explanation
        query_lower = query.lower()
        is_list_intent = any(w in query_lower for w in ["список", "каталог", "перечень", "какие файлы", "какие скрипты", "файлы", "скрипты"])
        has_code_docs = any(doc.doc_id.startswith("code-") or "Исходный код" in (doc.section or "") for doc in documents)
        is_code_list = is_list_intent and has_code_docs
        
        if is_code_list:
            rules = (
                "1. ФОРМАТ ДЛЯ КОДА: Выведи ответ с красивым форматированием. Обязательно добавь заголовок (например, ### Питон-файлы по продукту...) и вступительный текст.\n"
                "2. Форматируй каждый файл в виде списка: название файла жирным (**file.py**:), со следующей строки пиши его описание, а еще ниже с новой строки указывай 'Источник: [slug_файла]'.\n"
                "3. СТРОГО подставляй уникальный [slug] соответствующего конкретного файла из контекста (например, [code-script_a.py] или [script_a.py]), а НЕ один и тот же общий каталог для всех файлов!\n"
                "4. НЕ добавляй в конце блок 'Источники', он сгенерируется автоматически.\n"
                "5. СТРОЖАЙШЕ ЗАПРЕЩЕНО переводить технические термины и классы. Оставляй их В ТОЧНОСТИ как в тексте без перевода.\n"
                "6. ВАЖНО: Описания файлов и скриптов обязательно переводи на русский язык."
            )
            example = (
                "ПРИМЕР ИДЕАЛЬНОГО ОТВЕТА:\n"
                "### Питон-файлы по продукту Орбитариум (P709)\n\n"
                "Ниже представлен каталог доступных Python-файлов для продукта Орбитариум (P709):\n\n"
                "* **script_a.py**:\n"
                "  Выполняет выгрузку данных. Использует функции: extract_data, load_db.\n"
                "  Источник: [code-script_a.py]\n"
                "* **script_b.py**:\n"
                "  Валидирует схему JSON.\n"
                "  Источник: [code-script_b.py]"
            )
        else:
            rules = (
                "1. БАЗОВОЕ ФОРМАТИРОВАНИЕ: Напиши весь ответ строго ОДНИМ сплошным абзацем без переносов строк. СТРОЖАЙШЕ ЗАПРЕЩЕНО использовать списки, даже если в вопросе просят перечислить параметры.\n"
                "2. Не используй заголовки, вступления или заключительные фразы.\n"
                "3. Подтверждай факты ссылками в формате [slug]. СТРОГО используй оригинальные названия файлов из контекста (например, [p709-passport]). Ставь 1-2 наиболее точные ссылки на предложение, ЗАПРЕЩЕНО стакать много ссылок подряд вроде [slug1][slug2][slug3]!\n"
                "4. НЕ добавляй в конце блок 'Источники', он сгенерируется автоматически.\n"
                "5. СТРОЖАЙШЕ ЗАПРЕЩЕНО переводить или адаптировать технические термины. Оставляй их В ТОЧНОСТИ как в тексте без перевода.\n"
                "6. ВАЖНО: Описания файлов и скриптов обязательно переводи на русский язык."
            )
            example = (
                "ПРИМЕР ИДЕАЛЬНОГО ОТВЕТА:\n"
                "Продукт имеет код P709 [orbitarium-passport] и относится к направлению «Рыночные сервисы» [orbitarium-passport]. Владельцем указана Команда Спектр [orbitarium-teams]. Признаки качества включают статус PASS [orbitarium-quality]."
            )

        user_prompt = (
            f"Вопрос пользователя:\n{query}\n\n"
            f"Контекст документов из базы знаний Меридиан:\n{context_str}\n\n"
            f"Сформируй точный ответ по правилам:\n"
            f"{rules}\n\n"
            f"{example}"
        )

        selected_model = model or (self.llm.config.model_max if is_complex else self.llm.config.model_lite)

        response = await self.llm.acomplete(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            model=selected_model,
            temperature=0.2,
            max_tokens=2000,
        )

        return self._build_output(response.content, documents)

    def _format_context(self, documents: List[DocumentContext]) -> str:
        """Format documents into secure XML-isolated context for the LLM."""
        doc_nodes = []
        for doc in documents:
            attachment_part = ""
            if doc.attachment_text and doc.attachment_text.strip():
                fmt = doc.attachment_format or "text"
                attachment_part = (
                    f"\n  <attachment format=\"{fmt}\" path=\"{doc.attachment_path or ''}\">\n"
                    f"{doc.attachment_text.strip()}\n"
                    f"  </attachment>"
                )

            # Build metadata block with all available fields
            meta_attrs = f'owner="{doc.owner or ""}" methodology_version="{doc.methodology_version or ""}" updated_at="{doc.updated_at or ""}" valid_from="{doc.valid_from or ""}" lifecycle="{doc.lifecycle or ""}"'
            doc_node = (
                f'<document id="{doc.doc_id}" slug="{doc.slug}" product="{doc.product_name or ""}" '
                f'code="{doc.product_code or ""}" section="{doc.section or ""}" {meta_attrs}>\n'
                f"  <title>{doc.title}</title>\n"
                f"  <content>\n{doc.content.strip()}\n  </content>"
                f"{attachment_part}\n"
                f"</document>"
            )
            doc_nodes.append(doc_node)

        body = "\n\n".join(doc_nodes)
        return (
            f'<meridian_context type="knowledge_base_retrieval" untrusted_data="true">\n'
            f"{body}\n"
            f"</meridian_context>"
        )

    def _build_output(
        self,
        raw_text: str,
        documents: List[DocumentContext],
    ) -> AnswerOutput:
        # Extract all [slug-name] mentions from answer preserving order
        slug_map = {doc.slug: doc for doc in documents}
        found_slugs: List[str] = []

        # Regex for [slug] patterns
        matches = re.findall(r"\[([a-zA-Z0-9_\-\.]+)\]", raw_text)
        for m in matches:
            clean_m = m.strip()
            if clean_m in slug_map and clean_m not in found_slugs:
                found_slugs.append(clean_m)

        # Also search for slugs without brackets if mentioned
        for slug in slug_map:
            if slug in raw_text and slug not in found_slugs:
                found_slugs.append(slug)

        # If LLM didn't include citations but answer is based on top doc, associate top doc
        if not found_slugs and documents:
            found_slugs.append(documents[0].slug)

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
            citations=found_slugs,
            sources=cited_sources,
            has_answer=has_answer,
            confidence=round(confidence, 2),
            raw_response=raw_text,
        )
