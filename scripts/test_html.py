import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.orchestrator import MeridianOrchestrator
from app.evidence import evidence_service
import markdown
from jinja2 import Environment, FileSystemLoader

def main():
    question = "Подготовьте краткую карточку продукта «Орбитариум»: назовите его код, направление, владельца, версию методики и текущий жизненный цикл."
    orchestrator = MeridianOrchestrator()
    resp = orchestrator.ask(question)
    
    html_answer = markdown.markdown(
        resp.answer,
        extensions=["extra", "tables", "fenced_code", "nl2br"]
    )

    html_answer = evidence_service.enhance_citations(html_answer, active_citations=resp.citations)

    sources = []
    for doc in resp.sources:
        sources.append({
            "code": doc.product_code or "—",
            "name": doc.product_name or doc.title or "Документ",
            "section": doc.section or "Общий раздел",
            "score": 0.99,
            "attachment": "",
            "slug": doc.slug,
        })
        
    env = Environment(loader=FileSystemLoader("app/templates"))
    template = env.get_template("partials/bot_message.html")
    
    final_html = template.render(
        html_answer=html_answer,
        sources=sources,
        query=question,
        logs=resp.logs
    )
    
    with open("test_html_output.html", "w") as f:
        f.write(final_html)
    print("Done")

if __name__ == "__main__":
    main()
