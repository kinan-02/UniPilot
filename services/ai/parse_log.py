import json

with open("tests/agent_core/live_eval_logs/specialist_subagents-20260712T113527Z.json") as f:
    data = json.load(f)

for case in data:
    if case["case"] == "retrieval_fetches_real_completed_courses":
        for i, call in enumerate(case["calls"]):
            role = call.get("phase") or call.get("contract_name")
            if "Retrieval" in str(call.get("system_prompt")):
                print(f"\n[Call {i+1} Retrieval]")
                print("RAW RESPONSE:", call.get("raw_response_text", "")[:300])
            if "Planner" in str(call.get("system_prompt")):
                print(f"\n[Call {i+1} Planner]")
                print("RAW RESPONSE:", call.get("raw_response_text", "")[:300])
            if "Composition" in str(call.get("system_prompt")):
                print(f"\n[Call {i+1} Composition]")
                print("RAW RESPONSE:", call.get("raw_response_text", "")[:300])
        break
