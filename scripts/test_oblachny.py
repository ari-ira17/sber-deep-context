import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.orchestrator import MeridianOrchestrator
from app.evidence import evidence_service
import asyncio

async def test():
    query = "Составьте контекст для эскалации по качеству данных продукта «Облачный Сад»: укажите код продукта, раздел, владельца, действующую методику и признаки качества страницы."
    print(f"Question: {query}")
    
    orchestrator = MeridianOrchestrator()
    print("Running orchestrator...\n")
    
    try:
        response = orchestrator.ask(query)
        
        print("\n--- Model Response ---")
        print(response.answer)
        print("----------------------\n")
        
        with open("oblachny_response.txt", "w") as f:
            f.write(response.answer)
        print("Response successfully saved to oblachny_response.txt")
            
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(test())
