import asyncio
from app.agent_core.tools.primitives.search_knowledge import SearchKnowledgeInput, run_search_knowledge

async def main():
    payload = SearchKnowledgeInput(query="Machine Learning", limit=5)
    env = await run_search_knowledge(payload)
    print("ok:", env.ok)
    print("error:", env.error)

if __name__ == "__main__":
    asyncio.run(main())
