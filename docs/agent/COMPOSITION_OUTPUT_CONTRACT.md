# `composition_agent_output_v1`

Used by the `composition` role (the fourth of five generic-path reasoning block migrations).

## Schema

```json
{
  "type": "object",
  "properties": {"answer_text": {"type": "string"}},
  "required": ["answer_text"],
  "additionalProperties": false
}
```

The schema mandates exactly one field: `answer_text`, matching the strict format of the `compose_answer` primitive.

## Design Constraints
- **Zero Tool Access**: As detailed in `AGENT_VISION.md` §6/§7.2, the composition role NEVER receives tool access. It must construct its output entirely from the state it's handed, providing a hard guarantee against introducing ungrounded facts at the final step.
- **Strict Semantic Check**: Returning a blank string or placeholder for `answer_text` violates the spirit of the schema even if it technically validates. The reasoning block applies an explicit semantic check for emptiness.

## Error Vocabulary & Retries
The composition block fails closed rather than returning partial ungrounded prose. Failures emit `composition_failed: <reason>` in their `warnings`:
- `schema_validation_failed`: Triggered if the LLM fails to match the single-field schema or violates `additionalProperties: false`, and repair exhausts.
- `empty_answer_text`: Triggered if `answer_text` is empty whitespace or the standard placeholder.

**Retry Policy**: The wrapper (`run_composition_subagent`) automatically catches `empty_answer_text` (and by extension `result_is_missing`) and retries once, fulfilling the resilience behavior originally baked into `synthesis.py`.
