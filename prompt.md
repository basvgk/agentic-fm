# Repository organization review

**Draft prompt. Do not run this review until I explicitly ask you to execute it.**

## Goal

Help me turn this repository into a focused tool for **creating new FileMaker scripts and refactoring existing ones**. Keep the path from a request to a reviewed, validated, pasteable script clear. Other capabilities should remain (e.g. making layouts, fields, etc), but assess their role and placement instead of assuming they belong in the core.

**Minimize redundant and floating files.** Similar instructions and FileMaker behavior should live together in one well-defined place. A file should have a clear purpose, owner, and route from the agent entry point or a relevant workflow. Consolidate duplicated guidance, remove obsolete copies and scattered instructions after their useful content has been preserved, and replace repetition elsewhere with a direct pointer to the authoritative source. Avoid keeping an archive merely to avoid deciding whether a file is needed.

I also need two obvious, authoritative places to maintain:

1. **FileMaker behavior**: facts, constraints, platform differences, and practical gotchas that affect script correctness.
2. **My coding style**: naming, formatting, structure, comments, and other preferences for scripts and calculations.

Use the current `agent/docs/knowledge/` plus `agent/docs/knowledge/MANIFEST.md` and `agent/docs/CODING_CONVENTIONS.md` as the starting candidates for those homes. Check whether they actually serve these purposes consistently. Propose changes where needed; do not create competing sources of truth.

## Scope and guardrails

- **This is an analysis and proposal only. Do not move, rename, delete, rewrite, or otherwise alter repository files without my explicit approval of a concrete change plan.** Do not execute the proposed reorganization as part of this review.
- The repo is a fork of the repo `petrowsky/agentic-fm`. I want to keep the option to update my repo when the upstream gets updated.
- Read the repository's agent instructions and local project rules first. Preserve working script creation, refactoring, validation, clipboard, and deployment paths in any proposal.
- Do NOT alter examples (e.g. example scripts). If you consider this necessary, propose the change, reason and only continue after permission. Bundle requests.
- Treat generated or local-only data separately from maintained source files. Identify these from `.gitignore`, documentation, and generator code before drawing conclusions about unused files.
- Do not label a file unnecessary solely because no Markdown file links to it. Check imports, shell and Python calls, package scripts, config paths, FileMaker references, symlinks, and generated paths as appropriate.
- Do not silently change the meaning of established coding or FileMaker behavior rules. Flag conflicting rules and recommend which source should win.
- Do not mistake a deliberately lazy-loaded reference for a floating file. Show how an agent reaches it from the entry point, manifest, or workflow before recommending removal.
- Prefer short, task-specific routing over instructions to read a stack of documents before every task. Keep shared rules in one home; put genuinely directory-specific rules near the files they govern. Do not add mandatory chains of pointer files that an agent must follow to reach a required rule. An index that lets the agent select a relevant behavior article is acceptable if it saves reading unrelated articles.
- Use skills for repeatable workflows with a clear trigger and useful procedure, scripts, or assets. Keep stable FileMaker facts and my coding rules in their authoritative references rather than duplicating them inside every skill. Do not create a skill simply to hold a pointer to another document.

## Review

1. **Map the current repository.** Inventory top-level areas and the files that matter to creating or refactoring scripts. For each, state its purpose, whether it is maintained, generated, archival, or local-only, and which workflow uses it. Include agent entry points, skills, catalogs, examples, library code, context sources, converters, linter, clipboard/deploy tools, tests, documentation, and optional UI components.
2. **Trace references and dependencies.** Map references among agent instructions, docs, skills, code, configuration, and scripts. Identify broken paths, stale instructions, duplicate guidance, conflicting rules, and maintained files with no discoverable consumer. Find instructions or behavior repeated across `AGENTS.md`, skills, docs, and code prompts. For each duplication, identify the authoritative home and which copies should become links or be removed. Distinguish confirmed findings from possible issues that need runtime or FileMaker verification. Cite paths and line numbers for material findings.
3. **Design the everyday agent path.** Recommend a concise `AGENTS.md` entry point with direct paths and clear triggers for new scripts, refactors, FileMaker behavior, coding style, solution context, step XML structure, and validation/deployment. Keep essential shared rules there; load detailed guidance when the task calls for it. Assess the number of required hops from entry point to applicable rule, and simplify chains that make agents open several pointer files. Use a scoped `AGENTS.md` only where its instructions apply to that directory. Routine agent work should not require a broad search to discover the correct guidance. The one-time repository audit may, of course, scan files.
4. **Review the skills as a system.** Identify which existing skills serve the core new-script and refactor journeys, how agents discover them, and where triggers or steps overlap. Recommend which to keep, narrow, merge, retire, or create. In particular, assess whether creating a new script needs its own skill or is already covered well by the existing workflows. For each proposed core skill, state its trigger, when it should not run, what it owns, what it reads on demand, and its output. Keep descriptions short and distinct. Check that skill locations and symlinks work for the supported agents; do not assume a skill is discoverable merely because it appears in a README.
5. **Define the two knowledge homes.** Recommend the authoritative location and update process for FileMaker behavior and for my coding style. Explain where script-step XML specifications, solution-specific context, and project-specific framework rules belong, since they are different kinds of information. Specify how agents find applicable behavioral articles without reading every article on every task. Keep mandatory style and framework rules directly discoverable from the relevant workflow.
6. **Propose a target structure.** Give a concise directory tree and a mapping from current paths to proposed paths or dispositions: keep, consolidate, move, remove, or investigate. Use archive only where there is a concrete reason to retain historical material. Account for every maintained file that appears unreferenced or out of place. Prioritize the script creation and refactoring workflow. Explain what happens to related features such as layouts, schema tools, custom menus, the webviewer, and the website without assuming they can safely be removed.
7. **Plan the migration.** Break the work into small, reviewable phases. For each phase, list exact files or directories affected, reference updates required, verification commands or manual checks, and any risks. Include a way to confirm the final agent path works for both a new script and a refactor, including whether the intended skills trigger and load only relevant guidance.

## Deliverable

Present a report for discussion before editing the repository:

- A short summary of the current state and the proposed organizing principle.
- A prioritized findings table with evidence, impact on script work, and confidence.
- A reference/dependency map and an explicit list of broken or uncertain links.
- A consolidation list showing each duplicated or scattered rule, its proposed authoritative home, and what happens to the other copies; plus a list of floating files with evidence and disposition.
- The proposed target tree and current-to-target path mapping.
- A recommended `AGENTS.md` navigation outline, plus clear ownership rules for FileMaker behavior and coding style.
- A proposed skill set for the core workflows, with trigger boundaries and dispositions for overlapping or peripheral skills.
- A phased change plan with checks and decisions that require my input.

Ask me to approve a **specific phase and file list** before making any repository changes. Keep any existing unrelated work in the working tree intact.
