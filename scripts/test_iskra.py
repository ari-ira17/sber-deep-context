import os
import sys

# Add parent directory to sys.path to allow imports from agents
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.orchestrator import MeridianOrchestrator

def main():
    question = "Подготовьте краткую карточку продукта «Искра»: назовите его код, направление, владельца, версию методики и текущий жизненный цикл."
    print(f"Question: {question}")
    
    orchestrator = MeridianOrchestrator()
    print("Running orchestrator...")
    
    response = orchestrator.ask(question)
    
    print("\n--- Model Response ---")
    print(response.answer)
    print("----------------------")
    
    output_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'iskra_response.txt'))
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Question: {question}\n\n")
        f.write(f"Answer:\n{response.answer}\n\n")
        f.write(f"Citations: {response.citations}\n")
        f.write(f"Latency (sec): {response.latency_sec}\n")
        f.write(f"Sources retrieved: {len(response.sources)}\n")
        
    print(f"\nResponse successfully saved to {output_file}")

if __name__ == "__main__":
    main()
