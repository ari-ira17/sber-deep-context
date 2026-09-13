import json
import html
import re
from typing import Optional, List, Dict, Any
from pathlib import Path


PRODUCT_COLOR_PALETTE: Dict[str, str] = {
    "P701": "#FF6B6B",  
    "P702": "#4D96FF",  
    "P703": "#FFD93D",  
    "P704": "#6BCB77",  
    "P705": "#9B51E0",  
    "P706": "#FF9F45",  
    "P707": "#F24A72",  
    "P708": "#00C897",  
    "P709": "#2F80ED",  
    "P710": "#56CCF2",  
    "P711": "#EB5757",  
    "P712": "#F2994A",  
    "P713": "#BB6BD9",  
    "P714": "#828282",  
    "P715": "#27AE60",  
    "P716": "#E2B93B",  
    "P717": "#795548",  
    "P718": "#607D8B",  
}


def _render_visjs_page(
    page_title: str,
    raw_nodes: List[Dict[str, Any]],
    raw_edges: List[Dict[str, Any]],
    node_data: Dict[str, Any],
    *args,
    **kwargs,
) -> str:
    safe_page_title = html.escape(page_title)
    raw_nodes_json = json.dumps(raw_nodes, ensure_ascii=False)
    raw_edges_json = json.dumps(raw_edges, ensure_ascii=False)
    node_data_json = json.dumps(node_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{safe_page_title}</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        * {{ box-sizing: border-box; }}
        html, body {{
            width: 100vw;
            height: 100vh;
            overflow: hidden;
            margin: 0;
            padding: 0;
            background: transparent;
            color: var(--text-main);
            font-family: 'Inter', sans-serif;
            position: relative;
        }}
        .graph-wrapper {{
            width: 100%;
            height: 100%;
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: transparent;
        }}
        #mynetwork {{
            width: 100%;
            height: 100%;
            border: none;
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            z-index: 1;
        }}
        /* Минималистичная всплывающая карточка деталей узла при клике */
        .node-floating-card {{
            position: absolute;
            top: 14px;
            right: 14px;
            width: 290px;
            max-width: calc(100vw - 28px);
            background: var(--card-bg);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1px solid var(--glass-border);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
            z-index: 20;
            display: none;
            animation: fadeInCard 0.2s ease;
        }}
        @keyframes fadeInCard {{
            from {{ opacity: 0; transform: translateY(-6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .node-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
            margin-bottom: 0.4rem;
        }}
        .node-card-title {{
            font-size: 0.92rem;
            font-weight: 600;
            color: var(--text-main);
            line-height: 1.35;
        }}
        .node-card-close {{
            background: var(--glass-btn-bg);
            border: 1px solid var(--glass-border);
            color: var(--text-muted);
            width: 22px;
            height: 22px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 0.75rem;
            flex-shrink: 0;
            transition: all 0.2s ease;
        }}
        .node-card-close:hover {{
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
        }}
        .node-card-desc {{
            font-size: 0.8rem;
            color: var(--text-muted);
            line-height: 1.45;
            white-space: pre-wrap;
            max-height: 180px;
            overflow-y: auto;
        }}
        .graph-action-btn {{
            margin-top: 0.75rem;
            width: 100%;
            padding: 0.55rem 0.75rem;
            background: #10b981;
            color: #ffffff;
            border: none;
            border-radius: 9px;
            font-weight: 600;
            font-size: 0.8rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            transition: all 0.2s ease;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.2);
        }}
        .graph-action-btn:hover {{
            background: #059669;
            transform: translateY(-1px);
        }}
    </style>
</head>
<body>
    <div class="graph-wrapper">
        <div class="bg-blobs" style="z-index: 0; pointer-events: none; opacity: 0.35;">
            <div class="blob blob-green"></div>
            <div class="blob blob-orange"></div>
            <div class="blob blob-purple"></div>
        </div>
        <div id="mynetwork"></div>
    </div>

    <!-- Всплывающая компактная карточка при клике на узел -->
    <div id="node-floating-card" class="node-floating-card">
        <div class="node-card-header">
            <div id="node-details-title" class="node-card-title"></div>
            <button type="button" class="node-card-close" onclick="closeNodeCard()" title="Закрыть">✕</button>
        </div>
        <div id="node-details-desc" class="node-card-desc"></div>
        <div id="node-action-btn-box" style="display: none;"></div>
    </div>

    <script type="text/javascript">
        function detectDarkTheme() {{
            try {{
                if (window.parent && window.parent.document && window.parent.document.body) {{
                    return window.parent.document.body.classList.contains('dark-mode');
                }}
            }} catch(e) {{}}
            return localStorage.getItem('theme') === 'dark';
        }}

        const isDark = detectDarkTheme();
        if (isDark) document.body.classList.add('dark-mode');

        window.addEventListener('message', function(e) {{
            if (e.data && e.data.type === 'theme-change') {{
                if (e.data.isDark) {{
                    document.body.classList.add('dark-mode');
                }} else {{
                    document.body.classList.remove('dark-mode');
                }}
                location.reload();
            }}
        }});

        function closeNodeCard() {{
            var card = document.getElementById('node-floating-card');
            if (card) card.style.display = 'none';
        }}

        function openNodeSlug(slug) {{
            if (!slug) return;
            try {{
                if (window.parent && typeof window.parent.openEvidenceInspector === 'function') {{
                    window.parent.openEvidenceInspector(slug);
                }} else {{
                    window.location.href = `/evidence/drawer/${{encodeURIComponent(slug)}}`;
                }}
            }} catch(e) {{
                console.error(e);
            }}
        }}

        const nBg = isDark ? 'rgba(30,41,59,0.92)' : 'rgba(255,255,255,0.92)';
        const txtC = isDark ? '#f8fafc' : '#0f172a';
        const strkC = isDark ? '#0f172a' : '#ffffff';
        const edgeC = isDark ? 'rgba(255,255,255,0.22)' : 'rgba(0,0,0,0.15)';

        const rawNodes = {raw_nodes_json};
        const rawEdges = {raw_edges_json};
        const nodeData = {node_data_json};

        var nodes = new vis.DataSet(rawNodes.map(function(n) {{
            return {{
                id: n.id,
                label: n.label,
                color: {{ background: nBg, border: n.border || '#10b981' }},
                borderWidth: 2.5,
                font: {{ color: txtC, size: n.id === 1 ? 13 : 11, strokeWidth: 3, strokeColor: strkC, face: 'Inter' }},
                shape: n.shape || 'dot',
                size: n.size || 22,
                shadow: {{ enabled: true, color: (n.border || '#10b981') + '44', size: 16, x: 0, y: 0 }}
            }};
        }}));

        var edges = new vis.DataSet(rawEdges.map(function(e) {{
            return {{
                from: e.from,
                to: e.to,
                value: e.value || 2,
                label: e.label || '',
                dashes: !!e.dashes,
                font: {{ align: 'middle', size: e.dashes ? 10 : 12, color: txtC, strokeWidth: 2, strokeColor: strkC, face: 'Inter' }},
                color: {{ color: edgeC }}
            }};
        }}));

        var container = document.getElementById('mynetwork');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            physics: {{
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {{ gravitationalConstant: -110, centralGravity: 0.006, springLength: 220, springConstant: 0.045 }}
            }},
            interaction: {{ hover: true, tooltipDelay: 150 }}
        }};
        
        var network = new vis.Network(container, data, options);

        function openNodeSlug(slug) {{
            if (!slug) return;
            try {{
                if (window.parent && typeof window.parent.openEvidenceInspector === 'function') {{
                    window.parent.openEvidenceInspector(slug);
                }} else {{
                    window.location.href = `/evidence/drawer/${{encodeURIComponent(slug)}}`;
                }}
            }} catch(e) {{
                console.error(e);
            }}
        }}
        
        network.on("click", function (params) {{
            if (params.nodes.length > 0) {{
                var nodeId = String(params.nodes[0]);
                var info = nodeData[nodeId];
                if (info) {{
                    var card = document.getElementById('node-floating-card');
                    if (card) card.style.display = 'block';
                    document.getElementById('node-details-title').innerText = info.title || '';
                    document.getElementById('node-details-desc').innerText = info.desc || '';
                    var btnBox = document.getElementById('node-action-btn-box');
                    if (btnBox) {{
                        if (info.slug) {{
                            btnBox.innerHTML = '<button type="button" class="graph-action-btn" onclick="openNodeSlug(\\'' + info.slug + '\\')">📄 Открыть первоисточник</button>';
                            btnBox.style.display = 'block';
                        }} else {{
                            btnBox.innerHTML = '';
                            btnBox.style.display = 'none';
                        }}
                    }}
                }}
            }} else {{
                closeNodeCard();
            }}
        }});

        network.on("doubleClick", function (params) {{
            if (params.nodes.length > 0) {{
                var nodeId = String(params.nodes[0]);
                var info = nodeData[nodeId];
                if (info && info.slug) {{
                    openNodeSlug(info.slug);
                }}
            }}
        }});
    </script>
</body>
</html>
"""


def get_graph_html(
    query: str,
    documents: Optional[List[Any]] = None,
    score_display: Optional[str] = None,
    algorithm_display: str = "LanceDB + BM25 + Reranker",
    embedded: bool = False,
) -> str:
    """
    Дашборд графа с поддержкой темной/светлой темы (glass effect)
    и динамической визуализацией документов RAG.
    """
    if documents and len(documents) > 0:
        raw_nodes = []
        raw_edges = []
        node_data = {}

        
        raw_nodes.append({
            "id": 1,
            "label": f'"{query[:28]}..."' if len(query) > 28 else f'"{query}"',
            "border": "#10b981",
            "size": 30,
        })
        node_data["1"] = {
            "title": "Поисковый запрос",
            "desc": f"Исходный текст: {query}",
            "slug": "",
        }

        
        top_score_val = None
        for i, doc in enumerate(documents[:6]):
            doc_id = i + 2
            p_code = getattr(doc, "product_code", None) or "DOC"
            p_name = getattr(doc, "product_name", None) or getattr(doc, "title", None) or getattr(doc, "slug", f"doc_{i}")
            doc_slug = getattr(doc, "slug", "")
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
                "slug": doc_slug,
            }

            raw_edges.append({
                "from": 1,
                "to": doc_id,
                "value": max(1, int(score * 3) if 0 <= score <= 1 else 2),
                "label": f" {score_str}",
                "dashes": False,
            })

            
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
                    "slug": doc_slug,
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
            "1": {"title": "Поисковый запрос", "desc": "Исходный текст, введённый пользователем.", "slug": ""},
            "2": {"title": "Документ: P701 (Искра)", "desc": "Внутренний регламент ежедневных расчетов продукта Искра. Обнаружено точное совпадение по лимитам.", "slug": "p701-daily-settlement"},
            "3": {"title": "Документ: P704 (Мостик)", "desc": "Описание процесса финансирования и кредитных лимитов продукта Мостик. Релевантность высокая.", "slug": "p704-credit-limits"},
            "4": {"title": "Вложение: P701_table.png", "desc": "Скан-копия таблицы лимитов (обработана модулем OCR). Подтверждает данные из P701.", "slug": "p701-daily-settlement"},
        }
        if score_display is None:
            score_display = "96.4%"

    return _render_visjs_page(
        page_title=f"Граф связей - {query}",
        raw_nodes=raw_nodes,
        raw_edges=raw_edges,
        node_data=node_data,
    )


def get_document_graph_html(
    slug: str,
    evidence_service: Any,
    embedded: bool = True,
) -> str:
    """
    Интерактивный граф взаимосвязей для конкретного документа:
    - Центральный узел: сам документ
    - Кластерный узел: родительский продукт
    - Узел вложения: спецификация/таблица/код (если есть)
    - Смежные документы: регламенты по тому же продукту
    - Внутренние гиперссылки: упомянутые в тексте документы
    """
    ev = evidence_service.get_evidence(slug)
    if not ev:
        return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:2rem;color:#ef4444;"><h3>Документ не найден</h3><p>Документ <code>{html.escape(slug)}</code> отсутствует в базе знаний.</p></body></html>"""

    title = ev.get("title", slug)
    p_code = ev.get("product_code", "DOC")
    p_name = ev.get("product_name", "")
    p_color = ev.get("product_color", PRODUCT_COLOR_PALETTE.get(p_code, "#10b981"))
    section = ev.get("section", "Регламент")
    rendered_doc = ev.get("doc_html", "")

    raw_nodes = []
    raw_edges = []
    node_data = {}

    
    doc_short_title = title if len(title) <= 24 else title[:22] + "..."
    raw_nodes.append({
        "id": 1,
        "label": f"📄 {doc_short_title}",
        "border": p_color,
        "size": 28,
        "shape": "box",
    })
    node_data["1"] = {
        "title": f"Документ: {title}",
        "desc": f"Слаг: {slug}\nРаздел: {section}\nСтатус: {ev.get('lifecycle', 'ACTIVE')}",
        "slug": slug,
    }

    
    prod_label = f"🏷️ {p_name} ({p_code})" if p_name else p_code
    raw_nodes.append({
        "id": 2,
        "label": prod_label,
        "border": p_color,
        "size": 24,
    })
    node_data["2"] = {
        "title": f"Продукт: {p_name} ({p_code})",
        "desc": f"Кластер продуктов базы знаний «Меридиан».\nОбъединяет регламенты, вложения и правила для {p_name}.",
        "slug": slug,
    }
    raw_edges.append({
        "from": 2,
        "to": 1,
        "value": 3,
        "label": " регламент",
        "dashes": False,
    })

    current_id = 3

    
    att = ev.get("attachment")
    if att:
        att_filename = att.get("filename", "Вложение")
        att_fmt = att.get("format", "FILE")
        raw_nodes.append({
            "id": current_id,
            "label": f"📎 {att_filename}",
            "border": "#f59e0b",
            "size": 20,
        })
        att_raw = att.get("raw_text", "")
        att_snip = (att_raw[:180] + "...") if len(att_raw) > 180 else (att_raw or "Файл вложения.")
        node_data[str(current_id)] = {
            "title": f"Вложение: {att_filename} ({att_fmt})",
            "desc": f"Формат: {att_fmt}\nСодержимое: {att_snip}",
            "slug": slug,
        }
        raw_edges.append({
            "from": 1,
            "to": current_id,
            "value": 2,
            "label": " вложение",
            "dashes": True,
        })
        current_id += 1

    
    related_docs = ev.get("related_documents") or []
    for sib in related_docs[:5]:
        sib_slug = sib.get("slug")
        sib_label = sib.get("topic") or sib_slug
        if len(sib_label) > 20:
            sib_label = sib_label[:18] + "..."
        raw_nodes.append({
            "id": current_id,
            "label": f"📑 {sib_label}",
            "border": p_color,
            "size": 18,
        })
        node_data[str(current_id)] = {
            "title": f"Смежный регламент: {sib.get('title', sib_slug)}",
            "desc": f"Раздел: {sib.get('section', 'Смежный')}\nСлаг: {sib_slug}",
            "slug": sib_slug,
        }
        raw_edges.append({
            "from": 2,
            "to": current_id,
            "value": 1,
            "label": " подраздел",
            "dashes": False,
        })
        current_id += 1

    
    linked_slugs = set(re.findall(r"openEvidenceInspector\(['\"]([a-zA-Z0-9_\-]+)['\"]", rendered_doc))
    for l_slug in list(linked_slugs)[:4]:
        if l_slug == slug or any(node_data.get(str(nid), {}).get("slug") == l_slug for nid in range(1, current_id)):
            continue
        raw_nodes.append({
            "id": current_id,
            "label": f"🔗 {l_slug}",
            "border": "#3b82f6",
            "size": 18,
        })
        node_data[str(current_id)] = {
            "title": f"Перекрёстная ссылка: {l_slug}",
            "desc": f"Документ упоминается в тексте текущего регламента через внутреннюю гиперссылку.",
            "slug": l_slug,
        }
        raw_edges.append({
            "from": 1,
            "to": current_id,
            "value": 2,
            "label": " сноска",
            "dashes": True,
        })
        current_id += 1

    return _render_visjs_page(
        page_title=f"Граф связей - {title}",
        raw_nodes=raw_nodes,
        raw_edges=raw_edges,
        node_data=node_data,
    )


def get_mock_graph_html(query: str, embedded: bool = False) -> str:
    """Backwards compatibility helper."""
    return get_graph_html(query, documents=None, embedded=embedded)


