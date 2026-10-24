---
name: implementation-plan
description: Structured planning before script creation — decompose requirements, identify dependencies, surface FM-specific constraints, and confirm approach before generating code. Use when the developer says "plan this", "plan before coding", "decompose requirements", "implementation plan", or when the agent needs to think through a non-trivial script before writing it.
---

# Implementation Plan

Decompose a script or feature request into a structured plan before generating any code. This skill produces a written plan in the conversation — not a file artifact — that the developer can review and adjust before the agent proceeds to generation.

---

## When to use

- Before building any script with more than ~10 steps or multiple decision branches
- When a request involves multiple tables, layouts, or subscript calls
- When the developer explicitly asks to plan before coding
- When called by `script-refactor` or `multi-script-scaffold` to reason about approach

## When NOT to use

- Simple one-step requests ("add a Set Variable step")
- The developer has already provided a detailed spec and just wants code

---

## Step 1: Gather context

Read `agent/CONTEXT.json` if it exists. Extract:

- `task` — the developer's description of what to build
- `current_layout` — the starting layout context (name, base TO)
- `tables` — available tables and their fields
- `relationships` — how tables connect (needed for Go to Related Record, portal context)
- `scripts` — existing scripts that may need to be called
- `layouts` — layouts that may need to be navigated to
- `value_lists` — value lists that may be referenced

If CONTEXT.json is absent or stale (doesn't match the developer's request), suggest running Push Context on the relevant layout before proceeding.

---

## Step 2: Decompose the requirement

Break the request into discrete concerns. For each, identify:

1. **What it does** — the business logic in plain language
2. **What FM objects it needs** — fields, layouts, scripts, value lists, custom functions
3. **What could go wrong** — error conditions, empty found sets, missing records, locked records
4. **FM-specific constraints** — layout context requirements, commit timing, server vs client differences

Present as a structured outline:

```
## Plan: [Feature Name]

### 1. Input validation
- Parse script parameter (JSON expected)
- Guard: exit if parameter is empty or malformed

### 2. Navigate to context
- Go to Layout [ "Invoice Details" ] — requires Invoices TO
- Perform Find for the target record
- Guard: error 401 (no records found)

### 3. Business logic
- Calculate totals from Line Items portal
- Set Field [ Invoices::Status ; "Sent" ]
- Guard: error 301 (record locked)

### 4. Subscript calls
- Perform Script [ "Send Email" ] — needs script ID from CONTEXT.json
- Check Get ( ScriptResult ) for success/failure

### 5. Cleanup
- Go to Layout [ original layout ]
- Exit Script [ result JSON ]
```

---

## Step 3: Surface dependencies and risks

After the outline, explicitly call out:

### Objects needed
List every FM object the script will reference, with where to find the ID:
- Fields: table::field (from CONTEXT.json or fields.index)
- Layouts: name (from CONTEXT.json or layouts.index)
- Scripts: name (from CONTEXT.json or scripts.index)
- Value lists, custom functions if applicable

### Missing context
If the plan requires objects not in CONTEXT.json, say so:
- "This script references the Staff table but CONTEXT.json is scoped to Invoices — suggest running Push Context on a layout with Staff access"
- "Script 'Send Email' is not in CONTEXT.json — check scripts.index or ask the developer"

### Error handling strategy
State which pattern will be used:
- Single-pass loop (try/catch equivalent) — for scripts with multiple failure points
- Inline error checks — for simple linear scripts
- Transaction wrapper — if the script modifies multiple records atomically

### Server compatibility
Flag if the script must run on FileMaker Server (PSOS, scheduled, Data API):
- No UI steps (Show Custom Dialog, Go to Field, etc.)
- Set Error Capture [ On ] + Allow User Abort [ Off ] required
- Layout context must be established explicitly

---

## Step 4: Confirm with the developer

Present the plan and ask for confirmation before proceeding to code generation. Specifically ask:

- "Does this cover everything, or are there edge cases I'm missing?"
- "Should I proceed to generate the script?"

If the developer approves, the plan becomes the specification for `script-preview` or direct fmxmlsnippet generation.

---

## Output format

The plan is written directly in the conversation as markdown. No file artifact is created unless the developer requests one (e.g., "save this plan to plans/").

If called by another skill (e.g., `script-refactor`), the plan is produced inline and the calling skill proceeds without waiting for explicit developer confirmation — the plan serves as the agent's reasoning record.
