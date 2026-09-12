from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio
import markdown
from app.graph import get_mock_graph_html

app = FastAPI(title="Sber AI UI")

# Подключаем статику и шаблоны
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница чата"""
    return templates.TemplateResponse(request=request, name="chat.html")

@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request, query: str = Form(...)):
    return templates.TemplateResponse(request=request, name="partials/chat_turn.html", context={"query": query})

@app.get("/bot_reply", response_class=HTMLResponse)
async def bot_reply(request: Request, query: str):
    await asyncio.sleep(1.8) 
    
    # Мок-ответ без старого названия
    raw_answer = f"""
На основе корпоративной базы знаний по вашему запросу **«{query}»**:

В продукте **Искра** (P701) регламентированы ежедневные расчеты. Согласно приложенной документации, лимиты составляют до 5 млн руб. без дополнительного согласования со стороны риск-менеджмента. 

> Обратите внимание: вложения формата `.png` успешно обработаны с помощью локального OCR-модуля.
    """
    html_answer = markdown.markdown(raw_answer)
    
    sources = [
        {"code": "P701", "name": "Искра", "section": "Ежедневные расчёты", "score": "96%", "attachment": "png"},
        {"code": "P704", "name": "Мостик", "section": "Финансирование", "score": "82%", "attachment": "docx"}
    ]
    
    return templates.TemplateResponse(request=request, name="partials/bot_message.html", context={
        "html_answer": html_answer,
        "sources": sources,
        "query": query
    })

@app.get("/graph", response_class=HTMLResponse)
async def show_graph(query: str = "Запрос"):
    html_content = get_mock_graph_html(query)
    return HTMLResponse(content=html_content)
