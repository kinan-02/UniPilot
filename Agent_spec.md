# UniPilot Agent / MAS Architecture Specification

## 1. Goal

UniPilot will include an intelligent academic planning agent that helps students understand their degree progress, completed courses, missing requirements, course eligibility, semester planning, prerequisites, and schedule options.

The user-facing experience should feel like one modern AI academic advisor:

**UniPilot Agent**

Internally, the system should use a controlled multi-agent / tool-based architecture with deterministic academic services, centralized retrieval, context validation, and structured responses.

The architecture must prioritize:

* academic correctness,
* reliable retrieval,
* explainability,
* modular implementation,
* safe user-data handling,
* deterministic validation,
* low LLM-call cost,
* clean UI integration,
* future extensibility.

The system must not rely on the LLM as the source of truth for academic rules. The LLM can reason, explain, summarize, and communicate with the user, but official academic calculations and validations must come from structured data and deterministic backend services.

---

## 2. Core Architectural Decision

UniPilot should use:

```text
Single visible agent
+
Controlled internal MAS / tool architecture
+
Centralized context builder
+
Hybrid retrieval layer
+
Deterministic academic services
+
User-confirmed write actions
```

The user should interact with one assistant called the **UniPilot Agent**.

The user should not be exposed to multiple internal agents such as “Catalog Agent”, “Planner Agent”, or “Transcript Agent”. Those may exist internally, but the UI and conversation should feel unified.

The architecture should not be a free autonomous swarm. Instead, it should be a **supervisor/orchestrator architecture**.

The orchestrator controls the workflow, calls specialized modules, retrieves context, validates data, and composes the final response.

---

## 3. Existing Data Sources

UniPilot currently has three major data sources.

### 3.1 Obsidian Catalog Wiki Vault

The Technion catalog has been parsed into a structured Obsidian wiki vault.

This vault contains catalog-level academic information such as:

* degree programs,
* tracks,
* credit buckets,
* requirement descriptions,
* focus chains,
* required courses,
* elective pools,
* academic rules,
* catalog explanations,
* links between related pages,
* structured page hierarchy,
* index pages,
* human-readable academic logic.

The Obsidian vault is already structured, indexed, and contains links between relevant pages.

This vault should be used as a **retrieval and explanation knowledge base**.

It is especially useful for:

* explaining degree requirements,
* retrieving relevant catalog sections,
* grounding answers in catalog text,
* helping users understand complex academic rules,
* finding relevant pages through semantic search,
* expanding context through links between pages.

The Obsidian vault should not be the only source used for exact academic calculations.

---

### 3.2 Course Offerings JSON Files

UniPilot has structured JSON files for course offerings for each semester.

These JSONs contain semester-specific course information that may not exist in the catalog wiki vault.

Examples:

* whether a course is offered in a specific semester,
* lecture groups,
* tutorial groups,
* lab groups,
* times,
* rooms,
* instructors if available,
* exam dates if available,
* prerequisites if included,
* linked lesson/group data,
* course-specific semester metadata.

The course offerings JSONs should be used as canonical structured data for semester-specific planning.

They should support exact structured lookup as well as optional semantic/hybrid retrieval.

The system must not rely only on embeddings for course offerings. Exact course-number and semester lookups are required.

---

### 3.3 User-Specific MongoDB Data

User-specific data is stored in the online MongoDB database.

This includes data such as:

* authenticated user identity,
* student profile,
* degree program,
* track,
* catalog year,
* completed courses,
* transcript imports,
* saved semester plans,
* selected courses,
* preferences,
* agent conversations,
* pending actions,
* confirmed actions.

MongoDB should be queried directly by backend services.

User-specific data should not be mixed into the public/shared catalog vector index.

---

## 4. Core Principle: Structured Truth First, RAG Second, LLM Last

The agent must follow this principle:

```text
Exact structured data first.
Hybrid retrieval second.
LLM explanation last.
```

This means:

1. Use exact structured lookup when the system knows the course number, semester, user ID, degree program, track, or catalog year.
2. Use RAG/hybrid retrieval to find relevant catalog text, explanations, and supporting context.
3. Use deterministic services to validate academic logic.
4. Use the LLM to explain results, summarize, ask clarifying questions, and compose user-facing responses.

The LLM must not invent:

* course offerings,
* prerequisites,
* credit totals,
* degree requirements,
* course mappings,
* completed courses,
* schedule conflicts,
* graduation status.

---

## 5. High-Level Architecture

```text
Frontend Agent UI
    ↓
Agent API / Streaming Endpoint
    ↓
Agent Orchestrator
    ↓
Intent Router
    ↓
Task Planner
    ↓
Entity Resolver
    ↓
Retrieval Planner
    ↓
Context Builder
    ├── MongoDB User Data Retriever
    ├── Structured Catalog Retriever
    ├── Structured Offerings Retriever
    ├── Obsidian Wiki Hybrid Retriever
    └── Optional Agentic RAG Retriever
    ↓
Context Validation Layer
    ↓
Shared AgentContextPack
    ↓
Specialized Workflows / Internal Agents
    ├── Graduation Audit Workflow
    ├── Course Question Workflow
    ├── Transcript Import Workflow
    ├── Semester Planning Workflow
    └── Requirement Explanation Workflow
    ↓
Deterministic Academic Services
    ↓
Response Composer
    ↓
Structured UI Response
```

---

## 6. Main Backend Layers

The backend should be separated into the following layers:

```text
agent/
  orchestration and conversation logic

retrieval/
  context retrieval from catalog wiki, offerings JSONs, and MongoDB

services/
  deterministic academic business logic

models/
  database models and schemas

api/
  HTTP and streaming endpoints

schemas/
  shared request/response schemas

validation/
  context validation, action validation, and output validation
```

Recommended project structure:

```text
app/
  agent/
    orchestrator.py
    intent_router.py
    task_planner.py
    entity_resolver.py
    retrieval_planner.py
    context_builder.py
    context_validator.py
    response_composer.py
    action_manager.py
    schemas.py

    workflows/
      graduation_progress_workflow.py
      course_question_workflow.py
      transcript_import_workflow.py
      semester_planning_workflow.py
      requirement_explanation_workflow.py
      general_academic_workflow.py

    agents/
      graduation_audit_agent.py
      course_advisor_agent.py
      transcript_import_agent.py
      semester_planning_agent.py
      requirement_explanation_agent.py
      validation_agent.py

  retrieval/
    obsidian_wiki_indexer.py
    obsidian_wiki_retriever.py
    offerings_indexer.py
    offerings_retriever.py
    hybrid_retriever.py
    metadata_filter.py
    reranker.py

  services/
    student_profile_service.py
    completed_courses_service.py
    catalog_service.py
    degree_requirements_service.py
    course_offering_service.py
    prerequisite_validation_service.py
    requirement_matching_service.py
    graduation_audit_service.py
    schedule_conflict_service.py
    semester_plan_service.py
    transcript_parser_service.py

  api/
    agent_routes.py
    conversation_routes.py
    action_routes.py

  models/
    agent_conversation.py
    agent_message.py
    agent_run.py
    agent_step.py
    agent_tool_call.py
    agent_action_proposal.py

  validation/
    context_requirements.py
    academic_result_validator.py
    action_validator.py
```

---

## 7. Agent Orchestrator

The Agent Orchestrator is the central controller.

It receives the user message, starts an agent run, determines the task, retrieves the correct context, validates the context, runs the correct workflow, and streams the final result to the frontend.

The orchestrator is responsible for:

1. Receiving the user message.
2. Creating an `AgentRun`.
3. Calling the Intent Router.
4. Calling the Task Planner.
5. Calling the Entity Resolver.
6. Calling the Retrieval Planner.
7. Calling the Context Builder.
8. Calling the Context Validator.
9. Running the selected workflow.
10. Calling deterministic academic services.
11. Calling the Response Composer.
12. Returning structured UI blocks.
13. Creating proposed actions when needed.
14. Requiring user confirmation before important writes.
15. Persisting messages, runs, steps, and tool calls.
16. Streaming progress events to the frontend.

The orchestrator must have hard limits:

```text
Max retrieval attempts per run: 2 or 3
Max tool calls per run: configurable
Max workflow steps per run: configurable
Max plan alternatives: 3 to 5
Max context size passed to LLM: configurable
```

The orchestrator should not allow infinite agent loops.

---

## 8. Intent Router

The Intent Router classifies the user’s request.

Possible intent categories:

```text
graduation_progress_check
transcript_import
semester_plan_generation
semester_plan_modification
course_question
requirement_explanation
prerequisite_check
catalog_search
completed_courses_update
profile_update
general_academic_question
unknown_or_unsupported
```

Example:

```text
User: "Can I take 234218 next semester?"
Intent: course_question
```

Example:

```text
User: "What am I missing to graduate?"
Intent: graduation_progress_check
```

Example:

```text
User: "Build me a plan with no Friday classes."
Intent: semester_plan_generation
```

The Intent Router should return a structured result:

```json
{
  "intent": "semester_plan_generation",
  "confidence": 0.93,
  "requiresFile": false,
  "requiresConfirmation": false,
  "requiredContext": [
    "student_profile",
    "completed_courses",
    "degree_requirements",
    "course_offerings",
    "user_preferences"
  ]
}
```

The MVP can implement the Intent Router using a deterministic rules-first approach with optional LLM fallback.

Recommended order:

```text
1. Rule-based detection for obvious cases.
2. Course-number/entity detection.
3. Lightweight LLM classification only when ambiguous.
```

---

## 9. Task Planner

The Task Planner converts the intent into a workflow plan.

It should answer:

* What workflow should run?
* What data sources are needed?
* What tools/services are needed?
* Is user confirmation required?
* Is a file required?
* Is the request answerable with current context?
* Is this a read-only task or a write/proposed-action task?

Example task plan:

```json
{
  "workflow": "course_question_workflow",
  "readOnly": true,
  "requiresConfirmation": false,
  "dataNeeds": {
    "mongo": [
      "student_profile",
      "completed_courses"
    ],
    "structuredOfferings": [
      "target_semester_course_offering"
    ],
    "catalog": [
      "course_record",
      "requirement_contribution"
    ],
    "wikiRag": [
      "relevant_requirement_explanation"
    ]
  },
  "services": [
    "CourseCatalogService",
    "CourseOfferingService",
    "PrerequisiteValidationService",
    "RequirementMatchingService"
  ]
}
```

The Task Planner should not retrieve data itself. It only decides what is needed.

---

## 10. Entity Resolver

The Entity Resolver extracts and normalizes academic entities from the user request and current conversation.

Entities include:

```text
course numbers
course names
semester names
degree program
track
catalog year
requirement bucket
credit limit
preferred days
avoided days
preferred time windows
planning objective
uploaded files
selected plan option
previously discussed course
```

Examples:

```text
"234218" → courseNumber = "234218"
"next semester" → targetSemester = resolved semester according to system configuration
"no Friday classes" → avoidDays = ["Friday"]
"not more than 20 credits" → maxCredits = 20
"make it lighter" → planningObjective = "lighter_workload"
```

The Entity Resolver should normalize Hebrew and English names where relevant.

It should support course lookup by:

* exact course number,
* Hebrew course name,
* English course name,
* fuzzy name match,
* previous conversation reference.

If multiple possible matches exist, the system should either ask for clarification or show the likely options.

---

## 11. Retrieval Planner

The Retrieval Planner decides which data sources to query.

It receives:

* intent,
* task plan,
* resolved entities,
* existing conversation context.

It outputs a retrieval plan.

Example:

```json
{
  "retrievalPlan": [
    {
      "source": "mongodb",
      "queries": [
        "student_profile",
        "completed_courses"
      ]
    },
    {
      "source": "structured_offerings",
      "queries": [
        {
          "semester": "2026_spring",
          "courseNumber": "234218"
        }
      ]
    },
    {
      "source": "obsidian_wiki",
      "mode": "hybrid",
      "filters": {
        "degreeProgram": "הנדסת מערכות מידע",
        "catalogYear": "תשפ״ו"
      },
      "query": "234218 requirement contribution prerequisites"
    }
  ]
}
```

The Retrieval Planner should prefer exact structured retrieval over semantic retrieval when possible.

---

## 12. Context Builder

The Context Builder is one of the most important components in the system.

Its job is to produce a small, precise, validated, task-specific context package.

The LLM should not receive the entire catalog, entire Obsidian vault, entire offerings JSON, or full MongoDB user document unless required.

The Context Builder should collect only the data needed for the current task.

It should retrieve from:

```text
MongoDB user data
structured catalog data
structured course offerings data
Obsidian wiki hybrid RAG
optional semantic search over offerings
conversation assumptions
pending action state
```

The output is an `AgentContextPack`.

All internal agents and workflows should use this same shared context pack.

---

## 13. AgentContextPack Schema

The system should pass a structured context pack between components.

Example:

```json
{
  "conversationId": "...",
  "runId": "...",
  "userId": "...",
  "intent": "course_question",
  "entities": {
    "courseNumber": "234218",
    "targetSemester": "2026_spring"
  },
  "userContext": {
    "profile": {
      "degreeProgram": "הנדסת מערכות מידע",
      "track": "...",
      "catalogYear": "תשפ״ו"
    },
    "completedCourses": []
  },
  "academicContext": {
    "course": {},
    "offering": {},
    "degreeRequirements": [],
    "prerequisiteResult": {},
    "requirementContribution": {}
  },
  "retrievedWikiContext": [
    {
      "sourceType": "catalog_wiki",
      "sourceFile": "...",
      "pageTitle": "...",
      "sectionTitle": "...",
      "content": "...",
      "score": 0.84
    }
  ],
  "assumptions": [],
  "missingData": [],
  "warnings": [],
  "provenance": [],
  "validation": {
    "status": "valid",
    "errors": [],
    "warnings": []
  }
}
```

The context pack should include:

* resolved intent,
* resolved entities,
* user context,
* academic context,
* retrieved knowledge snippets,
* deterministic service outputs,
* assumptions,
* missing data,
* warnings,
* provenance,
* validation status.

---

## 14. Source Priority

When sources conflict, use this priority order:

```text
1. MongoDB user-specific data
   For the user’s actual profile, completed courses, saved plans, preferences, and confirmed records.

2. Structured course offerings JSON data
   For semester-specific offerings, groups, prerequisites, schedule times, and exams.

3. Structured catalog / requirements data
   For degree requirements, credit buckets, course mappings, exclusions, and academic rules.

4. Obsidian catalog wiki
   For explanation, source grounding, linked context, human-readable academic text, and fallback retrieval.

5. LLM general knowledge
   Should not be used for official academic facts.
```

The LLM must not override structured data.

---

## 15. Obsidian Wiki Retrieval

The Obsidian vault should be indexed into a vector database and searchable using hybrid retrieval.

Retrieval should combine:

```text
metadata filtering
semantic vector search
BM25 / keyword search
exact phrase search
course-number search
link graph expansion
reranking
```

The retriever should not treat the vault as random markdown files. It should preserve structure.

### 15.1 Obsidian Chunking Strategy

Chunk by semantic sections, not only by fixed token count.

Recommended chunking:

```text
one chunk per meaningful section
include heading path
include page title
include parent page
include nearby headings when needed
include outgoing links
include incoming links if available
include course numbers mentioned
include requirement bucket metadata
```

Each chunk should be understandable in isolation.

Every chunk should include the heading path.

Example:

```json
{
  "sourceType": "catalog_wiki",
  "sourceFile": "09-מדעי-הנתונים-וההחלטות-תשפו/הנדסת-מערכות-מידע.md",
  "pageTitle": "הנדסת מערכות מידע",
  "sectionTitle": "קורסי בחירה",
  "headingPath": [
    "הנדסת מערכות מידע",
    "דרישות השלמה לתואר",
    "קורסי בחירה"
  ],
  "catalogYear": "תשפ״ו",
  "faculty": "מדעי הנתונים וההחלטות",
  "degreeProgram": "הנדסת מערכות מידע",
  "track": "הנדסת מערכות מידע",
  "requirementBucket": "קורסי בחירה",
  "ruleType": "degree_requirement",
  "courseNumbersMentioned": [],
  "outgoingLinks": [],
  "incomingLinks": [],
  "language": "he",
  "content": "..."
}
```

### 15.2 Obsidian Metadata

Store metadata for every chunk:

```text
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

### 15.3 Link Graph Expansion

Because the Obsidian vault contains links, retrieval should optionally expand to linked pages.

Example:

1. Retrieve the most relevant requirement section.
2. Look at outgoing links.
3. Fetch linked course pages or related rule pages.
4. Add only the most relevant linked chunks to the context.

Use link expansion carefully to avoid context bloat.

Recommended limits:

```text
Top initial chunks: 5 to 10
Linked expansion depth: 1
Max linked chunks added: 3 to 5
Final chunks after reranking: 3 to 8
```

---

## 16. Course Offerings JSON Retrieval

Course offerings JSONs should be stored in two forms:

```text
1. Structured queryable storage
2. Vector/hybrid searchable index
```

The structured form is required for exact academic operations.

The vector/hybrid index is useful for semantic questions and exploratory search.

### 16.1 Structured Lookup

Use structured lookup for:

```text
course number
semester
lecture groups
tutorial groups
lab groups
times
rooms
instructors
exam dates
prerequisites
offering availability
schedule conflict validation
```

Example exact lookup:

```text
semester = 2026_spring
courseNumber = 234218
```

This should return the course offering record directly.

### 16.2 Offerings Chunking Strategy

For the vector/hybrid index, chunk offerings as:

```text
one chunk per course per semester
```

Example metadata:

```json
{
  "sourceType": "course_offering",
  "semester": "2026_spring",
  "courseNumber": "234218",
  "courseName": "...",
  "credits": 3.0,
  "hasLecture": true,
  "hasTutorial": true,
  "hasLab": false,
  "prerequisites": [],
  "lectureGroups": [],
  "tutorialGroups": [],
  "labGroups": [],
  "examDates": [],
  "language": "he",
  "rawTextForEmbedding": "..."
}
```

The `rawTextForEmbedding` should contain a searchable text representation of the offering.

However, all planning and validation should use the structured fields, not the embedded text.

---

## 17. MongoDB User Data Retrieval

User-specific data should be retrieved directly from MongoDB using authenticated `userId`.

The system should never retrieve another user’s data.

MongoDB data needed by the agent may include:

```text
student profile
degree program
track
catalog year
completed courses
current semester plans
saved preferences
transcript import history
agent conversations
pending actions
confirmed actions
```

### 17.1 Data Retrieval by Workflow

Graduation progress requires:

```text
student profile
completed courses
degree program
track
catalog year
possibly in-progress courses
```

Course question requires:

```text
student profile
completed courses
possibly current plan
```

Semester planning requires:

```text
student profile
completed courses
missing requirements
saved preferences
current plans
target semester
```

Transcript import requires:

```text
existing completed courses
previous transcript imports
catalog matching data
```

Profile update requires:

```text
current profile
proposed changes
confirmation state
```

---

## 18. Context Validation Layer

The Context Validation Layer verifies that the retrieved context is correct and sufficient for the task.

This should be mostly deterministic.

Each workflow should define a required context schema.

Example for `course_question`:

```json
{
  "required": [
    "userContext.profile.degreeProgram",
    "userContext.profile.catalogYear",
    "entities.courseNumber",
    "academicContext.course",
    "userContext.completedCourses",
    "entities.targetSemester",
    "academicContext.offering",
    "academicContext.prerequisiteResult"
  ],
  "optional": [
    "academicContext.requirementContribution",
    "academicContext.scheduleConflictStatus",
    "retrievedWikiContext"
  ]
}
```

The validator should check:

```text
missing required fields
stale data
wrong catalog year
wrong semester
course not found
ambiguous course match
empty RAG results
low retrieval confidence
conflicting sources
missing user profile
missing completed courses
missing offering data
missing prerequisite data
```

Validation statuses:

```text
valid
valid_with_warnings
needs_more_context
needs_user_clarification
failed
```

If context is incomplete, the system can:

```text
1. Retrieve again with a more targeted query.
2. Ask the user a clarification question.
3. Continue with an explicit assumption or warning.
4. Stop and explain what data is missing.
```

Retrieval loops must be limited.

Recommended:

```text
Max context retrieval attempts: 2 or 3
```

---

## 19. Provenance and Confidence

Every important context item should include provenance.

Provenance should track:

```text
source type
source ID
retrieval method
confidence
timestamp or version
exact field used
```

Example:

```json
{
  "claim": "Course 234218 is offered in Spring 2026",
  "sourceType": "course_offering_json",
  "sourceId": "2026_spring:234218",
  "retrievalMethod": "exact_lookup",
  "confidence": "high"
}
```

Example:

```json
{
  "claim": "This requirement belongs to the Information Systems Engineering track",
  "sourceType": "catalog_wiki",
  "sourceFile": "09-מדעי-הנתונים-וההחלטות-תשפו/הנדסת-מערכות-מידע.md",
  "retrievalMethod": "metadata_filtered_hybrid_search",
  "confidence": 0.87
}
```

The final response should be able to show user-facing source summaries like:

```text
Based on:
- Your completed courses
- Information Systems Engineering requirements
- Spring 2026 course offerings
- Technion catalog wiki
```

---

## 20. Hybrid Retrieval Strategy

The retrieval layer should support multiple retrieval modes.

### 20.1 Exact Lookup

Use exact lookup when the system has:

```text
course number
semester
degree program
track
catalog year
requirement bucket ID
user ID
plan ID
```

Exact lookup should be preferred for academic facts.

### 20.2 Metadata-Filtered Search

Use metadata filters before vector search whenever possible.

Example filters:

```json
{
  "catalogYear": "תשפ״ו",
  "degreeProgram": "הנדסת מערכות מידע",
  "track": "הנדסת מערכות מידע",
  "ruleType": "degree_requirement"
}
```

### 20.3 Semantic Vector Search

Use vector search for natural language queries such as:

```text
Explain the project requirement.
Which electives are related to AI?
What are the rules for this track?
What does this requirement bucket mean?
```

### 20.4 BM25 / Keyword Search

Use keyword search for:

```text
course numbers
exact Hebrew phrases
exact requirement names
specific page titles
catalog terminology
```

Course numbers often perform better with keyword search than vector search.

### 20.5 Reranking

After initial retrieval, rerank results based on:

```text
semantic similarity
metadata match
exact entity match
source priority
link relevance
recency/version
workflow relevance
```

The final context should include only the most relevant chunks.

---

## 21. Optional Agentic RAG

Agentic RAG can be used for difficult or exploratory queries.

Examples:

```text
Find electives that could help me with AI and also satisfy my track.
Explain how this focus chain works and which courses I can take.
Compare these two degree paths.
```

However, Agentic RAG should be controlled.

It should not freely search everything indefinitely.

Recommended behavior:

```text
1. Generate a retrieval sub-plan.
2. Execute exact and hybrid searches.
3. Validate results.
4. Run one additional retrieval pass only if needed.
5. Return final retrieved context.
```

Agentic RAG should have strict limits:

```text
Max retrieval passes: 2
Max chunks per pass: configurable
Max final chunks: configurable
Max total context tokens: configurable
```

Do not use Agentic RAG when exact structured lookup is enough.

---

## 22. Shared Context Across Agents

All specialized agents and workflows should use the same `AgentContextPack`.

Avoid this pattern:

```text
Graduation Agent searches wiki independently.
Course Agent searches wiki independently.
Planner Agent searches wiki independently.
Explanation Agent searches wiki independently.
```

Use this pattern:

```text
Context Builder retrieves and validates context once.
Specialized workflows consume the same context.
Extra retrieval occurs only when explicitly needed.
```

This improves:

* consistency,
* cost,
* speed,
* debuggability,
* testability,
* answer quality.

---

## 23. Deterministic Academic Services

Academic logic should be implemented in deterministic backend services.

Required services:

```text
StudentProfileService
CompletedCoursesService
CatalogService
DegreeRequirementsService
CourseOfferingService
RequirementMatchingService
GraduationAuditService
PrerequisiteValidationService
ScheduleConflictService
SemesterPlanService
TranscriptParserService
```

### 23.1 What the LLM Must Not Calculate Alone

The LLM must not independently calculate:

```text
graduation status
completed credits
missing credits
bucket completion
mandatory course completion
prerequisite satisfaction
course offering availability
schedule conflicts
exam conflicts
valid lesson group combinations
whether a course counts for a requirement
whether a plan can be saved
```

These must come from deterministic services.

### 23.2 Service Responsibility Table

| Task                         | Source of Truth                           |
| ---------------------------- | ----------------------------------------- |
| User profile                 | MongoDB + StudentProfileService           |
| Completed courses            | MongoDB + CompletedCoursesService         |
| Degree requirements          | Structured catalog / requirements service |
| Requirement matching         | RequirementMatchingService                |
| Graduation progress          | GraduationAuditService                    |
| Prerequisite validation      | PrerequisiteValidationService             |
| Course offering availability | CourseOfferingService                     |
| Schedule conflicts           | ScheduleConflictService                   |
| Semester plan saving         | SemesterPlanService                       |
| Transcript parsing           | TranscriptParserService                   |
| Human-readable explanation   | LLM + retrieved context                   |

---

## 24. Internal Agents / Specialized Workflows

The system may use specialized internal agents or workflows.

These should be bounded and tool-driven.

They should not directly mutate production data unless explicitly called by the orchestrator after user confirmation.

### 24.1 Conversation Agent

Role:

* handles user-facing conversation,
* interprets follow-up questions,
* keeps responses friendly and clear,
* asks clarifying questions when needed.

It should not perform academic calculations itself.

### 24.2 Graduation Audit Agent

Role:

* analyze graduation progress,
* explain completed and missing requirements,
* identify blockers,
* recommend next academic actions.

Inputs:

```text
student profile
completed courses
degree requirements
requirement matching result
graduation audit result
relevant wiki snippets
```

Output:

```json
{
  "totalRequiredCredits": 160,
  "completedCredits": 112,
  "missingCredits": 48,
  "completionPercentage": 70,
  "graduationStatus": "not_ready",
  "requirementBuckets": [],
  "blockers": [],
  "warnings": [],
  "assumptions": []
}
```

### 24.3 Course Advisor Agent

Role:

* answer questions about specific courses,
* check if a student can take a course,
* explain prerequisites,
* explain requirement contribution,
* check offering status,
* check whether the course helps graduation progress.

Output:

```json
{
  "course": {},
  "canTake": true,
  "prerequisiteStatus": {},
  "offeringStatus": {},
  "requirementContribution": {},
  "recommendation": "...",
  "warnings": []
}
```

### 24.4 Transcript Import Agent

Role:

* process transcript uploads,
* parse course rows,
* normalize courses,
* detect duplicates,
* match against catalog,
* show review table,
* create import action proposal.

The transcript import agent must never silently save parsed courses.

### 24.5 Semester Planning Agent

Role:

* generate semester plan options,
* respect missing requirements,
* respect prerequisites,
* use actual course offerings,
* use actual lecture/tutorial/lab groups,
* validate conflicts,
* respect preferences,
* produce multiple plan alternatives.

The planner must support a CheeseFork-like lesson/group model, where students can choose specific lesson groups directly in the weekly schedule.

Output:

```json
{
  "options": [
    {
      "label": "Balanced Plan",
      "totalCredits": 18,
      "courses": [],
      "selectedOfferings": [],
      "weeklySchedule": {},
      "requirementCoverage": [],
      "conflicts": [],
      "workloadEstimate": "medium",
      "pros": [],
      "cons": [],
      "warnings": []
    }
  ]
}
```

### 24.6 Requirement Explanation Agent

Role:

* explain requirement rules in simple language,
* explain why a bucket is complete or incomplete,
* explain why a course counts or does not count,
* explain eligible course pools,
* explain focus chains.

It should rely on deterministic audit results and retrieved catalog context.

### 24.7 Validation Agent

Role:

* check final answer consistency,
* ensure no unsupported academic claims,
* ensure missing data and assumptions are disclosed,
* ensure write actions require confirmation.

The MVP can implement this mostly with deterministic checks. A separate LLM validation call can be added later.

### 24.8 Response Composer Agent

Role:

* convert structured results into polished user-facing responses,
* generate concise explanations,
* attach structured UI blocks,
* generate suggested follow-up prompts.

The response composer should produce structured response objects, not only plain text.

---

## 25. Agent API

The backend should expose dedicated agent endpoints.

Suggested endpoints:

```text
POST /agent/conversations
GET  /agent/conversations
GET  /agent/conversations/{conversationId}
POST /agent/conversations/{conversationId}/messages
POST /agent/conversations/{conversationId}/cancel
POST /agent/actions/{actionId}/confirm
POST /agent/actions/{actionId}/reject
```

The message endpoint should support streaming.

Recommended streaming options:

```text
Server-Sent Events for MVP
WebSocket later if bidirectional live interaction is needed
```

---

## 26. Streaming Events

The agent should stream progress events to the frontend.

Event types:

```text
message.delta
message.completed
agent.step.started
agent.step.completed
agent.step.failed
tool.started
tool.completed
structured_output
action.proposed
run.completed
run.failed
```

Example stream:

```json
{
  "type": "agent.step.started",
  "label": "Reading your completed courses"
}
```

```json
{
  "type": "agent.step.completed",
  "label": "Reading your completed courses"
}
```

```json
{
  "type": "structured_output",
  "block": {
    "type": "RequirementSummaryBlock",
    "data": {}
  }
}
```

---

## 27. Persistence Models

The agent should persist conversations, messages, runs, steps, tool calls, and action proposals.

Recommended collections:

```text
agent_conversations
agent_messages
agent_runs
agent_steps
agent_tool_calls
agent_action_proposals
agent_artifacts
agent_assumptions
```

### 27.1 agent_conversations

Fields:

```text
id
userId
title
createdAt
updatedAt
lastMessagePreview
status
```

### 27.2 agent_messages

Fields:

```text
id
conversationId
userId
role
content
structuredBlocks
attachments
createdAt
```

Roles:

```text
user
assistant
system
tool
```

The frontend should normally display only `user` and `assistant`.

### 27.3 agent_runs

Fields:

```text
id
conversationId
userId
triggerMessageId
intent
status
startedAt
completedAt
error
```

Status values:

```text
queued
running
completed
failed
cancelled
requires_user_confirmation
```

### 27.4 agent_steps

Fields:

```text
id
runId
label
status
startedAt
completedAt
summary
```

Example labels:

```text
Reading student profile
Checking completed courses
Retrieving catalog rules
Searching course offerings
Matching requirements
Validating prerequisites
Building plan options
Preparing final answer
```

### 27.5 agent_tool_calls

Fields:

```text
id
runId
toolName
inputSummary
outputSummary
status
startedAt
completedAt
error
```

Do not expose raw sensitive tool data to the frontend by default.

### 27.6 agent_action_proposals

Fields:

```text
id
conversationId
userId
type
status
payload
preview
createdAt
confirmedAt
rejectedAt
executedAt
error
```

Status values:

```text
pending
confirmed
rejected
expired
executed
failed
```

---

## 28. Confirmation Model

The agent must distinguish between advice and actions.

The agent may recommend actions, but it must not silently make important changes.

User confirmation is required for:

```text
importing transcript courses
saving a semester plan
updating completed courses
deleting completed courses
changing degree program
changing track
changing catalog year
applying generated mappings
updating persistent preferences
```

Action proposal example:

```json
{
  "id": "...",
  "type": "save_semester_plan",
  "title": "Save recommended semester plan",
  "description": "This will save Option A as your active plan for Spring 2026.",
  "preview": {},
  "payload": {},
  "status": "pending",
  "requiresConfirmation": true
}
```

Only after the user confirms should the action execute.

---

## 29. Agent Response Schema

The agent should return structured responses.

Example:

```json
{
  "conversationId": "...",
  "messageId": "...",
  "runId": "...",
  "text": "...",
  "blocks": [],
  "warnings": [],
  "suggestedPrompts": [],
  "proposedActions": [],
  "assumptions": [],
  "usedSources": []
}
```

Supported block types:

```text
RequirementSummaryBlock
RequirementBucketBlock
CourseRecommendationBlock
TranscriptReviewBlock
SemesterPlanOptionsBlock
SchedulePreviewBlock
WarningBlock
ConfirmationBlock
SourceSummaryBlock
```

The frontend should render these blocks into rich UI components.

---

## 30. Main Workflows

## 30.1 Graduation Progress Check

Trigger examples:

```text
Check my graduation progress.
What am I missing to graduate?
How many credits do I still need?
Can I graduate?
```

Flow:

```text
1. Classify intent as graduation_progress_check.
2. Resolve degree program, track, and catalog year.
3. Retrieve user profile from MongoDB.
4. Retrieve completed courses from MongoDB.
5. Retrieve structured degree requirements.
6. Retrieve relevant Obsidian wiki requirement sections.
7. Run RequirementMatchingService.
8. Run GraduationAuditService.
9. Validate context and audit result.
10. Compose structured response.
```

Response should include:

```text
graduation summary card
requirement bucket cards
completed credits
missing credits
blockers
warnings
assumptions
used sources
suggested follow-up prompts
```

The LLM should explain the audit result, not calculate it.

---

## 30.2 Course Question

Trigger examples:

```text
Can I take 234218?
Does this course count for my track?
Is this course offered next semester?
What prerequisites am I missing?
```

Flow:

```text
1. Classify intent as course_question.
2. Resolve course number or course name.
3. Resolve target semester.
4. Retrieve user profile.
5. Retrieve completed courses.
6. Retrieve exact course catalog record.
7. Retrieve exact course offering record for target semester.
8. Validate prerequisites.
9. Check requirement contribution.
10. Optionally retrieve relevant wiki snippets.
11. Compose answer.
```

Response should include:

```text
clear yes/no/maybe answer
course card
prerequisite status
offering status
requirement contribution
warnings
recommendation
used sources
```

---

## 30.3 Transcript Import

Trigger examples:

```text
Import my transcript.
Parse this gradesheet.
Add these completed courses.
```

Flow:

```text
1. Classify intent as transcript_import.
2. Verify uploaded file exists.
3. Parse PDF or extracted text.
4. Extract course rows.
5. Normalize course numbers, names, credits, grades, and semesters.
6. Match courses against catalog.
7. Detect duplicates against MongoDB completed courses.
8. Mark uncertain rows.
9. Create transcript review result.
10. Create pending ImportCompletedCoursesAction.
11. Show review table and confirmation panel.
12. Save only after user confirmation.
13. Recalculate graduation progress after confirmed import.
```

The import flow must never silently save parsed transcript data.

Response should include:

```text
transcript review table
uncertain rows
duplicates
unmatched courses
total extracted credits
confirmation panel
warnings
```

---

## 30.4 Semester Plan Generation

Trigger examples:

```text
Build me a semester plan.
Make me a plan for next semester.
Create a plan with no Friday classes.
Build the fastest graduation plan.
Make the workload lighter.
```

Flow:

```text
1. Classify intent as semester_plan_generation.
2. Extract planning constraints and preferences.
3. Resolve target semester.
4. Retrieve user profile.
5. Retrieve completed courses.
6. Run graduation audit to identify missing requirements.
7. Retrieve eligible courses.
8. Retrieve target semester offerings.
9. Filter by prerequisites.
10. Rank courses by graduation value.
11. Generate candidate course sets.
12. Select valid lecture/tutorial/lab groups.
13. Validate schedule conflicts.
14. Validate credit load.
15. Generate 2 to 5 plan options.
16. Compose explanation and tradeoffs.
17. Create save-plan action only when user selects a plan.
```

Planner should account for:

```text
missing requirements
mandatory courses
electives
track requirements
prerequisites
course offerings
lecture groups
tutorial groups
lab groups
schedule conflicts
exam conflicts if available
credit load
user preferences
existing selected courses
active/inactive selected-course toggles
```

Response should include:

```text
plan option cards
total credits
courses
weekly schedule preview
requirement coverage
conflicts
warnings
pros and cons
suggested modifications
```

---

## 30.5 Semester Plan Modification

Trigger examples:

```text
Remove Friday classes.
Make this plan lighter.
Replace this course.
Add databases if possible.
Avoid morning lectures.
```

Flow:

```text
1. Load current plan context.
2. Extract requested modification.
3. Preserve existing choices where possible.
4. Re-run relevant planning constraints.
5. Generate updated plan option.
6. Validate conflicts and requirements.
7. Show updated plan.
8. Ask for confirmation before saving.
```

The agent should not discard the user’s existing selected courses unless required by the requested modification.

---

## 30.6 Requirement Explanation

Trigger examples:

```text
Why is this requirement incomplete?
Why did this course not count?
Explain my missing electives.
What does this bucket mean?
```

Flow:

```text
1. Identify the relevant requirement bucket.
2. Retrieve structured requirement data.
3. Retrieve related Obsidian wiki section.
4. Load audit result if relevant.
5. Explain rule in simple language.
6. Explain student’s current status.
7. Show completed courses used.
8. Show missing courses or credits.
9. Show eligible options if relevant.
```

Response should include:

```text
simple explanation
current status
completed courses used
missing credits/courses
eligible options
warnings
source summary
```

---

## 31. LLM Call Strategy

The architecture should minimize unnecessary LLM calls.

Do not implement each internal agent as a separate LLM call by default.

Recommended model:

```text
Most requests: 1 LLM call
Complex planning: 2 LLM calls
Transcript import: 1 to 3 depending on parser
Optional validation: +1 later
```

### 31.1 Simple Requests

For graduation progress, course questions, and requirement explanations:

```text
Backend:
- intent routing
- retrieval
- context building
- deterministic services
- validation

LLM:
- final explanation and response composition
```

Target:

```text
1 LLM call
```

### 31.2 Complex Planning

For semester planning:

```text
LLM Call 1:
Extract preferences and constraints if needed.

Backend:
Retrieve data, generate plans, validate schedules.

LLM Call 2:
Explain plan options and tradeoffs.
```

Target:

```text
2 LLM calls
```

### 31.3 Avoid Bad MAS Pattern

Avoid:

```text
Orchestrator LLM call
Graduation Agent LLM call
Catalog Agent LLM call
Prerequisite Agent LLM call
Planner Agent LLM call
Validation Agent LLM call
Response Agent LLM call
```

This creates too much cost, latency, and complexity.

The better pattern:

```text
LLM only where language understanding, reasoning, or explanation is needed.
Deterministic code everywhere else.
```

---

## 32. Conversation Memory and Assumptions

The agent should maintain conversation-level assumptions.

Examples:

```text
User prefers no Friday classes.
User prefers maximum 20 credits.
User wants to graduate as fast as possible.
User prefers lighter workload.
User is planning Spring 2026.
```

Important distinction:

```text
Conversation assumptions are temporary.
Profile preferences are persistent.
Academic records are official user data.
```

The agent should not permanently save preferences unless the user confirms that they want to save them.

The UI should show active assumptions in the context panel and allow the user to edit or remove them.

---

## 33. Security and Privacy

The agent must enforce strict user isolation.

Rules:

```text
Always scope MongoDB queries by authenticated userId.
Never expose one user’s data to another user.
Never trust user-provided userId values.
Never allow the LLM to directly write to the database.
Never expose raw stack traces to users.
Never log full sensitive transcript contents unnecessarily.
Never expose hidden system prompts or internal credentials.
```

Write actions must go through backend authorization and validation.

---

## 34. Error Handling

The agent should fail gracefully.

Possible error codes:

```text
student_profile_missing
degree_program_missing
track_missing
catalog_year_missing
completed_courses_missing
course_not_found
ambiguous_course_match
offering_data_missing
prerequisite_data_missing
degree_requirements_missing
transcript_parse_failed
planner_no_valid_plan
schedule_conflict_unresolved
context_validation_failed
retrieval_failed
action_confirmation_required
```

User-facing examples:

```text
I could not complete the graduation analysis because your degree track is missing. Please select your track first.
```

```text
I found the course, but I do not have offering data for the selected semester yet.
```

```text
I could not build a valid schedule with all requested courses because two required classes overlap.
```

Every error should include a useful next step when possible.

---

## 35. Observability and Debugging

The system should store enough information to debug agent behavior.

Track:

```text
intent classification result
retrieval plan
retrieved sources
context validation result
deterministic service outputs
LLM prompt version
LLM response metadata
tool call summaries
action proposal lifecycle
```

Do not store sensitive raw data unless necessary.

Use summaries where possible.

---

## 36. Testing Requirements

The agent architecture should be testable at each layer.

### 36.1 Unit Tests

Test:

```text
IntentRouter
EntityResolver
RetrievalPlanner
ContextBuilder
ContextValidator
RequirementMatchingService
GraduationAuditService
PrerequisiteValidationService
ScheduleConflictService
SemesterPlanService
ActionManager
```

### 36.2 Retrieval Tests

Test:

```text
course number exact lookup
Hebrew course name lookup
degree-program metadata filtering
track filtering
catalog year filtering
wiki link expansion
offerings JSON lookup
semantic search quality
BM25 fallback
reranking
```

### 36.3 Workflow Tests

Test complete workflows:

```text
graduation progress check
course question
transcript import review
semester plan generation
semester plan modification
requirement explanation
```

### 36.4 Safety Tests

Test:

```text
no cross-user data access
no write without confirmation
no silent transcript import
no invented course offering
no invented prerequisite
no save-plan action without validation
```

---

## 37. MVP Implementation Scope

The first version should not try to build everything at once.

MVP should include:

```text
1. Agent conversation API
2. Conversation persistence
3. Message streaming
4. Basic intent router
5. Entity resolver
6. Retrieval planner
7. Centralized context builder
8. MongoDB user-data retrieval
9. Structured offering lookup
10. Obsidian wiki hybrid retrieval
11. Context validation layer
12. Graduation progress workflow
13. Course question workflow
14. Structured response blocks
15. Action proposal model
16. Confirmation system
17. Basic frontend integration
```

Do not start with a fully autonomous semester planner.

---

## 38. Recommended Implementation Phases

### Phase 1 — Agent Infrastructure

Implement:

```text
agent conversations
agent messages
agent runs
streaming endpoint
basic orchestrator
step events
response schema
frontend connection
```

### Phase 2 — Retrieval and Context Layer

Implement:

```text
EntityResolver
RetrievalPlanner
ContextBuilder
ContextValidator
MongoDB user retriever
structured offerings retriever
Obsidian wiki retriever
AgentContextPack schema
provenance tracking
```

### Phase 3 — Graduation Progress Workflow

Implement:

```text
graduation audit workflow
requirement matching integration
requirement summary blocks
requirement bucket blocks
warnings
source summary
```

### Phase 4 — Course Question Workflow

Implement:

```text
course lookup
offering lookup
prerequisite validation
requirement contribution check
course recommendation cards
```

### Phase 5 — Transcript Import Workflow

Implement:

```text
file upload support
transcript parser
course row extraction
catalog matching
duplicate detection
review table
import confirmation action
```

### Phase 6 — Semester Planning Workflow

Implement:

```text
missing requirement extraction
eligible course filtering
offering-based planning
lesson/tutorial/lab group selection
schedule conflict validation
plan option cards
weekly schedule preview
save-plan action
```

### Phase 7 — Advanced Agentic RAG and Optimization

Implement:

```text
query decomposition
multi-step retrieval
link graph expansion tuning
reranking
planning optimization
advanced explanation
LLM validation call if needed
```

---

## 39. Final Design Rules

The implementation must follow these rules:

```text
1. One visible user-facing UniPilot Agent.
2. Internal agents are controlled workflows, not an uncontrolled swarm.
3. Centralized Context Builder prepares shared context.
4. All agents consume the same AgentContextPack.
5. Retrieve exact structured data before semantic search.
6. Use Obsidian wiki RAG for explanation and catalog grounding.
7. Use offerings JSONs as structured queryable semester data.
8. Use MongoDB direct queries for user-specific data.
9. Validate context before answering.
10. Limit retrieval loops.
11. Track provenance for important claims.
12. Use deterministic services for academic truth.
13. LLM explains and composes; backend verifies and decides.
14. No important write action happens without user confirmation.
15. Keep LLM calls low: usually 1, sometimes 2 for complex planning.
```

---

## 40. Final Architectural Summary

UniPilot’s agent architecture should be:

```text
User-facing conversation agent
+
Supervisor orchestrator
+
Intent router
+
Task planner
+
Entity resolver
+
Centralized retrieval planner
+
Context builder
+
Hybrid RAG over Obsidian catalog wiki
+
Structured lookup over course offerings JSONs
+
MongoDB retrieval for user-specific data
+
Context validation layer
+
Shared AgentContextPack
+
Deterministic academic services
+
Structured response composer
+
User-confirmed action system
```

The most important principle is:

```text
The LLM explains and orchestrates.
The backend retrieves, validates, calculates, and decides.
```

This architecture gives UniPilot the feeling of a modern intelligent academic agent while keeping academic decisions reliable, grounded, auditable, and safe.
