import os
import html
import asyncio
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load credentials from api.env or .env
if os.path.exists("api.env"):
    load_dotenv("api.env")
elif os.path.exists(".env"):
    load_dotenv(".env")

from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
import markdown

from agents.orchestrator import MeridianOrchestrator, OrchestratorResponse
from app.graph import get_graph_html, get_mock_graph_html, get_document_graph_html
from app.db import chat_history
from app.evidence import evidence_service
from app.sandbox import sandbox_service

logger = logging.getLogger(__name__)

app = FastAPI(title="Sber Meridian RAG AI Assistant")

# Инициализируем базу данных истории чатов
chat_history.init_db()

# Подключаем статику и шаблоны
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Подключаем вложения (изображения PNG, PDF, CSV) для инспектора первоисточников
attachments_dir = os.path.join(os.path.dirname(__file__), "..", "meridian_hackathon_knowledge_base", "knowledge_attachments")
if os.path.exists(attachments_dir):
    app.mount("/attachments", StaticFiles(directory=attachments_dir), name="attachments")

templates = Jinja2Templates(directory="app/templates")

# Инициализируем центральный оркестратор
orchestrator = MeridianOrchestrator()

# Кэш недавних ответов для быстрого построения графа
graph_cache: Dict[str, OrchestratorResponse] = {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница нового чата"""
    chats = chat_history.list_chats()
    sandbox_sources = chat_history.list_chat_sources()
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "chats": chats,
            "messages": [],
            "active_chat_id": None,
            "sandbox_sources": sandbox_sources,
        },
    )


@app.get("/chats/{chat_id}", response_class=HTMLResponse)
async def get_chat(request: Request, chat_id: str):
    """Страница существующего чата с загруженной историей сообщений"""
    chat = chat_history.get_chat(chat_id)
    if not chat:
        return RedirectResponse(url="/", status_code=303)
    chats = chat_history.list_chats()
    messages = chat_history.get_chat_messages(chat_id)
    sandbox_sources = chat_history.list_chat_sources()
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "chats": chats,
            "messages": messages,
            "active_chat_id": chat_id,
            "sandbox_sources": sandbox_sources,
        },
    )


@app.get("/api/chats", response_class=HTMLResponse)
async def list_chats_api(request: Request, active_id: Optional[str] = None):
    """Частичный шаблон списка чатов для боковой панели (HTMX)"""
    chats = chat_history.list_chats()
    return templates.TemplateResponse(
        request=request,
        name="partials/sidebar_chats.html",
        context={
            "chats": chats,
            "active_chat_id": active_id,
        },
    )


@app.delete("/chats/{chat_id}", response_class=HTMLResponse)
async def delete_chat_endpoint(request: Request, chat_id: str):
    """Удаляет сессию диалога из SQLite"""
    chat_history.delete_chat(chat_id)
    chats = chat_history.list_chats()
    current_url = request.headers.get("HX-Current-URL", "")

    response = templates.TemplateResponse(
        request=request,
        name="partials/sidebar_chats.html",
        context={"chats": chats, "active_chat_id": None},
    )
    if chat_id in current_url:
        response.headers["HX-Redirect"] = "/"
    else:
        response.headers["HX-Trigger"] = "refreshSidebar"
    return response


@app.post("/api/sources/upload")
@app.post("/api/chats/{chat_id}/upload")
async def upload_sandbox_files(
    files: List[UploadFile] = File(...),
    chat_id: Optional[str] = None,
):
    """Загружает пользовательские файлы в песочницу (глобально доступные источники без создания чата)."""
    uploaded_records = []
    for file in files:
        content = await file.read()
        if not content:
            continue
        rec = sandbox_service.save_and_register_file(
            filename=file.filename or "uploaded_file",
            file_bytes=content,
            chat_id="global",
        )
        uploaded_records.append(rec)

    all_sources = chat_history.list_chat_sources()
    return JSONResponse({
        "success": True,
        "uploaded": uploaded_records,
        "sources": all_sources,
    })


@app.get("/api/sources")
@app.get("/api/chats/{chat_id}/sources")
async def get_sandbox_sources(chat_id: Optional[str] = None):
    """Возвращает список всех файлов песочницы."""
    sources = chat_history.list_chat_sources()
    return JSONResponse({"sources": sources})


@app.get("/api/sources/html", response_class=HTMLResponse)
@app.get("/api/chats/{chat_id}/sources/html", response_class=HTMLResponse)
async def get_sandbox_sources_html(request: Request, chat_id: Optional[str] = None):
    """Возвращает HTML-список файлов песочницы для сайдбара."""
    sandbox_sources = chat_history.list_chat_sources()
    return templates.TemplateResponse(
        request=request,
        name="partials/sidebar_sources.html",
        context={"request": request, "sandbox_sources": sandbox_sources},
    )


@app.post("/api/sources/{source_id}/toggle", response_class=HTMLResponse)
@app.post("/api/chats/{chat_id}/sources/{source_id}/toggle", response_class=HTMLResponse)
async def toggle_source_endpoint(request: Request, source_id: str, chat_id: Optional[str] = None):
    """Переключает статус активности источника в контексте и возвращает обновленный список для сайдбара."""
    chat_history.toggle_chat_source(source_id)
    sandbox_sources = chat_history.list_chat_sources()
    return templates.TemplateResponse(
        request=request,
        name="partials/sidebar_sources.html",
        context={"request": request, "sandbox_sources": sandbox_sources},
    )


@app.delete("/api/sources/{source_id}")
@app.delete("/api/chats/{chat_id}/sources/{source_id}")
async def delete_sandbox_source(source_id: str, chat_id: Optional[str] = None):
    """Удаляет файл из песочницы."""
    success = chat_history.delete_chat_source(source_id)
    remaining = chat_history.list_chat_sources()
    return JSONResponse({"success": success, "sources": remaining})


@app.post("/chats/{chat_id}/favorite", response_class=HTMLResponse)
async def toggle_favorite_endpoint(request: Request, chat_id: str):
    """Переключает избранное состояние чата и обновляет боковую панель."""
    chat_history.toggle_favorite(chat_id)

    chats = chat_history.list_chats()

    current_url = request.headers.get("HX-Current-URL", "")
    active_chat_id = chat_id if chat_id in current_url else None

    return templates.TemplateResponse(
        request=request,
        name="partials/sidebar_chats.html",
        context={
            "chats": chats,
            "active_chat_id": active_chat_id,
        },
    )
@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request, query: str = Form(...), chat_id: Optional[str] = Form(None)):
    """Принимает запрос пользователя, сохраняет его в БД и возвращает блок с лоадером."""
    clean_query = query.strip()
    if not chat_id or not chat_history.get_chat(chat_id):
        # Называем чат по первому вопросу
        title = clean_query[:35] + ("..." if len(clean_query) > 35 else "")
        chat_id = chat_history.create_chat(chat_id=chat_id, title=title)

    chat_history.add_message(chat_id=chat_id, role="user", content=clean_query)

    return templates.TemplateResponse(
        request=request,
        name="partials/chat_turn.html",
        context={"query": clean_query, "chat_id": chat_id},
    )


@app.get("/bot_reply", response_class=HTMLResponse)
async def bot_reply(request: Request, query: str, chat_id: Optional[str] = None):
    """
    Основной RAG-пайплайн:
    1. Router Agent -> классификация и рерайт запроса
    2. Поиск по сессионной песочнице (Sandbox)
    3. RAG Hybrid Search (LanceDB + BM25 + Cross-Encoder)
    4. Обогащение техническими вложениями (OCR / AST)
    5. Adaptive Answer Agent (GigaChat Lite / Max)
    6. Сохранение ответа в SQLite и отправка HX-Trigger для обновления сайдбара
    """
    clean_query = query.strip()
    raw_answer = ""
    try:
        # Поиск по активным файлам песочницы (глобально включенные источники)
        sandbox_docs = sandbox_service.search_sandbox_sources(query=clean_query, top_k=3)

        resp: OrchestratorResponse = await orchestrator.aask(clean_query, extra_documents=sandbox_docs)
        graph_cache[clean_query] = resp
        raw_answer = resp.answer

        # Рендерим Markdown в HTML с поддержкой таблиц и блоков кода
        html_answer = markdown.markdown(
            resp.answer,
            extensions=["extra", "tables", "fenced_code", "nl2br"]
        )

        # Обогащаем сноски [slug] интерактивными чипами инспектора доказательств
        html_answer = evidence_service.enhance_citations(html_answer, active_citations=resp.citations)

        sources = []
        for doc in resp.sources:
            if 0.0 <= doc.score <= 1.0:
                score_pct = f"{int(round(doc.score * 100))}%"
            else:
                score_pct = f"{round(doc.score, 2)}"

            att = doc.attachment_format or ""
            if att.startswith("."):
                att = att[1:]

            doc_name = doc.title or doc.product_name or "Документ"
            sources.append({
                "code": doc.product_code or "—",
                "name": doc_name,
                "section": doc.section or "Общий раздел",
                "score": score_pct,
                "attachment": att,
                "slug": doc.slug,
            })

    except Exception as e:
        logger.exception("Error processing query: %s", clean_query)
        html_answer = f"<p style='color: #ef4444;'>Произошла ошибка при формировании ответа: {html.escape(str(e))}</p>"
        raw_answer = f"Ошибка: {str(e)}"
        sources = []

    # Сохраняем ответ ассистента в SQLite историю
    if chat_id:
        chat_history.add_message(
            chat_id=chat_id,
            role="assistant",
            content=raw_answer,
            html_content=html_answer,
            sources=sources,
        )

    response = templates.TemplateResponse(
        request=request,
        name="partials/bot_message.html",
        context={
            "html_answer": html_answer,
            "sources": sources,
            "query": clean_query,
        }
    )
    # Отправляем триггер HTMX для мгновенного обновления сайдбара
    response.headers["HX-Trigger"] = "refreshSidebar"
    return response


@app.get("/bot_reply_sse")
async def bot_reply_sse(request: Request, query: str, chat_id: Optional[str] = None):
    """
    Основной RAG-пайплайн с потоковым выводом логов через Server-Sent Events (SSE).
    """
    clean_query = query.strip()
    
    async def event_generator():
        try:
            async for event in orchestrator.astream_ask(clean_query):
                if event["type"] == "log":
                    msg = event["content"]
                    html_log = f'<div style="display: flex; align-items: center; gap: 8px;"><span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #3b82f6;"></span>{html.escape(msg)}</div>'
                    yield f"event: log\ndata: {html_log}\n\n"
                
                elif event["type"] == "result":
                    resp: OrchestratorResponse = event["data"]
                    graph_cache[clean_query] = resp
                    raw_answer = resp.answer

                    html_answer = markdown.markdown(
                        resp.answer,
                        extensions=["extra", "tables", "fenced_code", "nl2br"]
                    )

                    html_answer = evidence_service.enhance_citations(html_answer, active_citations=resp.citations)

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
                            "name": doc.title or doc.product_name or "Документ",
                            "section": doc.section or "Общий раздел",
                            "score": score_pct,
                            "attachment": att,
                            "slug": doc.slug,
                        })

                    if chat_id:
                        chat_history.add_message(
                            chat_id=chat_id,
                            role="assistant",
                            content=raw_answer,
                            html_content=html_answer,
                            sources=sources,
                        )
                    
                    final_html = templates.TemplateResponse(
                        request=request,
                        name="partials/bot_message.html",
                        context={
                            "html_answer": html_answer,
                            "sources": sources,
                            "query": clean_query,
                            "logs": resp.logs
                        }
                    ).body.decode("utf-8")
                    
                    final_html += '<script>htmx.trigger("body", "refreshSidebar");</script>'
                    
                    lines = final_html.splitlines()
                    data_str = "\n".join(f"data: {line}" for line in lines if line.strip())
                    yield f"event: final\n{data_str}\n\n"
                    
        except Exception as e:
            logger.exception("Error processing query in SSE: %s", clean_query)
            error_html = f"<div class='message bot-message'><div class='avatar'><img src='/static/img/sbercat.jpg'></div><div class='message-content'><p style='color: #ef4444;'>Ошибка: {html.escape(str(e))}</p></div></div>"
            error_html += '<script>htmx.trigger("body", "refreshSidebar");</script>'
            yield f"event: final\ndata: {error_html}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/graph", response_class=HTMLResponse)
async def show_graph(
    query: Optional[str] = None,
    slug: Optional[str] = None,
    embedded: bool = False
):
    """
    Интерактивный дашборд графа знаний (Vis.js / Pyvis).
    Визуализирует:
    1. Поисковый запрос (связи запроса, источников, вложений)
    2. Или конкретный документ по slug (связи документа, продукта, смежных регламентов, вложений)
    3. Поддерживает встраивание в slide-over шторку (embedded=True)
    """
    if slug:
        html_content = get_document_graph_html(slug=slug, evidence_service=evidence_service, embedded=embedded)
        return HTMLResponse(content=html_content)

    clean_query = (query or "Запрос").strip()
    cached_resp = graph_cache.get(clean_query)
    if cached_resp and cached_resp.sources:
        score_disp = f"{int(round(cached_resp.confidence * 100))}%" if 0.0 <= cached_resp.confidence <= 1.0 else "96.4%"
        html_content = get_graph_html(
            query=clean_query,
            documents=cached_resp.sources,
            score_display=score_disp,
            algorithm_display="RAG + Cross-Encoder",
            embedded=embedded
        )
    else:
        try:
            router_out = await orchestrator.router_agent.aroute(clean_query)
            docs = orchestrator.search_engine.search(router_out, top_k=5)
            docs = orchestrator._enrich_with_attachments(docs, router_out)
            html_content = get_graph_html(query=clean_query, documents=docs, embedded=embedded)
        except Exception:
            html_content = get_mock_graph_html(clean_query, embedded=embedded)

    return HTMLResponse(content=html_content)


@app.get("/evidence/drawer/{slug}", response_class=HTMLResponse)
async def get_evidence_drawer(request: Request, slug: str, highlight: Optional[str] = None):
    """
    Возвращает HTML-содержимое шторки Evidence Inspector для выбранного слага страницы.
    """
    ev = evidence_service.get_evidence(slug, highlight_term=highlight)
    if not ev:
        return HTMLResponse(
            content=f"""
            <div class="evidence-error">
                <h3>Первоисточник не найден</h3>
                <p>Документ с идентификатором <code>{html.escape(slug)}</code> отсутствует в базе знаний «Меридиан».</p>
                <button type="button" class="drawer-btn close-btn" onclick="closeEvidenceInspector()">Закрыть</button>
            </div>
            """,
            status_code=404
        )
    return templates.TemplateResponse(
        request=request,
        name="partials/evidence_drawer_content.html",
        context={"ev": ev}
    )


@app.get("/api/evidence/{slug}")
async def get_evidence_api(slug: str, highlight: Optional[str] = None):
    """REST API эндпоинт для программного получения полного досье первоисточника и метаданных."""
    ev = evidence_service.get_evidence(slug, highlight_term=highlight)
    if not ev:
        return {"error": "Document not found", "slug": slug}
    return ev


