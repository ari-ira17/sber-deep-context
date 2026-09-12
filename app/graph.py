import json
import html
from typing import Optional, List, Dict, Any
from pathlib import Path

# Product color palette matching Participant 4
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


def get_graph_html(
    query: str,
    documents: Optional[List[Any]] = None,
    score_display: Optional[str] = None,
    algorithm_display: str = "LanceDB + BM25 + Reranker",
) -> str:
    """
    Дашборд графа с поддержкой темной/светлой темы (glass effect)
    и динамической визуализацией документов RAG.
    """
    safe_query = html.escape(query)

    if documents and len(documents) > 0:
        raw_nodes = []
        raw_edges = []
        node_data = {}

        # 1. Central query node
        raw_nodes.append({
            "id": 1,
            "label": f'"{query[:28]}..."' if len(query) > 28 else f'"{query}"',
            "border": "#10b981",
            "size": 30,
        })
        node_data["1"] = {
            "title": "Поисковый запрос",
            "desc": f"Исходный текст: {query}",
        }

        # 2. Document nodes and edges
        top_score_val = None
        for i, doc in enumerate(documents[:6]):
            doc_id = i + 2
            p_code = getattr(doc, "product_code", None) or "DOC"
            p_name = getattr(doc, "product_name", None) or getattr(doc, "title", None) or getattr(doc, "slug", f"doc_{i}")
            p_label = f"{p_code} ({p_name})" if p_code != "DOC" else p_name
            if len(p_label) > 24:
                p_label = p_label[:22] + "..."

            score = getattr(doc, "score", 0.85)
            if top_score_val is None:
                top_score_val = score

            if 0.0 <= score <= 1.0:
                score_str = f"{int(round(score * 100))}%"
            else:
                score_str = f"{round(score, 2)}"

            border_color = PRODUCT_COLOR_PALETTE.get(p_code, "#3b82f6")
            raw_nodes.append({
                "id": doc_id,
                "label": p_label,
                "border": border_color,
                "size": 22,
            })

            content = getattr(doc, "content", "")
            snippet = (content[:240] + "...") if len(content) > 240 else content
            section = getattr(doc, "section", "Общий")
            node_data[str(doc_id)] = {
                "title": f"Документ: {p_code} ({p_name})",
                "desc": f"Раздел: {section}. Релевантность: {score_str}.\nСодержание: {snippet}",
            }

            raw_edges.append({
                "from": 1,
                "to": doc_id,
                "value": max(1, int(score * 3) if 0 <= score <= 1 else 2),
                "label": f" {score_str}",
                "dashes": False,
            })

            # 3. Attachment node if present
            att_path = getattr(doc, "attachment_path", None)
            att_format = getattr(doc, "attachment_format", None)
            if att_path or att_format:
                att_id = 100 + doc_id
                if att_path:
                    att_label = Path(att_path).name
                else:
                    att_label = f"attachment.{att_format.lstrip('.')}"

                raw_nodes.append({
                    "id": att_id,
                    "label": att_label,
                    "border": "#f59e0b",
                    "size": 18,
                })

                att_text = getattr(doc, "attachment_text", None) or ""
                att_snippet = (att_text[:240] + "...") if len(att_text) > 240 else (att_text or "Файл вложения (OCR / AST).")
                node_data[str(att_id)] = {
                    "title": f"Вложение: {att_label}",
                    "desc": f"Формат: {att_format or 'unknown'}. Данные: {att_snippet}",
                }

                raw_edges.append({
                    "from": doc_id,
                    "to": att_id,
                    "value": 1,
                    "label": " вложение",
                    "dashes": True,
                })

        if score_display is None:
            if top_score_val is not None and 0.0 <= top_score_val <= 1.0:
                score_display = f"{int(round(top_score_val * 100))}%"
            else:
                score_display = "96.4%"

    else:
        # Fallback mock nodes
        raw_nodes = [
            {"id": 1, "label": f'"{query[:28]}..."' if len(query) > 28 else f'"{query}"', "border": "#10b981", "size": 30},
            {"id": 2, "label": "P701 (Искра)", "border": "#3b82f6", "size": 22},
            {"id": 3, "label": "P704 (Мостик)", "border": "#3b82f6", "size": 22},
            {"id": 4, "label": "P701_table.png", "border": "#f59e0b", "size": 18},
        ]
        raw_edges = [
            {"from": 1, "to": 2, "value": 3, "label": " 96%", "dashes": False},
            {"from": 1, "to": 3, "value": 2, "label": " 82%", "dashes": False},
            {"from": 2, "to": 4, "value": 1, "label": " вложение", "dashes": True},
        ]
        node_data = {
            "1": {"title": "Поисковый запрос", "desc": "Исходный текст, введённый пользователем."},
            "2": {"title": "Документ: P701 (Искра)", "desc": "Внутренний регламент ежедневных расчетов продукта Искра. Обнаружено точное совпадение по лимитам."},
            "3": {"title": "Документ: P704 (Мостик)", "desc": "Описание процесса финансирования и кредитных лимитов продукта Мостик. Релевантность высокая."},
            "4": {"title": "Вложение: P701_table.png", "desc": "Скан-копия таблицы лимитов (обработана модулем OCR). Подтверждает данные из P701."},
        }
        if score_display is None:
            score_display = "96.4%"

    raw_nodes_json = json.dumps(raw_nodes, ensure_ascii=False)
    raw_edges_json = json.dumps(raw_edges, ensure_ascii=False)
    node_data_json = json.dumps(node_data, ensure_ascii=False)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Анализ графа - {safe_query}</title>
        <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="/static/css/style.css">
        <style>
            body {{ display: flex; flex-direction: row; width: 100vw; height: 100vh; overflow: hidden; margin: 0; }}
            .graph-wrapper {{ flex: 1; position: relative; background-color: transparent; }}
            #mynetwork {{ width: 100%; height: 100%; border: none; position: relative; z-index: 1; }}
            .side-panel {{
                width: 380px;
                background: var(--sidebar-bg);
                backdrop-filter: blur(40px);
                -webkit-backdrop-filter: blur(40px);
                border-left: 1px solid var(--glass-border);
                box-shadow: -10px 0 40px rgba(0,0,0,0.03);
                padding: 2.5rem;
                display: flex;
                flex-direction: column;
                z-index: 10;
                overflow-y: auto;
            }}
            .side-panel h2 {{ margin-top: 0; color: var(--text-main); font-size: 1.4rem; margin-bottom: 2rem; display: flex; align-items: center; gap: 12px; font-weight: 600; letter-spacing: -0.5px; }}
            .metric-card {{ background: var(--glass-btn-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); padding: 1.25rem; border-radius: 20px; margin-bottom: 1rem; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.03); color: var(--text-main); }}
            .metric-label {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 0.5rem; font-weight: 600; }}
            .metric-value {{ font-size: 1.25rem; font-weight: 600; color: var(--accent); }}
            
            #node-details-card {{ display: none; border-left: 4px solid #3b82f6; animation: slideDown 0.3s ease; }}
            @keyframes slideDown {{ from {{ opacity: 0; transform: translateY(-10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
            
            .back-btn {{ margin-top: 1rem; padding: 1rem; background: var(--btn-primary); color: white; text-align: center; text-decoration: none; border-radius: 24px; font-weight: 500; transition: 0.3s; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15); }}
            .back-btn:hover {{ background: var(--btn-primary-hover); transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0, 0, 0, 0.25); }}
            
            .theme-toggle-btn {{ background: transparent; border: 1px solid var(--glass-border); color: var(--text-main); padding: 0.8rem; border-radius: 20px; cursor: pointer; font-family: inherit; font-weight: 500; margin-top: auto; display: flex; align-items: center; justify-content: center; gap: 0.5rem; transition: 0.3s; }}
            .theme-toggle-btn:hover {{ background: var(--glass-btn-hover); }}
        </style>
    </head>
    <body>
        <div class="graph-wrapper">
            <div class="bg-blobs" style="z-index: 0;">
                <div class="blob blob-green"></div>
                <div class="blob blob-orange"></div>
                <div class="blob blob-purple"></div>
            </div>
            <div id="mynetwork"></div>
        </div>
        
        <div class="side-panel">
            <h2>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="18" cy="5" r="3"></circle>
                    <circle cx="6" cy="12" r="3"></circle>
                    <circle cx="18" cy="19" r="3"></circle>
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                </svg>
                Анализ графа
            </h2>
            
            <div class="metric-card">
                <div class="metric-label">Поисковый запрос</div>
                <div style="font-weight: 500; line-height: 1.4;">"{safe_query}"</div>
            </div>
            
            <div class="metric-card" id="node-details-card">
                <div class="metric-label" style="color: #3b82f6;">Информация об узле</div>
                <div id="node-details-title" style="font-weight: 600; margin-bottom: 0.5rem; font-size: 1.1rem;"></div>
                <div id="node-details-desc" style="font-size: 0.9rem; color: var(--text-muted); line-height: 1.5; white-space: pre-wrap;"></div>
            </div>
            
            <div class="metric-card" style="display: flex; gap: 1rem; margin-top: 1rem;">
                <div style="flex:1;">
                    <div class="metric-label">Точность (Score)</div>
                    <div class="metric-value">{score_display}</div>
                </div>
                <div style="flex:1;">
                    <div class="metric-label">Алгоритм</div>
                    <div class="metric-value" style="color: var(--text-muted); font-size: 1rem; margin-top: 4px;">{algorithm_display}</div>
                </div>
            </div>
            
            <button class="theme-toggle-btn" id="graph-theme-toggle">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
                <span id="g-theme-text">Сменить тему</span>
            </button>
            <a href="/" class="back-btn">Вернуться к диалогу</a>
        </div>

        <script type="text/javascript">
            // Инициализация темы
            const isDark = localStorage.getItem('theme') === 'dark';
            if(isDark) document.body.classList.add('dark-mode');
            
            document.getElementById('graph-theme-toggle').addEventListener('click', function() {{
                document.body.classList.toggle('dark-mode');
                const dark = document.body.classList.contains('dark-mode');
                localStorage.setItem('theme', dark ? 'dark' : 'light');
                location.reload(); // Перезагружаем для перерисовки узлов
            }});

            // Цвета узлов в зависимости от темы
            const nBg = isDark ? 'rgba(30,41,59,0.9)' : 'rgba(255,255,255,0.9)';
            const txtC = isDark ? '#f8fafc' : '#000000';
            const strkC = isDark ? '#0f172a' : '#ffffff';
            const edgeC = isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.2)';

            const rawNodes = {raw_nodes_json};
            const rawEdges = {raw_edges_json};
            const nodeData = {node_data_json};

            var nodes = new vis.DataSet(rawNodes.map(function(n) {{
                return {{
                    id: n.id,
                    label: n.label,
                    color: {{ background: nBg, border: n.border || '#3b82f6' }},
                    borderWidth: 3,
                    font: {{ color: txtC, size: n.id === 1 ? 14 : 12, strokeWidth: 3, strokeColor: strkC }},
                    shape: 'dot',
                    size: n.size || 22,
                    shadow: {{ enabled: true, color: (n.border || '#3b82f6') + '66', size: 20, x: 0, y: 0 }}
                }};
            }}));

            var edges = new vis.DataSet(rawEdges.map(function(e) {{
                return {{
                    from: e.from,
                    to: e.to,
                    value: e.value || 2,
                    label: e.label || '',
                    dashes: !!e.dashes,
                    font: {{ align: 'middle', size: e.dashes ? 11 : 13, color: txtC, strokeWidth: 2, strokeColor: strkC }},
                    color: {{ color: edgeC }}
                }};
            }}));

            var container = document.getElementById('mynetwork');
            var data = {{ nodes: nodes, edges: edges }};
            var options = {{
                physics: {{
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {{ gravitationalConstant: -120, centralGravity: 0.005, springLength: 250, springConstant: 0.04 }}
                }},
                interaction: {{ hover: true }}
            }};
            
            var network = new vis.Network(container, data, options);
            
            network.on("click", function (params) {{
                if (params.nodes.length > 0) {{
                    var nodeId = String(params.nodes[0]);
                    var info = nodeData[nodeId];
                    if (info) {{
                        document.getElementById('node-details-card').style.display = 'block';
                        document.getElementById('node-details-title').innerText = info.title;
                        document.getElementById('node-details-desc').innerText = info.desc;
                    }}
                }} else {{
                    document.getElementById('node-details-card').style.display = 'none';
                }}
            }});
        </script>
    </body>
    </html>
    """


def get_mock_graph_html(query: str) -> str:
    """Backwards compatibility helper."""
    return get_graph_html(query, documents=None)

