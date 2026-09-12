def get_mock_graph_html(query: str) -> str:
    """
    Дашборд графа с поддержкой темной/светлой темы (glass effect).
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Анализ графа - {query}</title>
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
                <div style="font-weight: 500; line-height: 1.4;">"{query}"</div>
            </div>
            
            <div class="metric-card" id="node-details-card">
                <div class="metric-label" style="color: #3b82f6;">Информация об узле</div>
                <div id="node-details-title" style="font-weight: 600; margin-bottom: 0.5rem; font-size: 1.1rem;"></div>
                <div id="node-details-desc" style="font-size: 0.9rem; color: var(--text-muted); line-height: 1.5;"></div>
            </div>
            
            <div class="metric-card" style="display: flex; gap: 1rem; margin-top: 1rem;">
                <div style="flex:1;">
                    <div class="metric-label">Точность (Score)</div>
                    <div class="metric-value">96.4%</div>
                </div>
                <div style="flex:1;">
                    <div class="metric-label">Алгоритм</div>
                    <div class="metric-value" style="color: var(--text-muted); font-size: 1rem; margin-top: 4px;">RRF + Vector</div>
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

            var nodes = new vis.DataSet([
                {{ id: 1, label: '"{query}"', color: {{ background: nBg, border: '#10b981' }}, borderWidth: 3, font: {{color: txtC, size: 14, strokeWidth: 3, strokeColor: strkC}}, shape: 'dot', size: 30, shadow: {{enabled: true, color: 'rgba(16, 185, 129, 0.4)', size: 25, x:0, y:0}} }},
                {{ id: 2, label: 'P701 (Искра)', color: {{ background: nBg, border: '#3b82f6' }}, borderWidth: 3, font: {{color: txtC, size: 14, strokeWidth: 3, strokeColor: strkC}}, shape: 'dot', size: 22, shadow: {{enabled: true, color: 'rgba(59, 130, 246, 0.4)', size: 20, x:0, y:0}} }},
                {{ id: 3, label: 'P704 (Мостик)', color: {{ background: nBg, border: '#3b82f6' }}, borderWidth: 3, font: {{color: txtC, size: 14, strokeWidth: 3, strokeColor: strkC}}, shape: 'dot', size: 22, shadow: {{enabled: true, color: 'rgba(59, 130, 246, 0.4)', size: 20, x:0, y:0}} }},
                {{ id: 4, label: 'P701_table.png', color: {{ background: nBg, border: '#f59e0b' }}, borderWidth: 3, font: {{color: txtC, size: 14, strokeWidth: 3, strokeColor: strkC}}, shape: 'dot', size: 18, shadow: {{enabled: true, color: 'rgba(245, 158, 11, 0.4)', size: 20, x:0, y:0}} }}
            ]);

            var edges = new vis.DataSet([
                {{ from: 1, to: 2, value: 3, label: ' 96%', font: {{align: 'middle', size: 13, color: txtC, strokeWidth: 2, strokeColor: strkC}}, color: {{color: edgeC}} }},
                {{ from: 1, to: 3, value: 2, label: ' 82%', font: {{align: 'middle', size: 13, color: txtC, strokeWidth: 2, strokeColor: strkC}}, color: {{color: edgeC}} }},
                {{ from: 2, to: 4, value: 1, dashes: true, color: {{color: edgeC}}, label: ' вложение', font: {{align: 'middle', size: 11, color: txtC, strokeWidth: 2, strokeColor: strkC}} }}
            ]);

            var nodeData = {{
                1: {{ title: "Поисковый запрос", desc: "Исходный текст, введённый пользователем." }},
                2: {{ title: "Документ: P701 (Искра)", desc: "Внутренний регламент ежедневных расчетов продукта Искра. Обнаружено точное совпадение по лимитам." }},
                3: {{ title: "Документ: P704 (Мостик)", desc: "Описание процесса финансирования и кредитных лимитов продукта Мостик. Релевантность высокая." }},
                4: {{ title: "Вложение: P701_table.png", desc: "Скан-копия таблицы лимитов (обработана модулем OCR). Подтверждает данные из P701." }}
            }};

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
                    var nodeId = params.nodes[0];
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
