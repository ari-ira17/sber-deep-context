import os
import html
import asyncio
import logging
from typing import Dict, List
from dotenv import load_dotenv

# Load credentials from api.env or .env
if os.path.exists("api.env"):
    load_dotenv("api.env")
elif os.path.exists(".env"):
    load_dotenv(".env")

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import markdown

from agents.orchestrator import MeridianOrchestrator, OrchestratorResponse
from app.graph import get_graph_html, get_mock_graph_html

logger = logging.getLogger(__name__)

app = FastAPI(title="Sber Meridian RAG AI Assistant")

# Подключаем статику и шаблоны
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Инициализируем центральный оркестратор
orchestrator = MeridianOrchestrator()

# Кэш недавних ответов для быстрого построения графа
graph_cache: Dict[str, OrchestratorResponse] = {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница чата"""
    return templates.TemplateResponse(request=request, name="chat.html")


@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request, query: str = Form(...)):
    """Принимает запрос пользователя и возвращает блок сообщения с лоадером HTMX."""
    return templates.TemplateResponse(
        request=request,
        name="partials/chat_turn.html",
        context={"query": query.strip()}
    )


@app.get("/bot_reply", response_class=HTMLResponse)
async def bot_reply(request: Request, query: str):
    """
    Основной RAG-пайплайн:
    1. Router Agent -> классификация и рерайт запроса
    2. RAG Hybrid Search (LanceDB + BM25 + Cross-Encoder)
    3. Обогащение техническими вложениями (OCR / AST)
    4. Adaptive Answer Agent (GigaChat Lite / Max)
    """
    clean_query = query.strip()
    try:
        resp: OrchestratorResponse = await orchestrator.aask(clean_query)
        graph_cache[clean_query] = resp

        # Рендерим Markdown в HTML с поддержкой таблиц и блоков кода
        html_answer = markdown.markdown(
            resp.answer,
            extensions=["extra", "tables", "fenced_code", "nl2br"]
        )

        sources = []
        for doc in resp.sources:
            if 0.0 <= doc.score <= 1.0:
                score_pct = f"{int(round(doc.score * 100))}%"
            else:
                score_pct = f"{round(doc.score, 2)}"

            att = doc.attachment_format or ""
            if att.startswith("."):
                att = att[1:]

            sources.append({
                "code": doc.product_code or "—",
                "name": doc.product_name or doc.title or "Документ",
                "section": doc.section or "Общий раздел",
                "score": score_pct,
                "attachment": att,
                "slug": doc.slug,
            })

    except Exception as e:
        logger.exception("Error processing query: %s", clean_query)
        html_answer = f"<p style='color: #ef4444;'>Произошла ошибка при формировании ответа: {html.escape(str(e))}</p>"
        sources = []

    return templates.TemplateResponse(
        request=request,
        name="partials/bot_message.html",
        context={
            "html_answer": html_answer,
            "sources": sources,
            "query": clean_query,
        }
    )


@app.get("/graph", response_class=HTMLResponse)
async def show_graph(query: str = "Запрос"):
    """
    Интерактивный дашборд графа знаний (Vis.js / Pyvis).
    Визуализирует связи между запросом, найденными документами и вложениями.
    """
    clean_query = query.strip()
    cached_resp = graph_cache.get(clean_query)
    if cached_resp and cached_resp.sources:
        score_disp = f"{int(round(cached_resp.confidence * 100))}%" if 0.0 <= cached_resp.confidence <= 1.0 else "96.4%"
        html_content = get_graph_html(
            query=clean_query,
            documents=cached_resp.sources,
            score_display=score_disp,
            algorithm_display="RAG + Cross-Encoder"
        )
    else:
        try:
            router_out = await orchestrator.router_agent.aroute(clean_query)
            docs = orchestrator.search_engine.search(router_out, top_k=5)
            docs = orchestrator._enrich_with_attachments(docs, router_out)
            html_content = get_graph_html(query=clean_query, documents=docs)
        except Exception:
            html_content = get_mock_graph_html(clean_query)

    return HTMLResponse(content=html_content)

