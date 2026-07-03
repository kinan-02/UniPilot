# UniPilot Agent UI / UX Specification

## 1. Purpose

This document defines the user interface and user experience for the UniPilot Agent.

The UniPilot Agent is the main conversational academic assistant inside UniPilot. It helps students understand their degree progress, missing requirements, completed courses, prerequisites, course offerings, semester planning, schedule conflicts, and academic decisions.

The interface should feel like a modern AI agent product, similar in interaction quality to popular AI assistant apps, while being specifically designed for academic planning.

The user should feel that they are working with one intelligent academic advisor, even though the backend may use multiple internal workflows, tools, and agents.

The interface must be:

* clean,
* modern,
* fast,
* structured,
* trustworthy,
* academic,
* easy to understand,
* easy to act on,
* responsive,
* accessible,
* suitable for complex academic planning.

The UI must not feel like a basic chatbot. It should combine conversational interaction with rich academic planning components.

---

## 2. Product Experience Goal

The UniPilot Agent should help the student answer questions like:

```text
What am I missing to graduate?
Can I take this course next semester?
Does this course count for my track?
Build me a semester plan.
Avoid Friday classes.
Import my transcript.
Explain why this requirement is incomplete.
Which electives should I take?
```

The interface should make complex academic information feel manageable.

The user should be able to:

1. Ask a natural language question.
2. See what the agent is doing.
3. Receive a structured answer.
4. Inspect academic details.
5. Understand warnings and missing data.
6. Approve or reject proposed actions.
7. Continue the conversation naturally.

The agent should not overwhelm the user with long walls of text. Important results should be presented using cards, tables, progress indicators, schedule previews, warnings, and action panels.

---

## 3. Core UX Principles

## 3.1 Conversation First

The main interaction model is a conversation.

The user should be able to type natural requests such as:

```text
Check my graduation progress.
Build me a plan for next semester.
Can I take 234218?
Show me only the missing requirements.
Make the plan lighter.
Remove Friday classes.
```

The agent should respond conversationally, but with structured academic output.

The chat should be the center of the page.

---

## 3.2 Structured Academic Output

The agent should not only return plain text.

Whenever the answer contains important academic data, the UI should display it in structured components.

Examples:

* graduation summary cards,
* requirement bucket cards,
* course cards,
* prerequisite status cards,
* semester plan option cards,
* weekly schedule previews,
* transcript review tables,
* warning banners,
* confirmation panels,
* source summary cards.

Plain text should explain and summarize. Structured components should carry the detailed information.

---

## 3.3 Transparency and Trust

The user should understand what data the agent used.

Important answers should show a short “Based on” section.

Example:

```text
Based on:
- Your completed courses
- Your selected degree track
- Technion catalog requirements
- Spring 2026 course offerings
```

If data is missing, the UI must show it clearly.

Example:

```text
Missing data:
- Your catalog year is not selected.
- No completed courses were imported yet.
```

The system must distinguish between:

* confirmed facts,
* assumptions,
* warnings,
* recommendations,
* missing data,
* proposed actions.

---

## 3.4 User Control

The agent may recommend actions, but it must not silently change important user data.

The UI must require confirmation before:

* importing transcript courses,
* saving a semester plan,
* updating completed courses,
* changing degree program,
* changing track,
* changing catalog year,
* saving persistent preferences,
* deleting academic records.

The user should always see what will change before approving it.

---

## 3.5 Academic Precision

The UI should not make uncertain academic information look final.

If a result is uncertain, ambiguous, incomplete, or based on assumptions, the UI should show that clearly.

Examples:

```text
Needs review
Prerequisite data missing
Offering data unavailable
Requirement mapping is uncertain
This course may count, but confirmation is needed
```

Warnings should be visible and not hidden inside long text.

---

## 3.6 Progressive Disclosure

The UI should show the most important information first.

Detailed information should be available, but not forced on the user immediately.

Use:

* expandable sections,
* “View details” buttons,
* compact cards,
* tabs,
* grouped tables,
* collapsible requirement buckets.

The user should be able to quickly understand the result, then drill down if needed.

---

## 4. Overall Page Layout

The agent page should use a three-area layout on desktop:

```text
┌──────────────────┬──────────────────────────────┬─────────────────────┐
│ Left Sidebar     │ Main Conversation             │ Right Context Panel │
│                  │                              │                     │
│ Conversations    │ Chat messages                 │ Student context     │
│ Shortcuts        │ Agent responses               │ Current plan        │
│                  │ Composer                      │ Assumptions         │
└──────────────────┴──────────────────────────────┴─────────────────────┘
```

Main sections:

1. Left sidebar
2. Main conversation area
3. Right context panel

The main conversation area is the primary focus.

The side panels should support the workflow but should not distract from the chat.

On mobile, the layout should collapse into a single-column experience.

---

## 5. Left Sidebar

The left sidebar helps the user navigate conversations and major UniPilot areas.

It should be visually clean and not too wide.

Recommended width on desktop:

```text
260px to 320px
```

The sidebar should include:

1. New conversation button
2. Conversation history
3. Academic shortcuts
4. Optional account/profile area

---

## 5.1 New Conversation Button

At the top of the sidebar, show a prominent button:

```text
New Agent Chat
```

Clicking it should start a new agent conversation.

The button should be visually clear and easy to find.

---

## 5.2 Conversation History

Show previous agent conversations.

Each conversation item should include:

* conversation title,
* short preview,
* last updated time,
* optional status indicator.

Example titles:

```text
Graduation progress check
Spring semester plan
Transcript import
Prerequisite question
Data Engineering track planning
```

If a conversation does not yet have a title, generate one from the first meaningful user request.

Example:

User first message:

```text
Can you check what I still need to graduate?
```

Generated title:

```text
Graduation progress check
```

Conversation item states:

```text
active
normal
failed
requires confirmation
```

If a conversation has a pending confirmation action, show a small indicator.

Example:

```text
Pending action
```

---

## 5.3 Academic Shortcuts

The sidebar should include quick links to important UniPilot areas:

```text
Dashboard
Degree Progress
Completed Courses
Semester Planner
Course Catalog
Profile Settings
```

These links should not dominate the UI.

The agent conversation remains the primary focus.

---

## 5.4 Sidebar Collapsed State

The sidebar should be collapsible on desktop.

Collapsed state should show icons only.

On mobile, the sidebar should become a drawer opened by a menu button.

---

## 6. Main Conversation Area

The main conversation area is the core of the agent experience.

It should contain:

1. Chat header
2. Message timeline
3. Agent activity states
4. Structured response blocks
5. Suggested follow-up prompts
6. Composer / input box

The main conversation area should have a comfortable reading width.

Recommended maximum content width:

```text
800px to 960px
```

Structured blocks may be wider when needed, especially schedule previews and tables.

---

## 7. Chat Header

At the top of the conversation area, show a clean header.

Example:

```text
UniPilot Agent
Ask me anything about your degree, courses, requirements, and semester planning.
```

The header may also show current student context.

Example:

```text
UniPilot Agent
Information Systems Engineering · 2026 Catalog
```

If profile data is incomplete, show a small warning.

Example:

```text
Some profile details are missing. The agent may ask follow-up questions.
```

The header may include:

* conversation title,
* current degree program,
* current track,
* catalog year,
* settings/menu button,
* conversation actions.

Possible actions:

```text
Rename conversation
Export conversation
Clear conversation
Delete conversation
```

---

## 8. Empty State

When there are no messages yet, show a useful empty state.

The empty state should feel like a starting dashboard for the agent.

Example:

```text
What can I help you plan today?
```

Subtext:

```text
Ask about your degree progress, missing requirements, courses, prerequisites, or semester plan.
```

Show suggested prompt cards.

Recommended prompt cards:

```text
Check my graduation progress
Import my transcript
Build a semester plan
Explain my missing requirements
Check if I can take a course
Compare schedule options
Find electives for my track
Optimize my weekly timetable
```

Each card should be clickable.

Clicking a card should either:

1. Insert the prompt into the composer, or
2. Immediately send the prompt.

For MVP, clicking can insert the text into the composer. Later, it can send directly.

Example prompt text:

```text
Analyze my graduation progress and tell me which requirements are completed, partially completed, or still missing.
```

---

## 9. Message Timeline

Messages should be displayed in a clean, modern chat timeline.

Message types:

```text
user message
assistant message
agent activity message
system notice
structured output
confirmation panel
error message
```

The UI should visually distinguish user messages and agent messages.

---

## 9.1 User Messages

User messages should appear aligned to the right.

They should support:

* plain text,
* pasted course numbers,
* pasted course lists,
* uploaded files,
* references to previous plans,
* selected course chips.

User message visual style:

* rounded bubble,
* readable text,
* not too wide,
* subtle background,
* timestamp optional,
* edit action on hover.

User messages should support editing if the backend supports regeneration.

Actions on user message:

```text
Edit
Copy
Regenerate from here
```

---

## 9.2 Agent Messages

Agent messages should appear aligned to the left.

Agent messages can include:

* natural language explanation,
* structured cards,
* warnings,
* tables,
* schedule previews,
* proposed actions,
* source summaries,
* suggested follow-ups.

Agent messages should avoid huge paragraphs.

Use short paragraphs, clear headings, and structured blocks.

Actions on agent message:

```text
Copy
Regenerate
Give feedback
View sources
```

---

## 9.3 Message Grouping

If the agent streams several related blocks in one run, they should appear as one assistant response group.

Example:

```text
Assistant response:
- short explanation
- graduation summary card
- requirement bucket cards
- warnings
- suggested prompts
```

Do not make every structured block look like a separate assistant message unless necessary.

---

## 10. Agent Activity States

When the agent is working, the UI should show meaningful activity states.

Do not only show a generic spinner.

Examples:

```text
Thinking…
Reading your academic profile…
Checking completed courses…
Retrieving catalog requirements…
Searching course offerings…
Validating prerequisites…
Matching courses to requirements…
Building schedule options…
Preparing recommendation…
```

For multi-step workflows, show a compact step list.

Example:

```text
Analyzing graduation progress
✓ Reading student profile
✓ Checking completed courses
◐ Matching degree requirements
○ Preparing summary
```

Step states:

```text
pending
running
completed
failed
skipped
```

The active step can show a spinner or subtle animated indicator.

Completed steps can show a checkmark.

Failed steps should show a warning icon and a short explanation.

---

## 10.1 Agent Step Display Rules

Agent activity should be helpful but not noisy.

Rules:

1. Show high-level steps only.
2. Do not expose raw internal logs.
3. Do not show raw database queries.
4. Do not show stack traces.
5. Do not show hidden prompts.
6. Do not show sensitive transcript contents in activity states.
7. Use user-friendly labels.

Good:

```text
Checking course prerequisites…
```

Bad:

```text
Calling PrerequisiteValidationService.validatePrereqs(userId=...)
```

---

## 10.2 Long-Running Tasks

For tasks that take longer, the UI should show visible progress.

Examples:

* transcript parsing,
* graduation audit,
* semester plan generation,
* schedule optimization.

Show:

```text
Current step
Completed steps
Stop button
```

The user should be able to cancel the current run.

Button:

```text
Stop
```

If stopped, show:

```text
The agent run was stopped. You can continue from here or try again.
```

---

## 11. Composer / Input Box

The composer is fixed at the bottom of the main conversation area.

It should feel similar to modern AI chat apps.

Composer should include:

* multiline text input,
* send button,
* file upload button,
* optional shortcut/action button,
* optional voice button later,
* attachment chips,
* loading/disabled state.

Placeholder examples:

```text
Ask about your degree, courses, requirements, or semester plan…
```

or:

```text
Ask UniPilot to check requirements, build a plan, or explain what you still need…
```

The composer should support multiline text.

Keyboard behavior:

```text
Enter = send
Shift + Enter = new line
```

On mobile, the composer should remain fixed at the bottom.

---

## 11.1 File Uploads

The composer should support file uploads.

Used for:

* transcript PDFs,
* grade sheets,
* academic documents,
* screenshots later if supported.

When a file is selected, show an attachment chip before sending.

Example:

```text
grades_transcript.pdf  ×
```

The user should be able to remove the file before sending.

Supported file states:

```text
selected
uploading
uploaded
failed
```

If upload fails, show a clear message.

Example:

```text
Could not upload this file. Please try again.
```

---

## 11.2 Send Button States

Send button states:

```text
enabled
disabled
loading
stop-generating
```

The send button should be disabled when:

* input is empty and no file is attached,
* a message is currently being submitted,
* the user has no permission,
* the conversation is unavailable.

When the agent is running, the button may change to a stop button.

---

## 12. Suggested Follow-Up Prompts

After major agent responses, show contextual suggested prompts.

These should appear as clickable chips below the assistant response.

Examples after graduation analysis:

```text
Show only missing requirements
Recommend courses for next semester
Explain why this bucket is incomplete
Find electives that satisfy this requirement
Build the fastest graduation plan
```

Examples after course question:

```text
Check prerequisites
Show offering groups
Add this to my plan
Find alternatives
Does it count for my track?
```

Examples after semester plan generation:

```text
Remove Friday classes
Make the workload lighter
Prioritize mandatory courses
Avoid morning classes
Show another option
Save this plan
```

The suggested prompts should be short and useful.

Clicking a suggestion should either:

1. Send the prompt directly, or
2. Insert it into the composer.

For MVP, direct send is acceptable if the prompt is clear and reversible.

---

## 13. Right Context Panel

On desktop, include an optional right-side context panel.

Recommended width:

```text
320px to 420px
```

The right panel should show structured context relevant to the current conversation.

Possible sections:

1. Student Context
2. Current Plan
3. Active Requirements
4. Agent Assumptions
5. Pending Actions
6. Sources Used

The panel should be collapsible.

On mobile, it should become a drawer or separate tab.

---

## 13.1 Student Context Section

Show important student context.

Fields:

```text
Degree program
Track
Catalog year
Completed credits
Current semester
Expected graduation target
```

Example:

```text
Student Context
Degree: Information Systems Engineering
Track: Data Engineering
Catalog: 2026
Completed: 112 credits
```

If data is missing, show it clearly.

Example:

```text
Catalog year: Missing
```

Include action:

```text
Update profile
```

---

## 13.2 Current Plan Section

If the user is building or editing a semester plan, show:

```text
Selected courses
Total credits
Schedule conflicts
Requirement coverage
Workload estimate
```

Example:

```text
Current Plan
18 credits
5 courses
No schedule conflicts
Covers 3 missing requirements
```

If no active plan exists, show:

```text
No active semester plan in this conversation.
```

---

## 13.3 Active Requirements Section

When discussing degree progress, show the currently relevant requirement buckets.

Example:

```text
Relevant Requirements
- Mandatory courses: partial
- Track electives: missing 12 credits
- Project requirement: missing
```

Clicking a bucket should scroll to or open the relevant requirement card in the conversation.

---

## 13.4 Agent Assumptions Section

Show temporary conversation assumptions.

Examples:

```text
Planning for Spring 2026
Avoid Friday classes
Maximum 20 credits
Prioritize graduation speed
```

The user should be able to remove or edit assumptions.

Important distinction:

```text
Conversation assumptions are temporary.
Saved preferences are persistent.
```

If the user wants to save an assumption as a persistent preference, the UI should ask for confirmation.

---

## 13.5 Pending Actions Section

Show actions waiting for user confirmation.

Examples:

```text
Import 42 completed courses
Save semester plan Option A
Update catalog year
```

Each pending action should have:

```text
Review
Confirm
Reject
```

Do not hide pending actions only inside chat history.

---

## 13.6 Sources Used Section

For important responses, show a compact source summary.

Example:

```text
Sources Used
- Your completed courses
- 2026 catalog requirements
- Spring 2026 offerings
- Catalog wiki: Information Systems Engineering
```

Clicking a source can expand details if available.

---

## 14. Structured Response Components

The agent should return structured blocks that the frontend renders into rich UI components.

Core components:

```text
RequirementSummaryCard
RequirementBucketCard
CourseRecommendationCard
PrerequisiteStatusCard
OfferingStatusCard
TranscriptReviewTable
SemesterPlanOptions
SemesterPlanCard
SchedulePreview
WarningBanner
ConfirmationPanel
SourceSummaryCard
MissingDataCard
```

---

## 15. Requirement Summary Card

Used for graduation progress results.

Should show:

```text
total required credits
completed credits
in-progress credits
missing credits
completion percentage
graduation status
main blockers
```

Example:

```text
Graduation Progress
Completed: 112 / 160 credits
Missing: 48 credits
Progress: 70%
Status: Not ready for graduation
Main blocker: Missing track electives and project requirement
```

Visual behavior:

* Show a progress bar.
* Use clear status labels.
* Highlight blockers.
* Keep it compact.

Status options:

```text
ready_to_graduate
not_ready
needs_review
missing_data
```

User-facing labels:

```text
Ready for graduation
Not ready yet
Needs review
Missing data
```

---

## 16. Requirement Bucket Card

Each requirement bucket should be displayed as a separate card.

Examples:

```text
Mandatory Courses
Math and Science Foundation
Core Engineering Courses
Track Requirements
Elective Courses
Project / Seminar
General Studies
Sports / Enrichment
```

Each card should show:

```text
bucket name
required credits
completed credits
missing credits
status
courses used
remaining options
warnings
```

Status values:

```text
completed
partial
missing
blocked
needs_review
```

Visual design:

* Completed buckets should look calm and positive.
* Missing or blocked buckets should be clearly visible.
* Needs review should be visually distinct.

Card sections:

```text
Summary
Courses counted
Still needed
Warnings
Eligible options
```

Long lists should be collapsible.

Actions:

```text
Explain this requirement
Show eligible courses
Recommend courses
```

---

## 17. Course Recommendation Card

Used when the agent recommends or analyzes a course.

Each course card should show:

```text
course number
course name
credits
semester availability
requirement contribution
prerequisite status
schedule status
recommendation reason
warnings
```

Example:

```text
234218 · Data Structures
3 credits
Offered: Spring 2026
Counts toward: Core requirement
Prerequisites: Satisfied
Recommendation: Good choice for next semester
```

Actions:

```text
View details
Check prerequisites
Add to plan
Find alternatives
```

If the course is not eligible, show why.

Example:

```text
Cannot take yet
Missing prerequisite: 234114
```

---

## 18. Prerequisite Status Card

Used when checking course eligibility.

Fields:

```text
course
status
satisfied prerequisites
missing prerequisites
uncertain prerequisites
notes
```

Status values:

```text
satisfied
missing
partially_satisfied
unknown
needs_review
```

Example:

```text
Prerequisites
Status: Missing requirements
Missing:
- Data Structures
- Introduction to Systems Programming
```

If prerequisite data is unavailable:

```text
Prerequisite data is unavailable for this course in the selected semester.
```

---

## 19. Offering Status Card

Used when checking whether a course is offered.

Fields:

```text
semester
is offered
available lecture groups
available tutorial groups
available lab groups
exam dates
notes
```

Example:

```text
Offering Status
Spring 2026: Offered
Lectures: 2 groups
Tutorials: 4 groups
Labs: None
```

Actions:

```text
Show groups
Add to plan
Check conflicts
```

---

## 20. Transcript Review Table

Used after transcript upload and parsing.

The table should show extracted courses before saving.

Columns:

```text
Course number
Course name
Credits
Grade
Semester
Status
Notes
```

Statuses:

```text
matched
duplicate
uncertain
unmatched
ignored
```

Rows with uncertainty should be highlighted.

Examples:

```text
Uncertain: Course name does not exactly match catalog
Duplicate: Already exists in completed courses
Unmatched: Could not find course in catalog
```

Actions:

```text
Confirm import
Review uncertain rows
Cancel
Edit row
Ignore row
```

The agent must never silently import transcript data.

The user must approve the final import.

---

## 21. Semester Plan Options

When the agent generates semester plans, show multiple options as cards.

Example:

```text
Option A — Balanced
18 credits
No Friday classes
Medium workload
Covers 3 missing requirements
No conflicts
```

```text
Option B — Faster Progress
23 credits
Heavy workload
Covers 5 missing requirements
One early morning class
```

Each option should show:

```text
label
total credits
number of courses
workload estimate
requirement coverage
conflicts
pros
cons
warnings
```

Actions:

```text
View details
Use this plan
Modify this plan
Compare
```

---

## 22. Semester Plan Card

When showing one plan in detail, display:

```text
plan label
target semester
total credits
courses
selected lecture/tutorial/lab groups
requirement coverage
weekly schedule
conflicts
exam dates if available
warnings
```

Course rows inside the plan should show:

```text
course number
course name
credits
selected groups
days/times
requirement satisfied
```

Actions:

```text
Save plan
Edit courses
Change groups
Remove course
Find replacement
```

Saving requires confirmation.

---

## 23. Schedule Preview

The weekly schedule preview is important for semester planning.

It should show:

```text
days of week
time blocks
course meetings
lecture/tutorial/lab labels
conflicts
empty days
```

The layout should resemble a weekly calendar grid.

Days:

```text
Sunday
Monday
Tuesday
Wednesday
Thursday
Friday
```

Friday may be shown even if empty because users often want to avoid Friday classes.

Each class block should show:

```text
course number
course short name
lesson type
group number
time
location if available
```

Example:

```text
234218
Lecture · Group 10
08:30–10:30
```

Conflict behavior:

* overlapping classes should be visibly highlighted,
* conflict details should appear below the schedule,
* the user should be able to click a conflict to inspect it.

Actions:

```text
Change group
Remove course
Find non-conflicting alternative
```

For mobile, the schedule should become:

* horizontally scrollable, or
* day-by-day stacked layout.

---

## 24. CheeseFork-Like Lesson/Group Selection UX

The semester planner should eventually support a CheeseFork-like group selection experience.

The user should be able to select lecture/tutorial/lab groups directly from the weekly grid.

Desired behavior:

1. User adds a course to the plan.
2. The schedule grid shows possible lesson/group options.
3. The user can click a specific group block directly in the weekly grid.
4. Selected groups become visually active.
5. Unselected groups remain visible but muted if relevant.
6. Conflicts are shown immediately.
7. The selected courses list updates automatically.
8. The user should not be forced to open a separate modal just to choose a group.

The UI should support:

```text
selected group
available group
conflicting group
disabled group
recommended group
```

This is not required for the earliest MVP, but the architecture and component design should allow it.

---

## 25. Warning Banner

Warnings should be visible and specific.

Warning types:

```text
missing_prerequisite
course_not_offered
schedule_conflict
exam_conflict
requirement_not_satisfied
credit_limit_exceeded
duplicate_course
course_already_completed
ambiguous_mapping
missing_profile_data
missing_catalog_data
missing_offering_data
uncertain_transcript_row
```

Each warning should include:

```text
title
short explanation
severity
recommended action
```

Severity levels:

```text
info
warning
danger
needs_review
```

Example:

```text
Warning: Missing prerequisite
The course 234218 requires 234114, which is not listed in your completed courses.
```

Warnings should not rely only on color. Include text and icons.

---

## 26. Missing Data Card

If the agent cannot complete a task because data is missing, show a clear missing data card.

Example:

```text
Missing information
I need your catalog year before I can accurately check graduation progress.

Required:
- Catalog year

Action:
Update profile
```

Missing data card should include:

```text
missing fields
why they are needed
available action
whether the agent can continue with assumptions
```

If the agent can continue with assumptions, show the assumption clearly.

Example:

```text
I can continue assuming catalog year תשפ״ו, but the result may need review.
```

---

## 27. Confirmation Panel

The confirmation panel is used before important write actions.

Examples:

```text
Confirm transcript import
Save semester plan
Update profile
Change degree track
Delete completed course
```

Panel should show:

```text
action title
what will change
preview of affected data
warnings
confirm button
cancel/reject button
review details button
```

Example:

```text
Confirm Transcript Import

The agent found 42 completed courses in your transcript.

This will:
- Add 42 courses to your completed courses list
- Skip 3 duplicate courses
- Mark 2 rows as needing review
- Recalculate your degree progress

Buttons:
Confirm import
Review courses first
Cancel
```

Important:

* Confirm button should be clear.
* Destructive actions should require extra caution.
* The user should be able to reject or cancel.

---

## 28. Source Summary Card

Important academic answers should include a compact source summary.

Example:

```text
Based on:
- Your completed courses
- Information Systems Engineering requirements
- Spring 2026 course offerings
- Technion catalog wiki
```

This can be shown at the bottom of the agent response.

Expandable details may include:

```text
source type
source title
section title
retrieval method
confidence
```

Do not overload the normal user with too much provenance unless they expand it.

---

## 29. Error States

Errors should be clear, calm, and actionable.

Do not show raw stack traces.

Examples:

```text
I could not complete the graduation analysis because your degree track is missing.
```

```text
I found the course, but I do not have offering data for the selected semester.
```

```text
I could not build a valid schedule because the selected courses overlap.
```

Each error should include a next action when possible.

Examples:

```text
Update profile
Choose semester
Upload transcript
Try again
Show conflicts
```

Error components should support:

```text
title
message
technical code hidden or collapsed
suggested action
retry button
```

---

## 30. Loading and Skeleton States

Structured cards should have skeleton loading states.

Examples:

* requirement summary skeleton,
* table skeleton,
* course card skeleton,
* schedule preview skeleton.

For streaming responses, the text can appear first, then cards can appear as they are ready.

The UI should avoid layout jumps as much as possible.

---

## 31. Streaming Behavior

Agent responses should stream progressively when possible.

Text can stream token-by-token or paragraph-by-paragraph.

Structured blocks should appear when their data is ready.

Recommended sequence:

```text
1. User sends message.
2. User message appears immediately.
3. Agent activity appears.
4. Steps update as backend works.
5. Agent text begins.
6. Structured blocks appear.
7. Suggested prompts appear.
8. Sources and actions appear.
9. Run completes.
```

If a structured block is ready before text completes, it can appear in the message group.

---

## 32. Stop, Retry, Edit, and Regenerate

The UI should support modern chat controls.

### Stop

While the agent is running:

```text
Stop
```

Stops the current run.

### Retry

If a run fails:

```text
Retry
```

Retries the same request.

### Edit

The user can edit a previous message.

After editing, the user can regenerate from that point.

### Regenerate

The user can regenerate the last agent response.

For academic workflows, regeneration should reuse deterministic results where possible rather than recalculating everything unnecessarily.

---

## 33. Copy and Export

Important outputs should support copying.

Examples:

```text
Copy graduation summary
Copy missing requirements
Copy course recommendation
Copy semester plan
Copy transcript review
```

Future export options:

```text
Export plan as PDF
Export graduation report as PDF
Export schedule
Download transcript import review
```

For MVP, copy actions are enough.

---

## 34. Visual Design Direction

The UI should feel like a serious academic productivity tool.

Design style:

```text
clean
modern
minimal
professional
calm
high trust
```

Recommended visual characteristics:

```text
soft neutral background
clear typography
rounded cards
subtle shadows or borders
strong spacing
clear hierarchy
accessible contrast
minimal clutter
smooth transitions
```

Avoid:

```text
overly playful chatbot styling
too many colors
dense tables without spacing
huge text blocks
hidden warnings
unclear action buttons
```

---

## 35. Typography

Use readable font sizes.

Recommended:

```text
Page title: 22–28px
Section title: 16–20px
Body text: 14–16px
Small metadata: 12–13px
Button text: 14–15px
```

Line height should be comfortable.

Avoid cramped text.

Hebrew text must render well and support RTL direction.

---

## 36. RTL and Hebrew Support

UniPilot must support Hebrew academic content.

The UI should support:

```text
Hebrew text
English text
mixed Hebrew-English text
course numbers inside Hebrew sentences
RTL layout where appropriate
LTR course numbers and codes
```

Important:

* Hebrew catalog content should be readable.
* Course numbers should remain left-to-right.
* Mixed-language cards should not break alignment.
* Tables should support Hebrew names and English names.
* The UI should handle both Hebrew and English user queries.

If the main app is English, Hebrew content can still appear inside cards and source snippets.

If the app supports full Hebrew mode later, layout direction should be switchable.

---

## 37. Color and Status Language

Use colors consistently for statuses, but never rely only on color.

Status examples:

```text
Completed
Partial
Missing
Blocked
Needs review
Offered
Not offered
Eligible
Not eligible
Conflict
```

Every status should have:

```text
text label
icon or badge
color treatment
```

Examples:

```text
Completed — check icon
Missing — warning icon
Blocked — alert icon
Needs review — question/help icon
```

---

## 38. Accessibility Requirements

The agent UI must be accessible.

Requirements:

```text
keyboard navigation
visible focus states
screen-reader-friendly message structure
ARIA labels for buttons and controls
sufficient color contrast
do not rely only on color
readable font sizes
proper heading hierarchy
accessible tables
accessible dialogs
escape key closes drawers/modals
focus trap inside modal dialogs
```

The composer must be keyboard accessible.

The schedule grid should have accessible alternatives, such as a list view of classes.

---

## 39. Mobile Behavior

On mobile:

* left sidebar becomes a drawer,
* right context panel becomes a drawer or tab,
* chat remains the primary view,
* composer remains fixed at the bottom,
* structured cards stack vertically,
* large tables become horizontally scrollable or stacked,
* schedule preview becomes scrollable or day-by-day,
* buttons should be large enough to tap.

The mobile layout should not feel like a broken desktop layout.

Recommended mobile navigation:

```text
Top bar:
- menu button
- conversation title
- context button
```

Bottom:

```text
fixed composer
```

---

## 40. Responsive Breakpoints

Suggested breakpoints:

```text
mobile: < 768px
tablet: 768px–1024px
desktop: > 1024px
wide desktop: > 1440px
```

Desktop:

```text
left sidebar + main chat + right context panel
```

Tablet:

```text
left sidebar collapsible
right panel collapsible
main chat focused
```

Mobile:

```text
single-column chat
drawers for sidebar and context
```

---

## 41. Frontend Component Structure

Recommended frontend components:

```text
AgentPage
AgentLayout
AgentSidebar
ConversationList
ConversationListItem
AgentHeader
AgentConversation
MessageTimeline
UserMessage
AssistantMessage
AgentActivityIndicator
AgentStepList
AgentComposer
AttachmentChip
SuggestedPromptChips
RightContextPanel
StudentContextCard
CurrentPlanContextCard
AgentAssumptionsCard
PendingActionsCard
SourceSummaryCard
RequirementSummaryCard
RequirementBucketCard
CourseRecommendationCard
PrerequisiteStatusCard
OfferingStatusCard
TranscriptReviewTable
SemesterPlanOptions
SemesterPlanCard
SchedulePreview
WarningBanner
MissingDataCard
ConfirmationPanel
ErrorState
LoadingSkeleton
```

Components should receive structured data from the backend.

The frontend should not hardcode academic logic.

---

## 42. Frontend Rendering Rules

The frontend should render according to backend block types.

Example:

```json
{
  "type": "RequirementSummaryBlock",
  "data": {}
}
```

renders:

```text
RequirementSummaryCard
```

Example:

```json
{
  "type": "SemesterPlanOptionsBlock",
  "data": {}
}
```

renders:

```text
SemesterPlanOptions
```

The frontend should gracefully handle unknown block types.

Fallback:

```text
Show generic structured data card or text fallback.
```

Do not crash the conversation if a block type is unknown.

---

## 43. User Action Flow

The UI should support actions proposed by the agent.

Action types:

```text
confirm
reject
review
edit
save
import
add_to_plan
remove_from_plan
change_group
show_details
```

Important write actions must go through the confirmation panel.

Example flow:

```text
Agent proposes semester plan
↓
User clicks "Use this plan"
↓
UI shows confirmation panel
↓
User confirms
↓
Backend saves plan
↓
Agent confirms success
```

---

## 44. Pending Action UX

If the user leaves a conversation with a pending action, it should remain visible.

Places to show pending actions:

```text
inside the relevant assistant message
right context panel
conversation list indicator
```

Example:

```text
Pending: Confirm transcript import
```

The user should be able to return and complete or reject the action.

Pending actions should expire if the backend defines an expiration policy.

---

## 45. Trust and Safety UX

The UI should make safety rules visible without being annoying.

Examples:

For transcript import:

```text
I will not save these courses until you confirm.
```

For plan saving:

```text
This plan is only a recommendation until you save it.
```

For uncertain requirement mapping:

```text
This mapping needs review because the catalog rule is ambiguous.
```

For missing data:

```text
This result may be incomplete because your catalog year is missing.
```

---

## 46. Conversation Flow Examples

## 46.1 Graduation Progress Check

User:

```text
Check my graduation progress.
```

UI flow:

1. User message appears.
2. Agent activity starts:

   ```text
   Reading your academic profile…
   Checking completed courses…
   Matching degree requirements…
   Preparing graduation summary…
   ```
3. Agent response appears with:

   * short summary,
   * RequirementSummaryCard,
   * RequirementBucketCards,
   * warnings,
   * source summary,
   * suggested prompts.

Suggested prompts:

```text
Show only missing requirements
Recommend next semester courses
Explain incomplete buckets
Build a graduation plan
```

---

## 46.2 Course Eligibility Question

User:

```text
Can I take 234218 next semester?
```

UI flow:

1. Agent resolves the course.
2. Agent checks profile, completed courses, offering, and prerequisites.
3. Response includes:

   * clear yes/no/maybe answer,
   * CourseRecommendationCard,
   * PrerequisiteStatusCard,
   * OfferingStatusCard,
   * warnings if needed.

Suggested prompts:

```text
Show schedule groups
Add this to my plan
Find alternatives
Does it count for my track?
```

---

## 46.3 Transcript Import

User uploads transcript PDF and says:

```text
Import my completed courses.
```

UI flow:

1. Attachment chip appears.
2. Agent activity:

   ```text
   Uploading transcript…
   Parsing transcript…
   Matching courses to catalog…
   Checking duplicates…
   Preparing review table…
   ```
3. Agent shows TranscriptReviewTable.
4. Agent shows ConfirmationPanel.
5. User reviews uncertain rows.
6. User confirms.
7. Backend imports courses.
8. Agent shows success and offers to recalculate graduation progress.

Important:

The import must not happen before confirmation.

---

## 46.4 Semester Plan Generation

User:

```text
Build me a plan for next semester with no Friday classes and not more than 20 credits.
```

UI flow:

1. Agent extracts preferences.
2. Right panel shows assumptions:

   ```text
   Target semester: next semester
   Avoid Friday
   Max credits: 20
   ```
3. Agent activity:

   ```text
   Checking missing requirements…
   Searching offered courses…
   Validating prerequisites…
   Building schedule options…
   Checking conflicts…
   ```
4. Agent shows SemesterPlanOptions.
5. User clicks “View details” on Option A.
6. UI shows SemesterPlanCard and SchedulePreview.
7. User clicks “Save plan”.
8. ConfirmationPanel appears.
9. User confirms.
10. Plan is saved.

---

## 46.5 Requirement Explanation

User:

```text
Why is my track electives bucket incomplete?
```

UI flow:

1. Agent identifies relevant bucket.
2. Agent retrieves audit result and catalog explanation.
3. Response includes:

   * simple explanation,
   * current completed credits,
   * missing credits,
   * courses already counted,
   * eligible course options,
   * source summary.

Suggested prompts:

```text
Find electives for this bucket
Recommend easiest options
Show offered electives next semester
```

---

## 47. MVP UI Scope

The first version should include:

```text
Agent page layout
left conversation sidebar
main chat area
message timeline
user messages
assistant messages
composer
file attachment chips
agent activity indicator
suggested prompt cards
suggested follow-up chips
RequirementSummaryCard
RequirementBucketCard
CourseRecommendationCard
WarningBanner
ConfirmationPanel
SourceSummaryCard
basic right context panel
mobile responsive layout
```

MVP does not need:

```text
voice input
advanced schedule drag-and-drop
full CheeseFork-like group selection
PDF export
deep conversation branching
advanced analytics
```

But components should be designed so these can be added later.

---

## 48. Implementation Phases

### Phase 1 — Basic Agent Chat UI

Implement:

```text
AgentPage
AgentSidebar
AgentConversation
UserMessage
AssistantMessage
AgentComposer
basic conversation persistence
basic streaming display
empty state
suggested prompt cards
```

### Phase 2 — Agent Activity and Structured Blocks

Implement:

```text
AgentActivityIndicator
AgentStepList
RequirementSummaryCard
RequirementBucketCard
CourseRecommendationCard
WarningBanner
SourceSummaryCard
```

### Phase 3 — Confirmation and Actions

Implement:

```text
ConfirmationPanel
PendingActionsCard
action confirm/reject flow
right context panel pending action display
```

### Phase 4 — Transcript Import UI

Implement:

```text
file upload
AttachmentChip
TranscriptReviewTable
uncertain row handling
import confirmation flow
```

### Phase 5 — Semester Planning UI

Implement:

```text
SemesterPlanOptions
SemesterPlanCard
SchedulePreview
plan comparison
save plan confirmation
```

### Phase 6 — Advanced Planner UX

Implement:

```text
CheeseFork-like group selection
direct weekly-grid group selection
conflict-aware group switching
drag/click schedule interactions
```

---

## 49. Final UI / UX Rules

The UniPilot Agent UI must follow these rules:

```text
1. Conversation is the primary interaction model.
2. Structured academic output should be shown as cards, tables, warnings, and schedules.
3. The user should always understand what the agent is doing.
4. Important academic answers must show sources or data basis.
5. Missing data and assumptions must be visible.
6. Warnings must be clear and not hidden.
7. Important write actions require confirmation.
8. The frontend should render structured blocks from the backend.
9. The frontend should not implement academic business logic.
10. The UI must support Hebrew and mixed Hebrew-English content.
11. The UI must be responsive and accessible.
12. The design should feel modern, calm, professional, and trustworthy.
13. The agent should feel like one unified academic advisor.
```

---

## 50. Final Product Expectation

The final UniPilot Agent interface should feel like a modern AI academic advisor.

The student should be able to open the agent page, ask a natural question, understand what the agent is doing, receive structured academic guidance, review warnings, approve proposed actions, and continue planning their degree with confidence.

The interface should make academic requirements, course choices, and semester planning feel understandable, interactive, and manageable.

The final experience should combine:

```text
the simplicity of chat
+
the structure of an academic dashboard
+
the reliability of deterministic academic validation
+
the flexibility of an intelligent planning assistant
```
