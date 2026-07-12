# Retrieval Output Contract

This document outlines the output contract of the `retrieval` role subagent (implemented via `RetrievalReasoningBlock`). 

The orchestrator and downstream subagents rely on this structure when parsing results from the `retrieval` role.

## Canonical Schema (`retrieval_agent_output_v1`)

```json
{
  "type": "object",
  "properties": {
    "certainty_basis": {
      "type": "string",
      "enum": [
        "official_record",
        "wiki_derived",
        "predicted_pattern",
        "llm_interpretation",
        "hypothetical_simulation"
      ]
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    },
    "source_ref": {
      "type": ["object", "null"],
      "properties": {
        "page": { "type": "string" },
        "section": { "type": ["string", "null"] },
        "reasoning_path": { "type": ["string", "null"] }
      },
      "required": ["page"]
    },
    "assumptions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "facts": {
      "type": "object",
      "description": "A dictionary of key-value pairs representing the structural or computed facts retrieved."
    }
  },
  "required": ["certainty_basis", "confidence", "facts"]
}
```

## Field Definitions

1. **`certainty_basis`**: Indicates the provenance level of the retrieved facts.
   - `official_record`: Sourced directly from a primary source (e.g., policy document or course catalog).
   - `wiki_derived`: Sourced from the knowledge graph or internal wiki.
   - `predicted_pattern`: Guessed or interpolated based on structural patterns.
   - `llm_interpretation`: The LLM's own interpretation or synthesis.
   - `hypothetical_simulation`: Derived from a simulation tool or hypothetical path.

2. **`confidence`**: A float between 0.0 and 1.0 indicating how confident the agent is in the exactness of the retrieved facts. 

3. **`source_ref`** *(optional)*: Pointer back to the exact location where this fact was found.
   - `page`: The ID, URL, or slug of the source (e.g., `MATH_101`).
   - `section` *(optional)*: The specific section or block ID.
   - `reasoning_path` *(optional)*: Explanation of how this source was reached if multiple hops were required.

4. **`assumptions`** *(optional)*: A list of any assumptions the agent had to make when resolving ambiguous data.

5. **`facts`**: The actual structured payload returned by the subagent. This must be a JSON object (`dict`), containing exactly the key-value structures requested by the user or the orchestrator prompt. Downstream systems expect this to be easily parseable.

## Orchestrator Mapping

When the `RetrievalReasoningBlock` returns its result, the orchestrator maps this schema into the `SubagentResult` object:

- `result.result` -> `facts`
- `result.certainty.basis` -> `certainty_basis`
- `result.certainty.confidence` -> `confidence`
- `result.certainty.source_ref` -> `source_ref`
- `result.assumptions` -> `assumptions`

Any downstream subagent relying on `retrieval` will see these facts natively unwrapped in its context via `dependency_state`.
