# Graph Report - services/agent/app/agent/evaluation  (2026-07-06)

## Corpus Check
- 38 files · ~16,305 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 389 nodes · 773 edges · 16 communities (15 shown, 1 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 68 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `aa2dd9e7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]

## God Nodes (most connected - your core abstractions)
1. `EvalCase` - 28 edges
2. `EvalCaseResult` - 21 edges
3. `evaluate_promotion_readiness()` - 18 edges
4. `EvalSideEffectFirewall` - 14 edges
5. `run_final_answer_eval_case()` - 13 edges
6. `evaluate_case_result()` - 13 edges
7. `build_readiness_scorecard()` - 13 edges
8. `sanitize_eval_payload()` - 13 edges
9. `score_agent_turn()` - 12 edges
10. `run_full_llm_shadow_eval_case()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `run_agent_benchmark_case()` --calls--> `setup_eval_user()`  [INFERRED]
  agent_eval_runner.py → agent_setup.py
- `_run()` --calls--> `run_agent_benchmark_case()`  [INFERRED]
  run_agent_eval.py → agent_eval_runner.py
- `run_agent_http_benchmark_case()` --calls--> `score_agent_turn()`  [INFERRED]
  agent_http_runner.py → agent_eval_scorer.py
- `run_final_answer_eval_case()` --calls--> `setup_eval_user()`  [INFERRED]
  final_answer_runner.py → agent_setup.py
- `_reasoning_patch()` --calls--> `FakeReasoningBlockRunner`  [INFERRED]
  full_shadow_runner.py → fake_reasoning.py

## Import Cycles
- None detected.

## Communities (16 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (64): FactStatus, aggregate_final_answer_summary(), _bilingual_name_match(), build_final_answer_eval_report(), _check_condition_fact(), _check_course_code_fact(), _check_credit_fact(), _check_grade_fact() (+56 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (40): BaseModel, compute_eval_run_summary(), Aggregate metrics for offline eval runs (Phase 23)., candidate_case_ids(), _clarification_correctness(), _count_safety_metric(), default_promotion_candidates(), _diverse_coverage() (+32 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (42): _append_persisted_blocks(), build_http_client(), Any, AsyncClient, Execute agent benchmark cases through HTTP API routes., Run one benchmark case end-to-end via HTTP., run_agent_http_benchmark_case(), _send_agent_message() (+34 more)

### Community 3 - "Community 3"
Cohesion: 0.10
Nodes (31): _collect_case_paths(), load_eval_cases(), _load_json_file(), _load_jsonl_file(), Any, Path, Load sanitized offline eval cases (Phase 23)., Load, validate, and sanitize eval cases. Never executes fixture content. (+23 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (25): build_full_llm_shadow_lab_settings(), _build_live_response(), AgentResponse, Any, Settings, Full LLM shadow replay runner for eval lab (Phase 26)., Run one case through the full LLM shadow lab pipeline., Recommended lab settings for full LLM shadow replay. (+17 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (23): EvalCaseKind, detect_possible_private_identifiers(), Any, Conservative private-identifier scanner for real-world eval imports (Phase 26)., Detect obvious private identifiers in an import payload. Conservative, not perfe, convert_real_world_case_to_eval_case(), _deterministic_case_id(), import_real_world_cases() (+15 more)

### Community 6 - "Community 6"
Cohesion: 0.14
Nodes (22): _append_persisted_blocks(), _collect_agent_turn(), _event_to_dict(), Any, AsyncIOMotorDatabase, StreamEvent, Execute one agent benchmark case and collect turn output., Run setup, agent turn, and scoring for one benchmark case. (+14 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (13): assert_readiness_eval_safe(), Static safety checks for readiness evaluation modules (Phase 24)., scan_readiness_forbidden_patterns(), RuntimeError, assert_eval_replay_safe(), Static safety checks for offline eval package (Phase 23)., scan_eval_replay_forbidden_patterns(), EvalSideEffectFirewall (+5 more)

### Community 8 - "Community 8"
Cohesion: 0.25
Nodes (14): EvalMode, ProgressReporter, _build_live_response(), AgentResponse, Any, Settings, Offline replay runner for autonomous agent eval (Phase 23 + Phase 26)., Run one eval case offline. Never writes student data or calls real LLM by defaul (+6 more)

### Community 9 - "Community 9"
Cohesion: 0.33
Nodes (14): check_oracle_contradictions(), compute_course_lookup_oracle_facts(), compute_graduation_oracle_facts(), compute_prerequisite_oracle_facts(), compute_requirement_bucket_oracle_facts(), compute_semester_plan_oracle_facts(), _courses(), _degree() (+6 more)

### Community 10 - "Community 10"
Cohesion: 0.33
Nodes (12): build_observed_from_case(), _check_promotion(), evaluate_case_result(), _gate(), _intent_matches(), _normalize_clarification_action(), Any, Extract observed behavior and evaluate eval gates (Phase 23). (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.35
Nodes (10): EvalUserContext, find_published_course_id(), find_published_program(), Any, AsyncIOMotorDatabase, Settings, Seed users and student data for agent evaluation runs., Create an isolated eval user, optional profile, and conversation. (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.27
Nodes (6): FakeReasoningBlockRunner, ReasoningBlockInput, ReasoningBlockOutput, Fake ReasoningBlock outputs for offline shadow replay (Phase 23)., Deterministic mock ReasoningBlock — never calls a real LLM., MockReasoningOutput

### Community 13 - "Community 13"
Cohesion: 0.42
Nodes (8): _collect_manifest_paths(), load_eval_suites(), _load_json_file(), _load_jsonl_file(), Any, Path, Load evaluation suite manifests (Phase 24)., Load and validate suite manifests. Never executes content or calls network/LLM.

### Community 14 - "Community 14"
Cohesion: 0.40
Nodes (4): Any, Markdown reporting for promotion readiness scorecards (Phase 24)., Render a compact Markdown readiness report without raw payloads., render_readiness_markdown_report()

## Knowledge Gaps
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_final_answer_eval_case()` connect `Community 0` to `Community 11`, `Community 7`?**
  _High betweenness centrality (0.364) - this node is a cross-community bridge._
- **Why does `setup_eval_user()` connect `Community 11` to `Community 0`, `Community 6`?**
  _High betweenness centrality (0.336) - this node is a cross-community bridge._
- **Why does `run_agent_benchmark_case()` connect `Community 6` to `Community 2`, `Community 11`?**
  _High betweenness centrality (0.302) - this node is a cross-community bridge._
- **What connects `Conversation agent evaluation harness.  Includes: - Full-turn HTTP eval (`agent_`, `Execute one agent benchmark case and collect turn output.`, `Clarification turns persist blocks without streaming structured_output events.` to the rest of the system?**
  _79 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06189640035118525 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.09268707482993198 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.07712765957446809 - nodes in this community are weakly interconnected._