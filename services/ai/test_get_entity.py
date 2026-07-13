import asyncio
from app.agent_core.tools.primitives.get_entity import GetEntityInput, run_get_entity

async def main():
    payload = GetEntityInput(entity_type="student_profile", entity_id="student_123")
    env = await run_get_entity(payload)
    print("ok:", env.ok)
    print("error:", env.error)

if __name__ == "__main__":
    asyncio.run(main())
