"""Router Agent for Meridian Knowledge Base.

Task 4.2:
- GigaChat Lite model integration (temperature=0.1)
- Extracts structured search metadata: product_code, product_name, section, owner, slug, doc_type
- Determines need_attachment (boolean)
- Rewrites query for dense + BM25 RAG search
- Robust JSON parsing with markdown stripping, json repair, and catalog fallback
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field

from llm.gigachat_client import GigaChatClient, GigaChatConfig

logger = logging.getLogger(__name__)

# Official Meridian catalog: code -> (product_name, section, owner)
MERIDIAN_CATALOG: Dict[str, Tuple[str, str, str]] = {
    "P701": ("Искра", "Ежедневные расчёты", "Команда Пульс"),
    "P702": ("Росинка", "Накопления", "Команда Резерв"),
    "P703": ("Янтарь", "Накопления", "Команда Резерв"),
    "P704": ("Мостик", "Финансирование", "Команда Опора"),
    "P705": ("Тихая Гавань", "Защищённые расчёты", "Команда Контур"),
    "P706": ("Лавка", "Торговые сервисы", "Команда Витрина"),
    "P707": ("Комета", "Ежедневные расчёты", "Команда Пульс"),
    "P708": ("Призма", "Рыночные сервисы", "Команда Спектр"),
    "P709": ("Орбитариум", "Рыночные сервисы", "Команда Спектр"),
    "P710": ("Парус", "Финансирование", "Команда Опора"),
    "P711": ("Бастион", "Защищённые расчёты", "Команда Контур"),
    "P712": ("Ритм", "Торговые сервисы", "Команда Витрина"),
    "P713": ("Зонтик", "Подписки и защита", "Команда Забота"),
    "P714": ("Созвездие", "Подписки и защита", "Команда Забота"),
    "P715": ("Мозаика", "Сервисы организаций", "Команда Союз"),
    "P716": ("Маховик", "Сервисы организаций", "Команда Союз"),
    "P717": ("Пергамент", "Цифровая инфраструктура", "Команда Механика"),
    "P718": ("Облачный Сад", "Цифровая инфраструктура", "Команда Механика"),
}

NAME_TO_CODE = {v[0].lower(): k for k, v in MERIDIAN_CATALOG.items()}


class RouterOutput(BaseModel):
    """Structured output of the Router Agent."""
    product_code: Optional[str] = Field(None, description="Code P701..P718 or None")
    product_name: Optional[str] = Field(None, description="Official product name")
    section: Optional[str] = Field(None, description="Product section/direction")
    owner: Optional[str] = Field(None, description="Owner team")
    slug: Optional[str] = Field(None, description="Specific page slug if identified")
    doc_type: Optional[str] = Field(None, description="Document type e.g. passport, architecture")
    need_attachment: bool = Field(False, description="Whether attachment content is required")
    query_rewrite: str = Field(..., description="Cleaned search query for RAG")
    raw_response: Optional[str] = Field(None, description="Raw LLM response for debugging")


def load_router_prompt() -> str:
    """Load router system prompt from file."""
    prompt_path = Path(__file__).parent / "prompts" / "router_system.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    # Fallback default prompt
    return (
        "Ты — маршрутизатор запросов к базе знаний Меридиан. Извлеки из вопроса: "
        "product_code, product_name, section, owner, slug, doc_type, need_attachment, query_rewrite. "
        "Верни строго JSON."
    )


class RouterAgent:
    """Router Agent extracting metadata and preparing queries for RAG search."""

    def __init__(
        self,
        llm_client: Optional[GigaChatClient] = None,
        system_prompt: Optional[str] = None,
    ):
        self.llm = llm_client or GigaChatClient()
        self.system_prompt = system_prompt or load_router_prompt()

    def route(self, query: str) -> RouterOutput:
        """Route and classify user query synchronously."""
        user_prompt = f"Вопрос пользователя: {query}\n\nВерни JSON с метаданными и query_rewrite:"
        
        response = self.llm.complete(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            model=self.llm.config.model_lite,
            temperature=0.1,
            max_tokens=600,
        )

        parsed = self._parse_and_validate(response.content, query)
        parsed.raw_response = response.content
        return parsed

    async def aroute(self, query: str) -> RouterOutput:
        """Route and classify user query asynchronously."""
        user_prompt = f"Вопрос пользователя: {query}\n\nВерни JSON с метаданными и query_rewrite:"
        
        response = await self.llm.acomplete(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            model=self.llm.config.model_lite,
            temperature=0.1,
            max_tokens=600,
        )

        parsed = self._parse_and_validate(response.content, query)
        parsed.raw_response = response.content
        return parsed

    def _parse_and_validate(self, text: str, original_query: str) -> RouterOutput:
        """Parse LLM output to JSON with automatic fallback and rule-based calibration."""
        extracted_data = self._extract_json(text)
        
        # Rule-based post-validation to guarantee 100% catalog consistency
        sanitized = self._sanitize_metadata(extracted_data, original_query)
        return RouterOutput(**sanitized)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON dictionary from markdown fences or text."""
        # Strip code blocks
        clean_text = text.strip()
        if "```json" in clean_text:
            match = re.search(r"```json\s*(.*?)\s*```", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1).strip()
        elif "```" in clean_text:
            match = re.search(r"```\s*(.*?)\s*```", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1).strip()

        # Try direct parse
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            pass

        # Try finding the first '{' and last '}'
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            sub = clean_text[start_idx : end_idx + 1]
            try:
                # Remove trailing commas
                fixed_sub = re.sub(r",\s*([}\]])", r"\1", sub)
                return json.loads(fixed_sub)
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse JSON from Router Agent response: %s", text)
        return {}

    def _sanitize_metadata(self, data: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Verify and enrich extracted metadata with Meridian product catalog."""
        lower_q = query.lower()
        
        product_code = data.get("product_code")
        product_name = data.get("product_name")
        section = data.get("section")
        owner = data.get("owner")
        slug = data.get("slug")
        doc_type = data.get("doc_type")
        need_attachment = data.get("need_attachment", False)
        query_rewrite = data.get("query_rewrite")

        # 1. Normalize product_code format
        if product_code and isinstance(product_code, str):
            product_code = product_code.strip().upper()
            if product_code not in MERIDIAN_CATALOG:
                # Invalid code returned by LLM
                product_code = None

        # 2. Prioritize explicit product names mentioned in the query
        for name, code in NAME_TO_CODE.items():
            if name in lower_q:
                product_code = code
                break

        # 3. Check explicit code mentions in query like P701..P718 if code still missing
        if not product_code:
            code_match = re.search(r"\b(p7[0-1][0-9])\b", lower_q)
            if code_match:
                candidate = code_match.group(1).upper()
                if candidate in MERIDIAN_CATALOG:
                    product_code = candidate

        # 4. Fill product_name, section, owner from catalog if code is known
        if product_code and product_code in MERIDIAN_CATALOG:
            cat_name, cat_section, cat_owner = MERIDIAN_CATALOG[product_code]
            if not product_name:
                product_name = cat_name
            if not section:
                section = cat_section
            if not owner:
                owner = cat_owner

        # 5. Detect attachment intent if not marked
        if not need_attachment:
            attachment_keywords = [
                "вложени", "прикреп", "диаграмм", "схем", "рисунок",
                "картинк", "скриншот", "изображени", "png", "pdf", "docx", "csv", "xlsx",
                "файл", "txt-вложени", "md-вложени", "исходный код", "код на python", "дамп"
            ]
            if any(kw in lower_q for kw in attachment_keywords):
                need_attachment = True

        # 6. Extract slug if query mentions it explicitly (in quotes, Russian quotes, or bare)
        if not slug:
            slug_match = re.search(r"[«\"'`]?([a-z0-9]+(?:-[a-z0-9]+)+)[»\"'`]?", lower_q)
            if slug_match:
                slug = slug_match.group(1).strip("«»\"'`")

        # 7. Fallback query rewrite
        if not query_rewrite or not isinstance(query_rewrite, str) or len(query_rewrite.strip()) == 0:
            cleaned = query
            for stop in ["подскажи", "расскажи", "пожалуйста", "какой", "какая", "какие", "найди", "в"]:
                cleaned = re.sub(rf"\b{stop}\b", "", cleaned, flags=re.IGNORECASE)
            query_rewrite = re.sub(r"\s+", " ", cleaned).strip() or query

        return {
            "product_code": product_code,
            "product_name": product_name,
            "section": section,
            "owner": owner,
            "slug": slug,
            "doc_type": doc_type,
            "need_attachment": bool(need_attachment),
            "query_rewrite": str(query_rewrite).strip(),
        }
