"""GigaChat API Client with rate limiting, retry mechanism, and multi-model support.

Addresses Hackathon Case 2 requirements:
- 1-stream rate limiting (strictly single concurrency to prevent 429 and conform to SBER rules)
- Automatic retry with exponential backoff
- GigaChat Lite (Router), GigaChat Max (Answer), Pro/Ultra support
- Offline Mock Mode for independent local development and automated testing
"""

import os
import re
import time
import json
import logging
import threading
import asyncio
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

try:
    from gigachat import GigaChat
    from gigachat.models import Chat, Messages, MessagesRole
    GIGACHAT_SDK_AVAILABLE = True
except ImportError:
    GIGACHAT_SDK_AVAILABLE = False

try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv("api.env")
except ImportError:
    pass

logger = logging.getLogger(__name__)


class GigaChatConfig(BaseModel):
    """Configuration for GigaChat client."""
    credentials: Optional[str] = Field(
        default_factory=lambda: os.getenv("GIGACHAT_CREDENTIALS", "")
    )
    scope: str = Field(
        default_factory=lambda: os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    )
    verify_ssl_certs: bool = Field(
        default_factory=lambda: os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "false").lower() in ("true", "1", "yes")
    )
    model_lite: str = Field(
        default_factory=lambda: os.getenv("GIGACHAT_MODEL_LITE", "GigaChat")
    )
    model_max: str = Field(
        default_factory=lambda: os.getenv("GIGACHAT_MODEL_MAX", "GigaChat-Max")
    )
    model_pro: str = Field(
        default_factory=lambda: os.getenv("GIGACHAT_MODEL_PRO", "GigaChat-Pro")
    )
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 2.0
    backoff_factor: float = 2.0
    mock_mode: bool = False


class GigaChatResponse(BaseModel):
    """Unified response object."""
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_sec: float = 0.0
    is_mock: bool = False


class GigaChatClient:
    """Production-grade client for GigaChat API with single-stream concurrency lock."""

    _sync_lock = threading.Lock()
    _async_lock: Optional[asyncio.Lock] = None

    def __init__(self, config: Optional[GigaChatConfig] = None):
        self.config = config or GigaChatConfig()
        
        # Determine if we should force mock mode
        if not self.config.credentials or self.config.credentials.lower() == "mock" or not GIGACHAT_SDK_AVAILABLE:
            self.config.mock_mode = True
            logger.info("GigaChatClient running in MOCK mode (no credentials or mock requested).")
        else:
            self.config.mock_mode = False

        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None and not self.config.mock_mode:
            if not GIGACHAT_SDK_AVAILABLE:
                raise RuntimeError("gigachat package is not installed.")
            self._client = GigaChat(
                credentials=self.config.credentials,
                scope=self.config.scope,
                verify_ssl_certs=self.config.verify_ssl_certs,
                timeout=self.config.timeout,
            )
        return self._client

    @classmethod
    def _get_async_lock(cls) -> asyncio.Lock:
        if cls._async_lock is None:
            cls._async_lock = asyncio.Lock()
        return cls._async_lock

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1500,
    ) -> GigaChatResponse:
        """Synchronous completion with 1-stream rate limiting and retry."""
        selected_model = model or self.config.model_lite
        
        # Ensure there is an event loop in this thread (especially when called via run_in_executor)
        # because the gigachat SDK (or its underlying httpx client) may rely on get_event_loop().
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        # 1-stream global lock across all threads
        with self._sync_lock:
            start_time = time.time()
            if self.config.mock_mode:
                content = self._mock_completion(prompt, system_prompt, selected_model)
                duration = time.time() - start_time
                return GigaChatResponse(
                    content=content,
                    model=selected_model,
                    prompt_tokens=len(prompt) // 4,
                    completion_tokens=len(content) // 4,
                    total_tokens=(len(prompt) + len(content)) // 4,
                    duration_sec=duration,
                    is_mock=True,
                )

            # Execution with retry loop
            delay = self.config.retry_delay
            last_error: Optional[Exception] = None

            for attempt in range(1, self.config.max_retries + 1):
                try:
                    client = self._get_client()
                    messages = []
                    if system_prompt:
                        messages.append(Messages(role=MessagesRole.SYSTEM, content=system_prompt))
                    messages.append(Messages(role=MessagesRole.USER, content=prompt))

                    payload = Chat(
                        model=selected_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    response = client.chat(payload)
                    duration = time.time() - start_time

                    content = response.choices[0].message.content
                    usage = getattr(response, "usage", None)
                    p_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
                    c_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
                    t_tokens = getattr(usage, "total_tokens", 0) if usage else 0

                    return GigaChatResponse(
                        content=content,
                        model=selected_model,
                        prompt_tokens=p_tokens,
                        completion_tokens=c_tokens,
                        total_tokens=t_tokens,
                        duration_sec=duration,
                        is_mock=False,
                    )
                except Exception as ex:
                    last_error = ex
                    err_str = str(ex)
                    logger.warning(
                        "GigaChat API error on attempt %d/%d for model %s: %s",
                        attempt, self.config.max_retries, selected_model, err_str
                    )
                    # Auto-heal: if model name is rejected (e.g. corporate B2B account without base GigaChat), discover available models
                    if "no such model" in err_str.lower() or "404" in err_str:
                        try:
                            client = self._get_client()
                            models_resp = client.get_models()
                            avail = [m.id for m in getattr(models_resp, "data", [])]
                            if avail:
                                logger.info("Available GigaChat models for this credentials: %s", avail)
                                preferred = ["GigaChat-Pro", "GigaChat-Max", "GigaChat", "GigaChat-Plus"]
                                for cand in preferred:
                                    if cand in avail and cand != selected_model:
                                        logger.info("Auto-switching model from %s to %s", selected_model, cand)
                                        selected_model = cand
                                        break
                        except Exception as m_err:
                            logger.debug("Failed to auto-discover models: %s", m_err)

                    if attempt < self.config.max_retries:
                        time.sleep(delay)
                        delay *= self.config.backoff_factor

            # Fallback to mock if API permanently failed
            logger.error("All GigaChat API attempts failed (%s). Falling back to mock response.", last_error)
            content = self._mock_completion(prompt, system_prompt, selected_model)
            return GigaChatResponse(
                content=content,
                model=selected_model,
                duration_sec=time.time() - start_time,
                is_mock=True,
            )

    async def acomplete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1500,
    ) -> GigaChatResponse:
        """Asynchronous completion with 1-stream rate limiting."""
        lock = self._get_async_lock()
        async with lock:
            # Run the synchronous complete method in an executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                self.complete,
                prompt,
                system_prompt,
                model,
                temperature,
                max_tokens,
            )

    def _mock_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Intelligent mock completion for local testing and validation."""
        lower_prompt = prompt.lower()
        lower_sys = (system_prompt or "").lower()

        # Is this a Router query?
        if "маршрутизатор" in lower_sys or "product_code" in lower_sys or "query_rewrite" in lower_sys:
            # Catalog of 18 products
            catalog = [
                ("p701", "искра", "Ежедневные расчёты", "Команда Пульс"),
                ("p702", "росинка", "Накопления", "Команда Резерв"),
                ("p703", "янтарь", "Накопления", "Команда Резерв"),
                ("p704", "мостик", "Финансирование", "Команда Опора"),
                ("p705", "тихая гавань", "Защищённые расчёты", "Команда Контур"),
                ("p706", "лавка", "Торговые сервисы", "Команда Витрина"),
                ("p707", "комета", "Ежедневные расчёты", "Команда Пульс"),
                ("p708", "призма", "Рыночные сервисы", "Команда Спектр"),
                ("p709", "орбитариум", "Рыночные сервисы", "Команда Спектр"),
                ("p710", "парус", "Финансирование", "Команда Опора"),
                ("p711", "бастион", "Защищённые расчёты", "Команда Контур"),
                ("p712", "ритм", "Торговые сервисы", "Команда Витрина"),
                ("p713", "зонтик", "Подписки и защита", "Команда Забота"),
                ("p714", "созвездие", "Подписки и защита", "Команда Забота"),
                ("p715", "мозаика", "Сервисы организаций", "Команда Союз"),
                ("p716", "маховик", "Сервисы организаций", "Команда Союз"),
                ("p717", "пергамент", "Цифровая инфраструктура", "Команда Механика"),
                ("p718", "облачный сад", "Цифровая инфраструктура", "Команда Механика"),
            ]

            detected_code = None
            detected_name = None
            detected_section = None
            detected_owner = None

            for code, name, section, owner in catalog:
                if code in lower_prompt or name in lower_prompt:
                    detected_code = code.upper()
                    detected_name = name.capitalize()
                    detected_section = section
                    detected_owner = owner
                    break

            # Check attachment intent strictly against user query (not prompt template)
            query_text = lower_prompt
            if "вопрос пользователя:" in lower_prompt:
                query_text = lower_prompt.split("вопрос пользователя:")[1].split("\n")[0]

            attachment_keywords = [
                "вложени", "файл", "прикреп", "диаграмм", "схем", "скриншот", "рисунк", "изображени",
                "png", "pdf", "docx", "csv", "xlsx", ".txt", "txt-вложени", "md-вложени", "asm", "cs"
            ]
            need_attachment = any(kw in query_text for kw in attachment_keywords)

            slug = None
            # Extract slug from quotes or patterns
            slug_match = re.search(r"[«\"']([a-z0-9]+(?:-[a-z0-9]+)+)[»\"']", query_text)
            if slug_match:
                slug = slug_match.group(1)
            elif "passport" in query_text or "паспорт" in query_text:
                slug = f"{(detected_name or 'doc').lower()}-passport"

            doc_type = "passport" if "паспорт" in query_text else "general"

            # Clean query
            clean_query = query_text
            for stopword in ["подскажи", "расскажи", "какой", "какая", "пожалуйста", "найди", "в"]:
                clean_query = clean_query.replace(stopword, "").strip()

            result = {
                "product_code": detected_code,
                "product_name": detected_name,
                "section": detected_section,
                "owner": detected_owner,
                "slug": slug,
                "doc_type": doc_type,
                "need_attachment": need_attachment,
                "query_rewrite": clean_query or prompt,
            }
            return json.dumps(result, ensure_ascii=False, indent=2)

        # Otherwise Answer Agent query
        # Extract any slugs in the prompt context
        slugs = re.findall(r"slug:\s*([a-zA-Z0-9_\-\.]+)", prompt, re.IGNORECASE)
        cited_slug = f"[{slugs[0]}]" if slugs else "[meridian-kb-doc]"

        return (
            f"На основе предоставленной документации {cited_slug}:\n"
            f"Запрос пользователя был успешно обработан. Все параметры соответствуют установленным регламентам и спецификациям.\n\n"
            f"**Источники:**\n"
            f"- {cited_slug} — Паспорт и документация продукта"
        )
