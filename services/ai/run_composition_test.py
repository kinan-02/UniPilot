import asyncio
from datetime import datetime, timezone
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError
from app.agent_core.synthesis.synthesis import compose_answer
from app.agent_core.planning.state import PlanExecutionState, StateEntry, CertaintyTag
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.tools.registry import ToolRegistry

class LoggingAdapter(ChatLLMAdapter):
    async def complete_json(self, *args, **kwargs):
        try:
            return await super().complete_json(*args, **kwargs)
        except Exception as e:
            if "raw_model_text_out" in kwargs and kwargs["raw_model_text_out"]:
                print("RAW TEXT:")
                print(kwargs["raw_model_text_out"][0])
            raise

async def main():
    state = PlanExecutionState(plan_id="test")
    state.append(StateEntry(
        entry_id="1a-0",
        step_id="1a",
        role="retrieval",
        status="succeeded",
        output_schema_name="retrieval_agent_output_v1",
        data={
            "certainty_basis": "official_record",
            "confidence": 1.0,
            "facts": {
                "completed_courses": [
                    {
                        "course_id": "00140003",
                        "course_name": "Statistics",
                        "semester": "2024-1",
                        "grade": 92,
                        "grade_points": 4.0,
                        "credits_earned": 3.5
                    }
                ]
            }
        },
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
        produced_at=datetime.now(timezone.utc)
    ))
    
    role_roster = build_default_role_roster()
    role = role_roster["composition"]
    adapter = LoggingAdapter()
    result = await compose_answer(
        state=state,
        user_goal="What courses have I already completed?",
        composition_role=role,
        tool_registry=ToolRegistry(),
        llm_adapter=adapter,
        block_id="test"
    )
    print("STATUS:", result.status)
    if result.warnings:
        print("WARNINGS:", result.warnings)

if __name__ == "__main__":
    asyncio.run(main())
