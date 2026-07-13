import json

with open("tests/agent_core/live_eval_logs/full_agent_e2e-20260713T090816Z.json") as f:
    logs = json.load(f)

for case in logs:
    case_name = case.get("case")
    calls = case.get("calls", [])
    total_calls = len(calls)
    
    # Count planner calls
    planner_calls = sum(1 for c in calls if c.get("output_schema_name") == "planner_invocation_output_v1")
    
    # Count tool invocations inside calls
    tool_requests = sum(len(c.get("parsed_response", {}).get("tool_requests", [])) for c in calls if c.get("parsed_response"))
    
    # Extract the final answer / synthesis if available
    final_state = case.get("state_entries", [])[-1] if case.get("state_entries") else {}
    
    print(f"Case: {case_name}")
    print(f"  Total LLM Calls: {total_calls}")
    print(f"  Planner Calls: {planner_calls}")
    print(f"  Tool Requests: {tool_requests}")
    print("-" * 40)
