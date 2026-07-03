# UniPilot RAG Fine-Tuning Specification

## 1. Purpose

This document defines how UniPilot should tune, evaluate, and lock the hyperparameters for the retrieval and context-building layer used by the UniPilot Agent / MAS.

This document is intended for the RAG fine-tuning phase, after the main agent architecture, data indexing, and basic retrieval pipelines exist.

The goal is to make UniPilot’s retrieval layer:

* accurate,
* stable,
* fast,
* explainable,
* testable,
* grounded in the correct academic sources,
* optimized per task type,
* safe for high-stakes academic planning.

The system should not rely on intuition when choosing RAG parameters. Hyperparameters must be selected using a benchmark of realistic UniPilot retrieval tasks.

The final output of this phase should be a set of locked retrieval profiles that can be used by the Agent Context Builder.

---

## 2. Core Principle

The RAG system must follow this rule:

```text
Exact structured retrieval first.
Hybrid retrieval second.
LLM explanation last.
```

RAG should not replace deterministic academic services.

RAG is used to retrieve relevant academic context, catalog explanations, wiki sections, offering records, and source-grounding material.

The LLM must not invent academic facts.

The backend should use deterministic services for:

* graduation status,
* credit counting,
* requirement matching,
* prerequisite validation,
* schedule conflict validation,
* course offering availability,
* saved plan validation.

RAG supports the agent by retrieving the right context. It does not decide academic truth by itself.

---

## 3. Data Sources Covered by This Tuning Phase

The RAG tuning phase covers the retrieval behavior for these sources:

### 3.1 Obsidian Catalog Wiki Vault

The Obsidian catalog wiki contains the parsed Technion catalog.

It includes:

* degree program pages,
* track pages,
* requirement bucket pages,
* required course lists,
* elective pool descriptions,
* focus chain rules,
* catalog explanations,
* linked pages,
* indexes,
* academic rules,
* Hebrew academic text.

This source is mainly used for:

* requirement explanations,
* source grounding,
* catalog rule retrieval,
* user-facing explanations,
* linked academic context,
* fallback when structured data needs human-readable explanation.

### 3.2 Course Offerings JSON Files

The course offerings JSONs contain semester-specific course information.

They may include:

* course number,
* course name,
* semester,
* credits,
* prerequisites,
* lecture groups,
* tutorial groups,
* lab groups,
* schedule times,
* rooms,
* exam dates,
* instructors if available.

This source should be used in two ways:

1. Structured exact lookup.
2. Optional semantic / hybrid retrieval.

For planning and validation, structured lookup is mandatory.

The vector/hybrid index is useful for discovery queries such as:

```text
Find AI-related electives offered next semester.
Find courses with no Friday classes.
Find electives that can help with my track.
```

### 3.3 Structured Catalog / Requirements Data

If UniPilot stores catalog rules, requirements, course mappings, and buckets in structured database collections, these should be used for exact academic logic.

The RAG system can retrieve supporting wiki context, but the structured catalog should remain the source of truth for calculations.

### 3.4 MongoDB User-Specific Data

User-specific data is not tuned as part of public RAG.

MongoDB should be queried directly by authenticated `userId`.

Examples:

* student profile,
* degree program,
* track,
* catalog year,
* completed courses,
* saved plans,
* transcript imports,
* preferences,
* pending actions.

User-specific records should not be embedded into the shared catalog vector index.

---

## 4. What This Phase Must Produce

At the end of the RAG fine-tuning phase, the project should have:

```text
1. A retrieval benchmark dataset.
2. Retrieval evaluation scripts.
3. Tuned retrieval profiles per task type.
4. Locked default hyperparameters.
5. Regression tests for retrieval failures.
6. A retrieval profile configuration file.
7. Documentation of chosen parameters and why they were chosen.
8. Context-size and latency limits.
9. Acceptance criteria for retrieval quality.
```

Recommended output files:

```text
docs/agent/RAG_FINE_TUNING_SPEC.md
docs/agent/RAG_EVALUATION_RESULTS.md
app/retrieval/profiles.py
app/retrieval/profile_config.json
app/retrieval/evaluation/
  benchmark_cases.jsonl
  run_retrieval_eval.py
  retrieval_metrics.py
  failure_analysis.md
tests/retrieval/
  test_rag_profiles.py
  test_course_exact_lookup.py
  test_catalog_requirement_retrieval.py
  test_offerings_retrieval.py
```

---

## 5. Do Not Use One Global RAG Configuration

UniPilot must not use one global RAG configuration for all user requests.

Different task types need different retrieval behavior.

For example:

```text
Course-number queries need exact and keyword-heavy retrieval.
Natural language explanation queries need semantic retrieval.
Requirement bucket queries need metadata-filtered catalog retrieval.
Semester planning needs structured offerings and deterministic filtering.
```

Therefore, the system should define retrieval profiles.

---

## 6. Retrieval Profiles

Implement retrieval profiles for different task types.

Initial required profiles:

```text
course_exact_lookup
course_semantic_search
catalog_requirement_lookup
requirement_explanation
semester_offering_lookup
semester_planning_retrieval
general_catalog_question
transcript_course_matching
fallback_academic_search
```

Each profile should define:

```text
source priority
exact lookup behavior
metadata filters
vector topK
BM25 topK
hybrid weight
reranking behavior
link expansion behavior
final chunk count
max context tokens
fallback strategy
latency budget
```

---

## 7. Profile Selection by Intent

The Context Builder / Retrieval Planner should select a profile based on the resolved intent.

Example mapping:

```text
course_question
  -> course_exact_lookup
  -> semester_offering_lookup
  -> catalog_requirement_lookup if requirement contribution is needed

graduation_progress_check
  -> catalog_requirement_lookup
  -> requirement_explanation

requirement_explanation
  -> requirement_explanation

semester_plan_generation
  -> semester_planning_retrieval
  -> semester_offering_lookup
  -> catalog_requirement_lookup

semester_plan_modification
  -> semester_planning_retrieval
  -> semester_offering_lookup

catalog_search
  -> general_catalog_question

transcript_import
  -> transcript_course_matching
```

The profile selection should be explicit and logged in the `AgentRun`.

---

## 8. Initial Default Retrieval Profiles

The values below are starting points. They must be evaluated and tuned using the benchmark.

### 8.1 Profile: `course_exact_lookup`

Used for:

```text
Can I take 234218?
Is 234218 offered next semester?
What are the prerequisites for 234218?
Does 234218 count for my track?
```

Expected behavior:

* exact lookup first,
* course number matching,
* keyword-heavy retrieval,
* very small final context.

Initial config:

```json
{
  "profileName": "course_exact_lookup",
  "exactLookupFirst": true,
  "sources": ["structured_catalog", "structured_offerings", "obsidian_wiki"],
  "vectorTopK": 5,
  "bm25TopK": 10,
  "hybridVectorWeight": 0.15,
  "hybridKeywordWeight": 0.85,
  "rerankCandidateLimit": 20,
  "finalTopN": 3,
  "wikiChunksFinal": 2,
  "linkExpansionDepth": 0,
  "maxContextTokens": 2500,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 800
}
```

Acceptance target:

```text
Course number Hit@1 >= 0.95
Offering exact lookup Hit@1 >= 0.98
Wrong-semester retrieval rate <= 0.02
```

---

### 8.2 Profile: `course_semantic_search`

Used for:

```text
Find AI-related courses.
Find courses about databases.
Which electives are related to optimization?
Find courses similar to machine learning.
```

Expected behavior:

* semantic search is useful,
* metadata filters should still restrict semester/degree if known,
* final result should be course records, not only wiki chunks.

Initial config:

```json
{
  "profileName": "course_semantic_search",
  "exactLookupFirst": false,
  "sources": ["structured_catalog", "structured_offerings", "obsidian_wiki"],
  "vectorTopK": 40,
  "bm25TopK": 30,
  "hybridVectorWeight": 0.65,
  "hybridKeywordWeight": 0.35,
  "rerankCandidateLimit": 60,
  "finalTopN": 10,
  "wikiChunksFinal": 4,
  "linkExpansionDepth": 1,
  "maxLinkedChunks": 3,
  "maxContextTokens": 6000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 1800
}
```

Acceptance target:

```text
Recall@10 >= 0.80 for semantic course discovery queries
Precision@10 should be manually acceptable for planning use
```

---

### 8.3 Profile: `catalog_requirement_lookup`

Used for:

```text
What are my degree requirements?
What does the track require?
Which buckets do I need?
What counts as a track elective?
```

Expected behavior:

* strong metadata filtering,
* degree program / track / catalog year should dominate,
* retrieve exact requirement sections from the Obsidian wiki and structured catalog.

Initial config:

```json
{
  "profileName": "catalog_requirement_lookup",
  "exactLookupFirst": true,
  "sources": ["structured_requirements", "obsidian_wiki"],
  "vectorTopK": 30,
  "bm25TopK": 30,
  "hybridVectorWeight": 0.45,
  "hybridKeywordWeight": 0.55,
  "rerankCandidateLimit": 50,
  "finalTopN": 6,
  "wikiChunksFinal": 6,
  "linkExpansionDepth": 1,
  "maxLinkedChunks": 3,
  "maxContextTokens": 6000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 1500
}
```

Acceptance target:

```text
Recall@5 >= 0.85 for requirement bucket questions
Correct degree/track/catalog-year retrieval >= 0.95
```

---

### 8.4 Profile: `requirement_explanation`

Used for:

```text
Explain my missing electives.
Why is this bucket incomplete?
Why did this course not count?
What does this focus chain mean?
```

Expected behavior:

* retrieve human-readable catalog text,
* include related linked pages,
* include deterministic audit result if available,
* prioritize explanation quality.

Initial config:

```json
{
  "profileName": "requirement_explanation",
  "exactLookupFirst": true,
  "sources": ["structured_requirements", "obsidian_wiki"],
  "vectorTopK": 35,
  "bm25TopK": 35,
  "hybridVectorWeight": 0.55,
  "hybridKeywordWeight": 0.45,
  "rerankCandidateLimit": 70,
  "finalTopN": 8,
  "wikiChunksFinal": 8,
  "linkExpansionDepth": 1,
  "maxLinkedChunks": 5,
  "maxContextTokens": 8000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 2000
}
```

Acceptance target:

```text
Recall@8 >= 0.85 for explanation questions
User-facing answer should include correct rule and correct student status
```

---

### 8.5 Profile: `semester_offering_lookup`

Used for:

```text
Is this course offered next semester?
What lecture groups are available?
Does this course have tutorials?
When is the exam?
```

Expected behavior:

* exact structured lookup first,
* semester must be resolved,
* vector search should only be fallback or for discovery.

Initial config:

```json
{
  "profileName": "semester_offering_lookup",
  "exactLookupFirst": true,
  "sources": ["structured_offerings", "offering_vector_index"],
  "vectorTopK": 5,
  "bm25TopK": 10,
  "hybridVectorWeight": 0.10,
  "hybridKeywordWeight": 0.90,
  "rerankCandidateLimit": 20,
  "finalTopN": 3,
  "wikiChunksFinal": 0,
  "linkExpansionDepth": 0,
  "maxContextTokens": 3000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 700
}
```

Acceptance target:

```text
Exact course + semester offering Hit@1 >= 0.98
Wrong-semester retrieval rate <= 0.01
```

---

### 8.6 Profile: `semester_planning_retrieval`

Used for:

```text
Build me a semester plan.
Build a plan with no Friday classes.
Find offered electives that satisfy missing requirements.
Make the plan lighter.
```

Expected behavior:

* deterministic planner first,
* structured offerings first,
* RAG only supports discovery and explanation,
* do not pass all offerings to the LLM.

Initial config:

```json
{
  "profileName": "semester_planning_retrieval",
  "exactLookupFirst": true,
  "structuredPlannerFirst": true,
  "sources": ["structured_requirements", "structured_offerings", "obsidian_wiki", "offering_vector_index"],
  "vectorTopK": 40,
  "bm25TopK": 40,
  "hybridVectorWeight": 0.45,
  "hybridKeywordWeight": 0.55,
  "rerankCandidateLimit": 80,
  "finalTopN": 10,
  "wikiChunksFinal": 5,
  "linkExpansionDepth": 1,
  "maxLinkedChunks": 3,
  "maxContextTokens": 8000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 2500
}
```

Acceptance target:

```text
Eligible-course retrieval Recall@10 >= 0.85
Planning output must use structured offering records, not raw text chunks
No invented offerings
No invented prerequisites
```

---

### 8.7 Profile: `general_catalog_question`

Used for:

```text
What are the rules for this degree path?
How do focus chains work?
What is required to graduate?
Explain the catalog structure.
```

Expected behavior:

* semantic retrieval can be stronger,
* link expansion is useful,
* final context can include several wiki sections.

Initial config:

```json
{
  "profileName": "general_catalog_question",
  "exactLookupFirst": false,
  "sources": ["obsidian_wiki", "structured_requirements"],
  "vectorTopK": 40,
  "bm25TopK": 30,
  "hybridVectorWeight": 0.70,
  "hybridKeywordWeight": 0.30,
  "rerankCandidateLimit": 70,
  "finalTopN": 8,
  "wikiChunksFinal": 8,
  "linkExpansionDepth": 1,
  "maxLinkedChunks": 5,
  "maxContextTokens": 8000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 2200
}
```

Acceptance target:

```text
Recall@8 >= 0.80 for broad catalog questions
Retrieved context must match user degree/track when known
```

---

### 8.8 Profile: `transcript_course_matching`

Used for:

```text
Match parsed transcript rows to catalog courses.
Normalize course numbers and names.
Resolve uncertain transcript rows.
```

Expected behavior:

* exact course number matching first,
* fuzzy course name matching second,
* keyword-heavy retrieval,
* semantic search only for uncertain course names.

Initial config:

```json
{
  "profileName": "transcript_course_matching",
  "exactLookupFirst": true,
  "sources": ["structured_catalog", "obsidian_wiki"],
  "vectorTopK": 10,
  "bm25TopK": 20,
  "hybridVectorWeight": 0.25,
  "hybridKeywordWeight": 0.75,
  "rerankCandidateLimit": 30,
  "finalTopN": 5,
  "wikiChunksFinal": 2,
  "linkExpansionDepth": 0,
  "maxContextTokens": 4000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 1000
}
```

Acceptance target:

```text
Course-number matching accuracy >= 0.98
Course-name fuzzy matching accuracy >= 0.90
Uncertain rows should be marked uncertain, not guessed silently
```

---

### 8.9 Profile: `fallback_academic_search`

Used when:

* intent is unclear,
* entity resolution fails,
* initial retrieval fails,
* user asks a broad academic question.

Initial config:

```json
{
  "profileName": "fallback_academic_search",
  "exactLookupFirst": false,
  "sources": ["obsidian_wiki", "structured_catalog", "structured_offerings"],
  "vectorTopK": 50,
  "bm25TopK": 50,
  "hybridVectorWeight": 0.60,
  "hybridKeywordWeight": 0.40,
  "rerankCandidateLimit": 100,
  "finalTopN": 8,
  "wikiChunksFinal": 8,
  "linkExpansionDepth": 1,
  "maxLinkedChunks": 5,
  "maxContextTokens": 8000,
  "maxRetrievalAttempts": 2,
  "latencyBudgetMs": 3000
}
```

Acceptance target:

```text
Should retrieve useful sources for broad questions
Should not be used when exact lookup is available
```

---

## 9. Chunking Strategy

### 9.1 Obsidian Wiki Chunking

The Obsidian wiki should use structure-aware chunking.

Do not use blind fixed-size chunks only.

Chunk by:

```text
page
heading
subheading
semantic section
table section
rule block
course list
```

Recommended initial values:

```text
Target chunk size: 300–800 tokens
Maximum chunk size: 1,200 tokens
Overlap: 50–100 tokens only when section boundaries are weak
Minimum chunk size: 80–120 tokens, unless it is an important table/list
```

Each chunk must include:

```text
page title
heading path
source file
catalog year
faculty
degree program
track if known
requirement bucket if known
rule type if known
course numbers mentioned
outgoing links
incoming links if available
language
index version
```

The heading path must be included in both metadata and embedding text.

Example embedding text format:

```text
Page: הנדסת מערכות מידע
Heading path: דרישות השלמה לתואר > קורסי בחירה מסלולית
Catalog year: תשפ״ו
Degree program: הנדסת מערכות מידע

Content:
...
```

This helps chunks remain meaningful in isolation.

---

### 9.2 Obsidian Tables

If the wiki contains tables, treat each meaningful table as either:

```text
one table chunk
```

or:

```text
one chunk per logical row group
```

Do not split a table randomly in the middle of related rows.

For long tables:

```text
include table title
include column headers in every chunk
preserve course numbers
preserve requirement labels
```

---

### 9.3 Course Offerings JSON Chunking

Course offerings should use:

```text
one chunk per course per semester
```

No overlap is needed.

Each offering chunk should include:

```text
semester
course number
course name
credits
prerequisites
lecture groups
tutorial groups
lab groups
schedule summary
exam dates
raw text for embedding
structured fields
```

Important:

```text
The structured fields are used for validation and planning.
The embedding text is used for semantic discovery only.
```

---

## 10. Metadata Requirements

Metadata quality is a major part of RAG quality.

Every chunk should have strong metadata.

### 10.1 Required Metadata for Wiki Chunks

```text
chunkId
sourceType
sourceFile
pageTitle
sectionTitle
headingPath
catalogYear
faculty
degreeProgram
track
requirementBucket
ruleType
courseNumber
courseName
courseNumbersMentioned
outgoingLinks
incomingLinks
language
createdAt
updatedAt
indexVersion
```

Some fields may be null if not applicable, but the fields should exist.

### 10.2 Required Metadata for Offering Chunks

```text
chunkId
sourceType
semester
courseNumber
courseName
credits
hasLecture
hasTutorial
hasLab
hasExamDate
prerequisiteCourseNumbers
lectureGroupCount
tutorialGroupCount
labGroupCount
daysOfWeek
language
sourceFile
indexVersion
```

### 10.3 Required Metadata for Retrieval Results

Each retrieval result should include:

```text
chunkId
sourceType
sourceId
retrievalMethod
rawScore
normalizedScore
rank
matchedFilters
confidence
contentPreview
metadata
```

---

## 11. Metadata Filtering Strategy

Metadata filters should be applied before vector search whenever possible.

Use strict filters first, then relax only if retrieval fails.

Example for degree requirement retrieval:

```text
Attempt 1:
catalogYear + degreeProgram + track + ruleType

Attempt 2:
catalogYear + degreeProgram + ruleType

Attempt 3:
catalogYear + faculty + ruleType

Attempt 4:
sourceType only, with warning
```

Example for offering retrieval:

```text
Attempt 1:
semester + courseNumber

Attempt 2:
courseNumber only

Attempt 3:
semester + course name search

Attempt 4:
semantic offering search, with warning
```

The Context Validator must record when fallback retrieval was used.

---

## 12. Hybrid Search Weighting

Hybrid search should combine:

```text
dense vector search
keyword / BM25 search
exact matching boosts
metadata boosts
link graph boosts
```

Initial weighting by query type:

| Query Type                   | Vector Weight | Keyword Weight |
| ---------------------------- | ------------: | -------------: |
| Exact course number          |          0.15 |           0.85 |
| Course offering exact lookup |          0.10 |           0.90 |
| Transcript course matching   |          0.25 |           0.75 |
| Hebrew course name           |          0.40 |           0.60 |
| Requirement title            |          0.35 |           0.65 |
| Requirement explanation      |          0.55 |           0.45 |
| General catalog question     |          0.70 |           0.30 |
| Fuzzy academic question      |          0.70 |           0.30 |
| Planning discovery           |          0.45 |           0.55 |

These are starting points only.

The final values must be selected by benchmark results.

---

## 13. Reranking Strategy

After candidate retrieval, rerank results.

Reranking should consider:

```text
semantic similarity
keyword match
exact course number match
metadata match
source priority
degree/track/catalog-year match
semester match
link relevance
workflow relevance
recency/index version
```

The reranker should heavily boost exact matches.

Examples:

```text
If query contains course number 234218 and result has courseNumber 234218:
large boost.

If target semester is 2026_spring and result semester is 2026_spring:
large boost.

If user degree is Information Systems Engineering and result degreeProgram matches:
large boost.

If result is wrong catalog year:
large penalty.
```

Recommended initial reranking candidate sizes:

```text
Simple exact query: 20 candidates
Requirement query: 50–70 candidates
Planning query: 80 candidates
Fallback query: 100 candidates
```

Final context should usually include:

```text
Simple query: 1–3 chunks/records
Requirement explanation: 4–8 chunks
Planning: 5–10 chunks plus structured planner results
```

---

## 14. Link Graph Expansion

The Obsidian wiki has links between pages. Use link expansion carefully.

Initial settings:

```text
Default: off for exact course queries
Depth: 1 for requirement explanations and broad catalog questions
Max linked chunks: 3–5
Expansion only after initial retrieval
Rerank linked chunks before adding them to context
```

Do not blindly include all linked pages.

Good use cases:

```text
requirement bucket links to eligible course pool
track page links to focus chain page
degree program page links to course list page
catalog rule links to exception page
```

Bad use cases:

```text
course exact lookup where exact structured data is already enough
simple offering availability question
transcript matching
```

---

## 15. Context Size Limits

The Context Builder should enforce context size limits.

Initial limits:

| Workflow                 | Max Context Tokens |
| ------------------------ | -----------------: |
| Course question          |        2,500–4,000 |
| Offering question        |        2,500–3,500 |
| Requirement explanation  |        6,000–8,000 |
| Graduation audit         |       6,000–10,000 |
| Semester planning        |       8,000–12,000 |
| Transcript import review |        4,000–8,000 |
| General catalog question |        6,000–8,000 |

Important:

```text
Do not pass all retrieved chunks to the LLM.
Do not pass all course offerings to the LLM.
Do not pass entire user records unless needed.
```

The Context Builder should summarize or select context.

---

## 16. Retrieval Attempts and Fallbacks

Every retrieval profile should have a limited number of attempts.

Recommended:

```text
Max retrieval attempts per run: 2
Absolute max: 3
```

Attempt pattern:

```text
Attempt 1:
strict filters + exact lookup where available

Attempt 2:
relaxed filters + hybrid search

Attempt 3:
fallback search only if necessary, with explicit warning
```

If context is still insufficient:

```text
ask the user a clarification question
or continue with a visible warning
or fail with a useful missing-data message
```

Do not loop indefinitely.

---

## 17. Benchmark Dataset

Create a benchmark dataset before tuning.

Recommended MVP size:

```text
100–200 cases
```

Recommended mature size:

```text
500+ cases
```

The benchmark should represent real UniPilot usage.

### 17.1 Benchmark Case Schema

Use JSONL.

Each line should be one benchmark case.

Example:

```json
{
  "id": "course_exact_001",
  "query": "Can I take 234218 next semester?",
  "intent": "course_question",
  "profile": "course_exact_lookup",
  "language": "en",
  "entities": {
    "courseNumber": "234218",
    "targetSemester": "2026_spring"
  },
  "metadataContext": {
    "degreeProgram": "הנדסת מערכות מידע",
    "track": "הנדסת מערכות מידע",
    "catalogYear": "תשפ״ו"
  },
  "mustRetrieve": [
    "offering:2026_spring:234218",
    "course:234218"
  ],
  "acceptableSources": [
    "wiki:course:234218",
    "wiki:requirements:information_systems"
  ],
  "negativeSources": [
    "offering:2025_winter:234218"
  ],
  "notes": "Exact course number and semester query. Should use exact lookup."
}
```

### 17.2 Required Benchmark Categories

Include cases for:

```text
1. Exact course-number queries
2. Course name queries in Hebrew
3. Course name queries in English
4. Mixed Hebrew-English queries
5. Requirement bucket lookup
6. Requirement explanation
7. Graduation progress context retrieval
8. Track elective retrieval
9. Focus chain retrieval
10. Course offering lookup
11. Prerequisite retrieval
12. Semester planning discovery
13. Transcript course matching
14. Ambiguous course names
15. Wrong semester avoidance
16. Wrong track avoidance
17. Wrong catalog year avoidance
18. Broad catalog questions
19. Fuzzy academic questions
20. No-result / missing-data cases
```

---

## 18. Example Benchmark Cases

Add cases like these.

### 18.1 Exact Course Number

```json
{
  "id": "course_exact_234218",
  "query": "Can I take 234218 next semester?",
  "intent": "course_question",
  "profile": "course_exact_lookup",
  "language": "en",
  "entities": {
    "courseNumber": "234218",
    "targetSemester": "2026_spring"
  },
  "mustRetrieve": [
    "course:234218",
    "offering:2026_spring:234218"
  ],
  "negativeSources": [
    "offering:2025_winter:234218"
  ]
}
```

### 18.2 Hebrew Requirement Explanation

```json
{
  "id": "req_explain_he_001",
  "query": "תסביר לי את דרישות הבחירה במסלול הנדסת מערכות מידע",
  "intent": "requirement_explanation",
  "profile": "requirement_explanation",
  "language": "he",
  "metadataContext": {
    "degreeProgram": "הנדסת מערכות מידע",
    "catalogYear": "תשפ״ו"
  },
  "mustRetrieve": [
    "wiki:requirements:information_systems:track_electives"
  ]
}
```

### 18.3 Semester Planning

```json
{
  "id": "planning_001",
  "query": "Build me a plan for next semester with no Friday classes and not more than 20 credits.",
  "intent": "semester_plan_generation",
  "profile": "semester_planning_retrieval",
  "language": "en",
  "entities": {
    "targetSemester": "2026_spring",
    "avoidDays": ["Friday"],
    "maxCredits": 20
  },
  "mustRetrieveTypes": [
    "structured_requirements",
    "structured_offerings"
  ],
  "notes": "Planner should use structured offerings, not raw chunks."
}
```

### 18.4 Course Discovery

```json
{
  "id": "course_discovery_001",
  "query": "Find AI-related electives offered next semester.",
  "intent": "semester_plan_generation",
  "profile": "course_semantic_search",
  "language": "en",
  "entities": {
    "targetSemester": "2026_spring",
    "topic": "AI"
  },
  "mustRetrieveTypes": [
    "course_offering"
  ],
  "acceptableSources": [
    "offering:2026_spring:*",
    "wiki:topic:ai"
  ]
}
```

### 18.5 Transcript Matching

```json
{
  "id": "transcript_match_001",
  "query": "Match transcript row: 234218 מבני נתונים 3.0 credits",
  "intent": "transcript_import",
  "profile": "transcript_course_matching",
  "language": "mixed",
  "entities": {
    "courseNumber": "234218",
    "courseName": "מבני נתונים"
  },
  "mustRetrieve": [
    "course:234218"
  ]
}
```

---

## 19. Metrics

Evaluate retrieval with multiple metrics.

Required metrics:

```text
Hit@K
Recall@K
Precision@K
MRR
nDCG
wrong-source rate
wrong-semester rate
wrong-track rate
wrong-catalog-year rate
latency
final context token count
```

### 19.1 Most Important Metrics

For UniPilot, prioritize:

```text
1. Required-source Recall@K
2. Hit@K
3. Wrong-source avoidance
4. MRR / nDCG
5. Precision@K
6. Latency
7. Context size
```

For exact academic queries, Hit@1 matters a lot.

For explanation queries, Recall@5 or Recall@8 matters more.

---

## 20. Acceptance Targets

Initial MVP targets:

```text
Exact course-number queries:
Hit@1 >= 0.95

Exact offering lookup:
Hit@1 >= 0.98

Transcript course number matching:
Accuracy >= 0.98

Transcript fuzzy course-name matching:
Accuracy >= 0.90

Requirement explanation:
Recall@5 >= 0.85

Track / bucket retrieval:
Recall@5 >= 0.85

General catalog questions:
Recall@8 >= 0.80

Fuzzy academic questions:
Recall@8 >= 0.75

Wrong semester retrieval:
<= 0.02

Wrong track retrieval:
<= 0.05

Wrong catalog year retrieval:
<= 0.05

Normal retrieval latency:
< 1 second for simple queries

Complex hybrid retrieval latency:
< 2.5 seconds for complex queries
```

These targets may be adjusted after the first evaluation run, but the final values should be documented.

---

## 21. Evaluation Script Requirements

Build a retrieval evaluation runner.

Suggested script:

```text
app/retrieval/evaluation/run_retrieval_eval.py
```

The script should:

```text
1. Load benchmark_cases.jsonl.
2. Run each query through the retrieval planner.
3. Execute retrieval using the specified profile.
4. Record retrieved results.
5. Compute metrics.
6. Save per-case output.
7. Save aggregate metrics by profile.
8. Save failure cases.
```

Output files:

```text
app/retrieval/evaluation/results/
  latest_summary.json
  latest_cases.jsonl
  latest_failures.jsonl
  profile_metrics.json
```

Each evaluated case should store:

```json
{
  "caseId": "course_exact_234218",
  "profile": "course_exact_lookup",
  "query": "Can I take 234218 next semester?",
  "retrieved": [
    {
      "rank": 1,
      "sourceId": "offering:2026_spring:234218",
      "sourceType": "course_offering",
      "score": 0.98,
      "retrievalMethod": "exact_lookup"
    }
  ],
  "metrics": {
    "hitAt1": true,
    "hitAt5": true,
    "recallAt5": 1.0,
    "mrr": 1.0
  },
  "latencyMs": 142,
  "contextTokens": 1200,
  "passed": true
}
```

---

## 22. Failure Analysis

For every failed retrieval case, classify the failure.

Failure categories:

```text
wrong_metadata_filter
metadata_too_strict
metadata_too_loose
chunk_too_large
chunk_too_small
course_number_missed
course_name_missed
hebrew_text_missed
mixed_language_query_failed
wrong_semester
wrong_track
wrong_catalog_year
semantic_search_too_broad
keyword_search_too_strict
bm25_outperformed_vector
vector_outperformed_bm25
link_expansion_added_noise
reranker_removed_correct_result
exact_lookup_not_used
structured_source_missing
source_data_missing
ambiguous_query
benchmark_expected_source_wrong
```

Each failure should have a note.

Example:

```json
{
  "caseId": "req_explain_he_001",
  "failureType": "metadata_too_strict",
  "notes": "The correct chunk had degreeProgram metadata missing, so strict filter removed it."
}
```

Failures should be added to regression tests after they are fixed.

---

## 23. Tuning Process

Use the following process.

```text
1. Create initial benchmark dataset.
2. Run baseline retrieval.
3. Record metrics.
4. Inspect failed cases manually.
5. Tune one profile at a time.
6. Change one major parameter group at a time.
7. Re-run evaluation.
8. Compare metrics, latency, and context size.
9. Lock profile config when it passes targets.
10. Add failure cases to regression tests.
11. Document final values.
```

Do not tune all profiles together.

Recommended order:

```text
1. course_exact_lookup
2. semester_offering_lookup
3. transcript_course_matching
4. catalog_requirement_lookup
5. requirement_explanation
6. course_semantic_search
7. semester_planning_retrieval
8. general_catalog_question
9. fallback_academic_search
```

---

## 24. Tuning Grids

### 24.1 Obsidian Wiki Tuning Grid

Test selected combinations of:

```text
chunk size:
300, 500, 800, 1200 tokens

overlap:
0, 50, 100, 150 tokens

vector topK:
10, 20, 40

BM25 topK:
10, 20, 40

hybrid vector weight:
0.3, 0.5, 0.7

rerank candidate limit:
30, 50, 70

final topN:
5, 8, 12

link expansion:
off
depth 1 max 3 links
depth 1 max 5 links
```

Do not run the full Cartesian product if it is too large. Start with targeted experiments.

### 24.2 Course Offering Tuning Grid

Since offerings are naturally structured, chunking should remain one course per semester.

Tune:

```text
vector topK:
10, 20, 40

BM25 topK:
10, 20, 40

hybrid vector weight:
0.1, 0.3, 0.5

final topN:
3, 5, 10

metadata strictness:
semester + courseNumber
semester only
courseNumber only
relaxed fallback
```

### 24.3 Reranking Tuning Grid

Tune boosts and penalties:

```text
exact course number boost
exact semester boost
degree program match boost
track match boost
catalog year match boost
wrong semester penalty
wrong track penalty
wrong catalog year penalty
link relevance boost
source priority boost
```

Keep the boost values in a config file so they can be adjusted without rewriting code.

---

## 25. Recommended Profile Config File

Create a config file:

```text
app/retrieval/profile_config.json
```

Example structure:

```json
{
  "profiles": {
    "course_exact_lookup": {
      "exactLookupFirst": true,
      "sources": ["structured_catalog", "structured_offerings", "obsidian_wiki"],
      "vectorTopK": 5,
      "bm25TopK": 10,
      "hybridVectorWeight": 0.15,
      "rerankCandidateLimit": 20,
      "finalTopN": 3,
      "wikiChunksFinal": 2,
      "linkExpansionDepth": 0,
      "maxContextTokens": 2500,
      "maxRetrievalAttempts": 2,
      "latencyBudgetMs": 800
    },
    "requirement_explanation": {
      "exactLookupFirst": true,
      "sources": ["structured_requirements", "obsidian_wiki"],
      "vectorTopK": 35,
      "bm25TopK": 35,
      "hybridVectorWeight": 0.55,
      "rerankCandidateLimit": 70,
      "finalTopN": 8,
      "wikiChunksFinal": 8,
      "linkExpansionDepth": 1,
      "maxLinkedChunks": 5,
      "maxContextTokens": 8000,
      "maxRetrievalAttempts": 2,
      "latencyBudgetMs": 2000
    }
  }
}
```

The code should load profile values from this config.

Avoid hardcoding retrieval parameters throughout the codebase.

---

## 26. Context Validation After Retrieval

After retrieval, the Context Validator must check whether the context is sufficient.

Validation checks:

```text
required fields exist
correct source type
correct semester
correct catalog year
correct degree program
correct track
course number matches
retrieval confidence above threshold
no conflicting high-priority sources
structured data present when required
wiki context present when explanation is required
```

Validation statuses:

```text
valid
valid_with_warnings
needs_more_context
needs_user_clarification
failed
```

If validation fails:

```text
1. Try one targeted retrieval fallback if attempts remain.
2. Otherwise ask for clarification or return a missing-data response.
```

---

## 27. Source Priority Rules

When sources conflict, use this priority order:

```text
1. MongoDB user-specific data
2. Structured course offerings JSON / offering DB
3. Structured catalog / requirement DB
4. Obsidian catalog wiki
5. LLM general knowledge
```

The LLM should never override structured data.

If wiki text conflicts with structured offering data, the structured offering data wins for semester-specific information.

If user data conflicts with retrieved assumptions, MongoDB confirmed user records win.

---

## 28. Regression Tests

Every important retrieval failure should become a regression test.

Required tests:

```text
test_exact_course_number_retrieval
test_exact_offering_semester_lookup
test_wrong_semester_avoidance
test_requirement_bucket_retrieval
test_hebrew_requirement_query
test_mixed_language_query
test_transcript_course_number_matching
test_transcript_fuzzy_course_name_matching
test_metadata_relaxation_fallback
test_link_expansion_does_not_add_noise
test_reranker_preserves_exact_matches
test_context_validator_rejects_wrong_semester
test_context_validator_rejects_wrong_track
```

Example test behavior:

```text
Given query "Can I take 234218 next semester?"
When target semester is 2026_spring
Then top result must include offering:2026_spring:234218
And must not return a different semester as the primary result
```

---

## 29. Logging and Observability

For each retrieval run, log:

```text
conversationId
runId
intent
selected retrieval profile
query
resolved entities
metadata filters
retrieval attempts
retrieved source IDs
scores
reranked source IDs
final selected context
validation result
latency
context token count
fallbacks used
```

Do not log sensitive transcript contents unless necessary.

Use summaries and IDs where possible.

---

## 30. Final Report

After tuning, create:

```text
docs/agent/RAG_EVALUATION_RESULTS.md
```

This file should include:

```text
benchmark size
profiles evaluated
final chosen parameters
metric table per profile
main failure types
fixes applied
remaining known weaknesses
latency results
context token results
regression test summary
```

Example metric table:

| Profile                 | Hit@1 | Recall@5 |  MRR | Wrong Semester Rate | Avg Latency |
| ----------------------- | ----: | -------: | ---: | ------------------: | ----------: |
| course_exact_lookup     |  0.97 |     0.99 | 0.98 |                0.01 |       180ms |
| requirement_explanation |  0.76 |     0.88 | 0.81 |                0.03 |      1200ms |

---

## 31. Cursor Implementation Instructions

When implementing this phase, Cursor should:

```text
1. Inspect the existing retrieval/indexing code.
2. Identify current chunking, metadata, and retrieval behavior.
3. Add or update retrieval profile configuration.
4. Implement benchmark JSONL loading.
5. Implement retrieval evaluation metrics.
6. Implement evaluation runner.
7. Add example benchmark cases.
8. Run baseline evaluation.
9. Report current metrics.
10. Tune profile parameters one profile at a time.
11. Add regression tests for failures.
12. Save final profile configuration.
13. Write RAG_EVALUATION_RESULTS.md.
```

Cursor should not:

```text
1. Replace deterministic academic services with RAG.
2. Use one global RAG setting for all tasks.
3. Embed private user MongoDB data into the shared vector index.
4. Pass entire catalog or entire offerings files into the LLM.
5. Ignore metadata filters.
6. Ignore Hebrew/mixed-language retrieval.
7. Tune only by manual impression.
8. Tune without benchmark results.
9. Allow unlimited retrieval loops.
```

---

## 32. Final Locked Defaults for MVP

If evaluation has not yet been completed, use these defaults temporarily:

```text
Obsidian chunks:
semantic section chunks
300–800 target tokens
max 1200 tokens
50–100 overlap only when needed

Offerings chunks:
one course per semester
no overlap

Candidate retrieval:
vectorTopK 30
bm25TopK 30

Reranking:
rerank 30–70 candidates depending on profile

Final context:
3–8 chunks for most tasks
5–10 chunks for planning/explanation

Link expansion:
depth 1 only
max 3–5 linked chunks
off for exact course lookup

Retrieval attempts:
max 2

Hybrid weights:
course exact: vector 0.15 / keyword 0.85
offering exact: vector 0.10 / keyword 0.90
transcript matching: vector 0.25 / keyword 0.75
requirement explanation: vector 0.55 / keyword 0.45
general catalog: vector 0.70 / keyword 0.30
planning discovery: vector 0.45 / keyword 0.55
```

These are only starting defaults. The fine-tuning phase must replace them with benchmark-backed values.

---

## 33. Final Success Criteria

The RAG fine-tuning phase is complete when:

```text
1. Benchmark dataset exists.
2. Evaluation runner works.
3. Metrics are computed per profile.
4. Retrieval profiles are configured separately.
5. Exact course and offering lookups pass acceptance targets.
6. Requirement retrieval passes acceptance targets.
7. Hebrew and mixed-language queries are tested.
8. Wrong semester / wrong track / wrong catalog year cases are tested.
9. Context validation catches bad retrieval.
10. Regression tests exist for known failures.
11. Final profile config is committed.
12. RAG_EVALUATION_RESULTS.md documents the final choices.
```

The final result should be a retrieval layer that is measurable, reliable, and tuned for UniPilot’s real academic tasks.

The guiding rule remains:

```text
Tune retrieval by task profile and benchmark results.
Do not guess.
Do not use one global RAG configuration.
Do not let RAG replace deterministic academic validation.
```
