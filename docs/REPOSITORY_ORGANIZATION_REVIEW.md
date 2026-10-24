# Repository organization review — working document

## Read this first (agent handoff)

This document is a **read-only review and proposed migration plan**, not an implementation specification or permission to reorganize the repository. It was requested after the first review missed much of `agent/`. The goal is to make this fork a focused tool for **creating new FileMaker scripts and refactoring existing ones**, while retaining other capabilities and the ability to merge updates from `petrowsky/agentic-fm`.

**Current user direction:** The error trapping and response pattern in `agent/docs/knowledge/error-framework.md` is the **default for scripts in this repository**. It must not depend on the ignored, local-only `PROJECT.md` to become active. The user wants an obvious home for FileMaker behavior and one for coding style, fewer redundant or floating files, and an agent path from request to reviewed, validated, pasteable script. Error handling is one of many FileMaker rule topics; it should not get a special top-level folder or a separate rule system. Its supporting specification, custom functions, and example templates should move from `filemaker/error-framework/` under that topic in `agent/docs/knowledge/`. They asked that this analysis be saved and improved; they have **not** approved the proposed repository reorganization. Do not move, rewrite, delete, or edit example scripts on the authority of this report. An approval should name a specific phase and file list.

Start a future review by checking `git status` and current user instructions. Preserve unrelated work and ignored local/generated data. This report records evidence observed in this checkout; recheck it after upstream updates. Paths and line numbers below are relative to the repository root and refer to the state at the time of this review. “No named consumer found” means a repository text/reference scan, not proof of no runtime use.

### Recommended decision, in brief

1. Keep FileMaker rule topics together under `agent/docs/knowledge/`, including `error-framework.md`. Move that topic's supporting specification, custom functions, and script templates from `filemaker/error-framework/` to `agent/docs/knowledge/error-framework/`. This is a resource folder beside the normal topic article, not a separate agent rule system or a special top-level framework folder.
2. Make the existing tracked `agent/docs/knowledge/error-framework.md` a **default-loaded topic** for script work via `AGENTS.md`. Tighten that article in place, preserving the short reasons needed to apply each rule. The 805-line specification remains a human design and implementation reference. Default loading is a routing decision, not a reason to relocate or rename the topic.
3. Keep `agent/docs/CODING_CONVENTIONS.md` as the coding-style authority. Keep `agent/docs/knowledge/MANIFEST.md` as a selector for task-specific FileMaker behavior articles. Error framework rules must load for **every** script task; keyword selection is insufficient for them.
4. Make new-script creation and refactoring explicit workflows. Keep step XML in the catalog, solution IDs in generated context/indexes, and output validation through FMLint. Do not reorganize examples or generated paths simply to make the tree look smaller.

## Scope, method, and important corrections

This audit inspected tracked file inventory, symlinks, `.gitignore`, agent instructions, local rules, skills, documentation, imports and named path references, shell generators, Python scripts, the webviewer API/prompt loader, and existing test fixtures. It did **not** run FileMaker, deploy scripts, test a live companion, or modify production files. A companion `/health` probe was unreachable. The working tree was clean before this document was written.

Corrections to the initial conversational report:

- `agent/config/fmlint.config.json` exists **locally and is ignored**. It disables B001 and B006, so this checkout does not currently emit their legacy suggestions. The **shipped** `agent/fmlint/fmlint.config.json` enables B001; the rule implementations still recognize only direct `Get ( LastError )` and recommend it. This is a distributable-default defect and a local-override dependency, not a demonstrated current lint failure (`agent/config/fmlint.config.json:1-8`, `agent/fmlint/rules/best_practices.py:20-37,369-385,436-453`).
- `agent/library/README.md` and `agent/sandbox/script.xml` are **tracked files inside ignored directories**. The rest of those directories is local-only. Do not call the whole directories generated or untracked. The library has no local `MANIFEST.md` or reusable item in this checkout; the lookup skill requires that manifest (`.cursor/skills/library-lookup/SKILL.md:8-25`).
- The webviewer **does not use the knowledge manifest to select articles**. `/api/docs` concatenates every `.md` file in `agent/docs/knowledge/` except `MANIFEST.md`, and the UI passes that entire text into its AI system prompt (`webviewer/server/api.ts:186-209`, `webviewer/src/App.tsx:120-125`, `webviewer/src/ai/prompt/system-prompt.ts:45-53`). This includes generic examples that conflict with the default framework. CLI/IDE and webviewer prompt routes must be assessed together.
- `validate_snippet.py` is a compatibility shim over FMLint, not an independent validator (`agent/scripts/validate_snippet.py:3-7,39-45`). It is still used by the webviewer API and several skills, so removing it would break consumers.

## Current repository map

| Area | Status, owner, and consumer |
|---|---|
| `AGENTS.md`, `.claude/CLAUDE.md`, `.cursor/AGENTS.md` | Maintained entry points. `AGENTS.md` and `.cursor/AGENTS.md` symlink to `.claude/CLAUDE.md`; `.claude/skills` symlinks to `.cursor/skills`. Links resolve locally. Whether a given Codex/Claude/Cursor session exposes every skill still needs a smoke test; repository symlinks and README text do not prove runtime discovery. |
| `agent/` | Agent-side runtime, knowledge, reference data, converters, linter, config templates, tests, and outputs. File-by-file map below. |
| `filemaker/` | Maintained FileMaker-side `Context()` source and snippet, companion script group/file, custom menu assets, framework custom functions, detailed specification, and two example scripts. The framework files support the error-handling rule topic; they are not a separate source of agent rules. Do not alter examples as part of this review. |
| `fmparse.sh`, `fmcontext.sh` | Maintained generators. Export → `agent/xml_parsed/` → `agent/context/{solution}/*.index`; both output areas are ignored (`fmparse.sh:37,389`, `fmcontext.sh:5-7,39-40`). |
| `webviewer/` | Optional but active Preact/Monaco editor and API. Reads catalog, examples, context, sandbox, library, conventions, and knowledge; runs the compatibility validator and has its own TS converters/linter/tests (`webviewer/server/api.ts:186-209,231-288,459-579,672-708`). |
| `website/` | Maintained public Astro site. Installation, validation, skills, and tree descriptions mirror README; update only where behavior or paths change. |
| Top-level `README.md`, `QUICKSTART.md`, `ARCHITECTURE.md`, `UPDATES.md`, `ROADMAP.md` and `docs/` | Maintained user documentation and design references. `PROJECT.md` is ignored local context; the wrong framework-spec path is at `PROJECT.md:20-22`. |

### `agent/` inventory: context, config, catalog, and output

| Current paths | Maintained/generated status; concrete consumer and disposition |
|---|---|
| `CONTEXT.example.json` | Tracked schema example. Keep; sync when FileMaker `Context()` changes (`ARCHITECTURE.md:249`). `CONTEXT.json` is generated by Push Context and ignored. |
| `config/automation.json.example`, `config/companion.json.example` | Tracked setup templates for deployment/OData and companion address. Keep. Their `.json` counterparts are local and ignored; skills must handle their absence. |
| `config/layout-signals.json.example`, `config/modules.json.example`, `config/removals.json.example` | Tracked defaults for solution analysis, reference tracing, and sensitive-item filtering during export. Keep near their consumers (`agent/scripts/analyze.py:1692-1713`, `trace.py:1004-1009`, `fmparse.sh:283-301`). |
| `config/webviewer-system-prompt.example.md` | Tracked UI-specific HR output/insert protocol. Keep with webviewer config, but add or inject the default script contract; it currently gives a direct `Exit Script [ Result: False ]` example (`:46-58`). A local override is ignored. |
| `config/fmlint.config.json` | Local ignored override, present here; disables B001/B006 and adds known framework namespaces. Do not edit or treat it as a shipped solution (`:1-23`). |
| `catalogs/step-catalog-en.json` | Tracked, primary step IDs/params/XML/HR grammar; consumed by Python converters, FMLint, and webviewer. Keep path stable. |
| `catalogs/CATALOG_SCHEMA.md`, `SCHEMA_GUIDANCE.md` (under `docs/`), `catalogs/UPDATING_CATALOGS.md` | Normative catalog schema, agent hand-authoring guide, and catalog maintenance process respectively. Keep their separate jobs; reconcile `UPDATING_CATALOGS.md:5` (“canonical XML reference” is examples) with the primary-catalog wording in `AGENTS.md:226-238` and `ARCHITECTURE.md:247`. |
| `catalogs/{animation-enums,find-requests,language-enums,shared-enums,window-enums}.md` | Tracked maintenance references reached from schema/updating guides; not floating merely because normal script creation does not read them. |
| `catalogs/function-catalog.json` | Tracked 1,437-line function/prototype list (`version: 22.0.4`). No literal filename consumer was found in tracked code/docs; inspect dynamic loading and intended update source before retaining, wiring, or removing it. |
| `context/`, `xml_parsed/`, `docs/filemaker/functions/`, `docs/filemaker/script-steps/`, `docs/filemaker/error-codes.md` | Ignored generated/locally fetched inputs. The first two come from export/index generators; Claris docs are created by `docs/filemaker/fetch_docs.py` and intentionally not committed (`.gitignore:1-23`, `agent/docs/filemaker/fetch_docs.py:28-38`). |
| `sandbox/` | Ignored in-progress output, but `sandbox/script.xml` is tracked. Inspect why that exception exists before changing the directory contract; preserve current local files. |
| `library/` | Ignored personal snippet collection, but `library/README.md` is tracked. The README describes a manifest and XML/HR items; no manifest or snippet currently exists here. Keep optional library route, make the empty/missing-manifest case explicit. |

### `agent/` inventory: documentation and knowledge

| Paths | Present job; proposal |
|---|---|
| `docs/CODING_CONVENTIONS.md` | 319-line coding-style authority; retain, reduce repeated style instructions elsewhere. Distinguish preferences from FileMaker behavior and default error contract. |
| `docs/AGENTIC_DEBUG.md`, `AUTOMATION.md`, `CLIPBOARD.md`, `COMPANION_SERVER.md`, `PLUGIN_INTEGRATION.md`, `SANDBOXED_ENVIRONMENT.md` | Runtime and integration guides, each reached by a specific workflow or startup branch. Keep; fix broken native-error citation in debug guide and avoid forcing every agent to read all six. |
| `docs/CONVERTERS.md`, `SCHEMA_GUIDANCE.md`, `CUSTOM_MENUS.md` | Converter overview, catalog-to-snippet guide, and custom-menu workflow. Keep as on-demand technical guides. `docs/CONVERTERS.md` points to `scripts/XML_TRANSFORMATION.md`, which is a structural mapping reference rather than a floating file. |
| `docs/filemaker/fetch_docs.py` | Tracked optional fetcher; generated vendor docs are local-only. Keep separate from authored behavioral knowledge. |
| `docs/knowledge/MANIFEST.md`, `CONTRIBUTING.md` | Keyword router and contribution process. Keep the error-framework row as a normal topic entry, and ensure the agent entry point loads that topic by default for script work rather than relying only on keyword matching. |
| `docs/knowledge/{disambiguation,executesql,field-references,file-operations,found-sets,json-functions,line-endings,record-locking,return-delimited-lists,script-ids,script-parameters,single-pass-loop,variables}.md` | Topic-specific FileMaker facts and patterns. Keep selective loading; repair generic patterns/examples that conflict with the default contract. Move only genuine style preferences to `CODING_CONVENTIONS.md`, leaving semantics here. |
| `docs/knowledge/{custom-menu-corruption,theme-layout-css,paste-dependency-order}.md` | Peripheral but reachable behavior; keep on demand for menu, layout, and multi-object install tasks. The manifest links them, so they are not floating. |
| `docs/knowledge/dry-coding.md` | Primarily style/process preference; its aligned variable example (`:45-58`) conflicts with the no-alignment rule in `CODING_CONVENTIONS.md:114-132`. Consolidate preference into style home, preserving useful decision criteria; consider removing the article after references update. |
| `docs/knowledge/error-framework.md` | Current 230-line error-handling topic and default for script work. Keep it beside the other rule topics and tighten it in place; make the default loading explicit in `AGENTS.md`. See design below. |
| `docs/knowledge/terminology.md`, `docs/reference/terminology.md` | First is only a five-line moved-file pointer; second is the full glossary and is linked by `disambiguation.md`. Once references are checked, remove the pointer and keep the glossary as human reference. |
| `docs/reference/legacy/{error-data-capture,error-handling}.md` | Historical generic error patterns. `PROJECT.md:11-13` reserves their native-error details for maintaining `FMError.Set`. Extract any unique, verified implementation fact into the appropriate function documentation or specification, then remove these if no concrete consumer remains. Do not let them compete with the default contract. |

### `agent/` inventory: executable code, linter, tests, and fixtures

| Paths | Present job; disposition |
|---|---|
| `scripts/{calc_literal,catalog_grammar,saxml_read,catalog_emit,fm_xml_to_snippet,snippet_to_hr}.py` | Converter pipeline and shared calculation grammar. Keep together; they are imported by one another, tests, FMLint, or webviewer integration. `scripts/XML_TRANSFORMATION.md` explains the SaXML mapping. |
| `scripts/{clipboard,clipboard_win,companion_server,deploy}.py` | Clipboard transport, Windows variant, HTTP host bridge, tiered installation. Core path; keep. Correct bare-`python` examples rather than moving code. |
| `scripts/validate_snippet.py`, `fmlint/` | Compatibility CLI and full Python linter. Keep shim while webviewer and skills use it; make `python3 -m agent.fmlint` the documented core check. `fmlint/` includes `__init__`, `__main__`, `catalog`, `config`, `context`, `engine`, `literals`, `types`, `formats/{detect,hr_parser,xml_parser}`, `rules/{best_practices,calculations,documentation,live_eval,naming,references,structure}`, built-in config, README, and `pyproject.toml`. These modules have clear package/import roles. |
| `scripts/{analyze,layout_to_summary,trace,extract_theme,fm_icon_extract,fm_svg_convert,install_menus}.py` | Solution analysis, layout/theme extraction, cross-reference tracing, icon conversion, and menu installation. Peripheral but active through skills/other code. Keep paths until related workflows are consciously changed. |
| `scripts/extract_steps.py` | Standalone per-step snippet extractor. No named consumer found; inspect its expected input format and whether catalog maintenance still needs it. Candidate retire after verification, not automatic deletion. |
| `scripts/bench_analyze.py` | Benchmark for `analyze.py`; no named caller found and it hardcodes two solution names (`:24-31`). Developer tooling, not daily script work. Decide whether it belongs in a development-only test/benchmark area, with generic fixtures, or should be removed. |
| `scripts/generate-step-catalog.ts.old` | 603-line bootstrap generator with no named caller. `webviewer/WEBVIEWER_INTEGRATION.md:200` says it is archived and must not run. Candidate remove after documenting the maintenance route in the catalog guide; Git history preserves it. |
| `scripts/test_*.py` | Tracked tests: `test_attrgroup_projection_hr`, `test_calc_comments`, `test_calc_literal_delimiters`, `test_catalog_emit`, `test_catalog_grammar`, `test_catalog_grammar_engine`, `test_comment_line_breaks`, `test_converter_conformance`, `test_deploy`, `test_field_missing_hr`, `test_fmlint_literals`, `test_hr_display_form_quote`, `test_hr_fullwidth_comments`, `test_hr_fullwidth_parens`, `test_icon_replace_keeps_returns`, `test_insert_calculated_result_hr_order`, `test_insert_from_device_hr`, `test_option_flags_hr`, `test_path_param_labels_hr`, `test_perform_applescript_hr`, `test_save_a_copy_as_hr`. Keep tests with code until a deliberate test-layout migration; `test_deploy.py` is interactive and needs separate handling from offline tests. |
| `fixtures/converter/` | 112 tracked offline fixtures: 103 SaXML step samples, three unsupported cases, one calculation-placement case, three FM-line JSON cases, and `saxml-to-snippet.json` plus `xml-to-hr.json`. Converter conformance consumes these; do not classify as examples to prune. |
| `snippet_examples/steps/` | 217 tracked files: `CONVENTIONS.md` plus 216 XML samples across accounts (6), AI (16), control (28), editing (8), fields (19), files (22), found sets (13), miscellaneous (29), navigation (13), open-menu-item (16), PDF (6), records (17), spelling (8), windows (15). Catalog `snippetFile`, webviewer API, and conformance checks consume them. No example edits in this review. |

## Daily paths and actual dependency edges

**New script:** request → short `AGENTS.md` route → default script error contract + coding conventions → task-selected behavior article(s) → `CONTEXT.json` when relevant, then indexes, then targeted export → per-step catalog entries → HR review → fmxmlsnippet in sandbox → FMLint → `deploy.py`/clipboard. A generic framework template without solution-specific references may use documented contracts without context (`AGENTS.md:121`, `PROJECT.md:24-32`).

**Refactor:** identify source using `script-lookup` → sanitized HR for logic and calls → targeted SaXML conversion if needed → preserve behavior and public parameter/result contract → same default rules and targeted behavior → HR diff → FMLint → deployment. A refactor must not silently rewrite dependent scripts or change behavior just to satisfy a style preference.

**Other object work:** menu UUIDs need `menu-lookup`; layouts, fields, schema, icons, data operations, and webviewer construction keep their own task triggers. Their files remain because their skills and runtime components reference them. They need not load during an ordinary script request.

**Key direct code paths that constrain moves:** `webviewer/server/api.ts` reads `agent/catalogs/step-catalog-en.json` (`:231-240`), `agent/snippet_examples/steps` (`:271-288`), `agent/library` (`:459-523`), `agent/sandbox` (`:555-579`), and every knowledge article (`:186-209`). `agent/scripts/deploy.py:103-110` resolves solution from `CONTEXT.json`; `agent/scripts/companion_server.py:755-778` writes it. `fmparse.sh` and `fmcontext.sh` generate ignored paths. The step catalog is also loaded by Python conversion and linter code. Changes to these paths are cross-component migrations, not documentation cleanups.

## Findings, with confidence and impact

| Priority | Finding and evidence | Impact / confidence |
|---|---|---|
| P0 | Default error framework depends on ignored `PROJECT.md:3-18`, while tracked `AGENTS.md:193-200` loads it only if PROJECT declares one. This is the user's explicit correction. | Other clones/agents can generate incompatible scripts. Confirmed. |
| P0 | `script-refactor/SKILL.md:108-112`, `script-review/SKILL.md:94-98`, `fm-debug/SKILL.md:36-52`, and `AGENTIC_DEBUG.md:16` teach direct native-error capture and cite missing `agent/docs/knowledge/error-data-capture.md`. `script-review/SKILL.md:127-129` asks for direct script-result reading. | Contradicts `error-framework.md:109-127,168-193`; likely wrong review/refactor advice. Confirmed. |
| P0 | Webviewer sends all knowledge articles, including generic direct-error and direct-result examples, into one prompt (`webviewer/server/api.ts:186-209`). The default prompt has a non-framework return example (`agent/config/webviewer-system-prompt.example.md:46-58`). | Webviewer may generate contrary code despite the CLI rule. Confirmed loading; model behavior needs runtime check. |
| P1 | Shipped FMLint B001/B006 only recognize `Get ( LastError )` (`agent/fmlint/rules/best_practices.py:37,385`) and suggest it (`:78,450,500`). Local ignored config disables these rules, masking the mismatch here. | Distributed defaults and webviewer lint may give wrong guidance. Confirmed source; fixture needed for end-to-end behavior. |
| P1 | The 230-line error-framework article repeats the script skeleton and logger call (`:78-107,134-166`), lists many helper names and JSON fields that can be referenced on demand, and mixes implementation details with mandatory script rules. | Every-script reading costs context and makes priority rules harder to find. Confirmed structure; target length is a design proposal. |
| P1 | `single-pass-loop.md:3-9` says use `$_error`, but the framework reserves it (`error-framework.md:44-49,67-76`). `record-locking.md:100` points to the missing error-data article and includes generic capture examples. | Topic articles can override the default accidentally. Confirmed. |
| P1 | `AGENTS.md` is a long symlinked entry point with embedded XML/schema examples (`.claude/CLAUDE.md:83-335`). The user-facing README lists skills, but no standalone new-script skill exists (`README.md:77-110`). | Excessive loading and unclear creation trigger. Confirmed. Runtime skill discovery uncertain. |
| P2 | `script-preview/SKILL.md:24-30` requires `CONTEXT.json` even though the entry point allows absence; `script-refactor/SKILL.md:12-17` assumes optional `automation.json`. | Routine tasks can stall in a fresh clone. Confirmed. |
| P2 | Style and behavior overlap: `dry-coding.md:45-58` contradicts no alignment padding (`CODING_CONVENTIONS.md:114-132`); `variables.md` repeats naming; `script-parameters.md` includes a direct-result convention superseded by the framework. | Multiple apparent authorities and extra reading. Confirmed. |
| P2 | `PROJECT.md:20-22` names nonexistent `docs/FileMaker Script Error Handling Specification.md`; actual source is `filemaker/error-framework/...`. `knowledge/MANIFEST.md:3` mentions absent `agent/docs/mbs/`. | Broken navigation. Confirmed. |
| P2 | `README.md:68-74` says `validate_snippet.py` runs automatically; root instructions mandate FMLint, while skills/webviewer still call the shim. | Validation story is inconsistent even though shim delegates to FMLint. Confirmed. |
| P3 | `function-catalog.json`, `extract_steps.py`, and `bench_analyze.py` have no named caller in tracked repository text; old generator is explicitly retired; terminology pointer has no substantive content. | Candidates for investigation/consolidation, **not** grounds for immediate deletion. Confirmed reference scan only. |

### Broken, lazy, and uncertain links

- **Confirmed broken code-formatted paths:** `agent/docs/knowledge/error-data-capture.md` (used in multiple skills/docs), `docs/FileMaker Script Error Handling Specification.md` in local PROJECT, `agent/docs/mbs/` in the manifest. Ordinary relative Markdown links checked in the earlier audit resolved; code-formatted path mentions require separate checking.
- **Deliberately lazy:** catalog enum guides, `find-requests.md`, `SCHEMA_GUIDANCE.md`, `XML_TRANSFORMATION.md`, `theme-layout-css.md`, menu knowledge, and generated Claris docs. Their task/workflow or maintenance route is documented above.
- **Needs runtime/FileMaker verification:** actual skill discovery in each supported agent; behavior of B001/B006 with framework snippets under shipped vs local config; whether `function-catalog.json` has a dynamic consumer; the live FileMaker acceptance of any future catalog edit; the role of `sandbox/script.xml` as a tracked sample. Do not infer these from text alone.

## Where rules and reasons should live

### Error handling as a normal rule topic

`agent/docs/knowledge/error-framework.md` belongs beside the other FileMaker rule topics. Its status as the default for scripts is expressed by the agent entry point loading it for every script task; it does not need a separate rules document. Move the custom functions, template XML, and detailed Dutch specification from `filemaker/error-framework/` into `agent/docs/knowledge/error-framework/` as supporting references and installation assets for this topic. The specification also contains prescriptive script guidance; keep every rule needed for agent output in the knowledge article so the agent has one rule source. Consult the specification for design or implementation detail.

### Tighten the existing topic with enough reason to apply it

Tighten `agent/docs/knowledge/error-framework.md` in place as the **single normative agent article** for default error trapping, response, logging, and trace propagation. Put a short rationale immediately under rules where order or scope is surprising. For example, “Call `FMError.Set` immediately after the risky step because later executable steps can replace the native error” belongs beside that instruction. Detailed field definitions, function implementation notes, and design history belong in the existing specification and function files, reached only when needed. No separate mandatory “why” document is proposed.

Suggested article outline, aiming for roughly 90–120 lines after content-parity review:

1. **Scope/default and dependencies:** applies to every new or changed script in this repo; framework functions and logger required for installation; templates may use public contracts before solution integration; never silently switch to direct native-error patterns.
2. **One canonical skeleton:** header, `$params`/`Trace.Init`/`$data`/`$context`, single-pass loop, cleanup, one guarded logger call, one final `Response.Make` exit. State where explicit task requests may override header defaults.
3. **Native error:** immediate `FMError.Set`, read via documented getter, clear deliberately handled errors; no direct `Get ( LastError*)` in scripts.
4. **Own error:** `Error.Make` with stable application code; framework private `$_` variables are never touched directly; logger once per script after cleanup.
5. **Child calls:** `Param.Make` for payload/trace, `Response.Capture` immediately after call, inspect through `Response.*`, create parent's own error if needed; no direct `Get ( ScriptResult )`.
6. **Output and references:** `Response.Make ( $data )`, response/trace invariants that affect callers, links to the spec and unchanged parent/child examples. Keep a compact public-function table **only** for functions script authors actually call; move implementation-only functions to the spec.

Before shortening, compare every requirement in current `error-framework.md:18-219`, `PROJECT.md:3-32`, and specification section 16 (`filemaker/error-framework/FileMaker Script Error Handling Specification.md:774`) against the new document. Do not lose the permission to override header defaults, native error 401 handling, logger timing, plain-text/JSON payload behavior, private-state rule, or template-vs-integration distinction. A length target is not a reason to omit a necessary rule.

### The other two homes

- **Coding style:** `agent/docs/CODING_CONVENTIONS.md` owns naming, tabs, spacing, comments, arrangement, and preferences. It should link to the default script contract without reprinting error mechanics. A rule like “prefer `GetFieldName()` for a string field reference” may be stated briefly there; detailed rename behavior stays in `knowledge/field-references.md`.
- **FileMaker behavior:** `agent/docs/knowledge/` owns platform semantics and gotchas, including the error-framework topic. The agent entry point loads the error-framework article for every script task; the manifest selects additional topics. Per-step parameter/XML details stay in the catalog. Topic articles should avoid unqualified script examples that violate this repo’s default error rules.

## Skills: specific trigger boundaries

| Workflow | Trigger, ownership, and decision |
|---|---|
| **New `script-create`** | Trigger: create a new FileMaker script or script steps. Do not run for review-only, preview-only, or existing-script refactor. Own context/reference selection, default contract/style loading, relevant behavior selection, HR design, catalog-based XML, FMLint, and deployment. Output: HR review and validated sandbox XML. A dedicated skill is justified because no existing skill owns this complete common journey. |
| `script-refactor` | Trigger: change an existing script while preserving observable behavior. Own target/source and call-tree inspection, dependency/contract check, focused edits, HR diff, validation/deploy. Read `script-lookup` on demand. Remove obsolete direct-error instructions and unconditional approval pauses. |
| `script-lookup`, `script-review`, `script-preview`, `fmlint` | Keep as focused support: locating source; read-only call-tree review; requested HR preview; explicit/automatic validation. They must point to the default contract rather than restating it. Preview must work without `CONTEXT.json` when the task does not need solution references. |
| `implementation-plan` | Narrow to an explicitly requested plan or genuinely complex, ambiguous script design. It should not make a routine authorized script request wait for a second approval. |
| `script-debug` and `fm-debug` | Keep diagnostic orchestration vs runtime capture distinct. `script-debug` triggers on unexplained behavior; `fm-debug` runs only when runtime instrumentation/capture is needed. Fix its direct-native-error guidance for framework scripts. |
| `script-test`, `multi-script-scaffold`, `library-lookup` | Keep for requested test scripts, interdependent placeholder scripts, and populated personal-library matches. Handle missing optional local files gracefully. |
| Layout/schema/data/menu/icon/webviewer/analysis skills | Retain with distinct triggers for those features. Their supporting scripts and docs are real consumers; do not load them during routine script composition. |

## Proposed target tree and current-to-target map

```text
AGENTS.md -> .claude/CLAUDE.md          # shorter, direct task routing
.cursor/skills/
  script-create/                       # new core workflow
  script-refactor/                     # existing core workflow, corrected
  script-lookup/, script-review/, script-preview/, fmlint/
  ...                                  # supporting and peripheral skills remain
agent/
  docs/
    CODING_CONVENTIONS.md              # style authority
    knowledge/MANIFEST.md              # behavioral selector
    knowledge/error-framework.md       # default-loaded rule topic, tightened in place
    knowledge/error-framework/         # supporting files for that topic
      FileMaker Script Error Handling Specification.md
      custom-functions/, examples/    # installables and templates, moved intact
    knowledge/*.md                      # other FileMaker behavior on demand
    reference/terminology.md           # human glossary
  catalogs/, scripts/, fmlint/, fixtures/, snippet_examples/
  config/, library/, sandbox/, context/, xml_parsed/
filemaker/
  Context.fmfn, context.xml, agentic-fm.xml, agentic-fm.fmp12
  custom_menu/
webviewer/, website/                    # retained optional products
```

| Current path(s) | Target/disposition |
|---|---|
| `agent/docs/knowledge/error-framework.md` | Tighten in place as a normal rule topic; load by default for script work through `AGENTS.md` and the webviewer. No duplicate active file. |
| `filemaker/error-framework/` | Move the specification, custom functions, and example templates into `agent/docs/knowledge/error-framework/`; repair their links and install instructions. Preserve example XML and custom-function content. |
| `PROJECT.md` | Keep only local status/install notes if needed; remove responsibility for activating the default. Correct its existing broken spec link. It remains ignored and should not be the sole authority for any shipped behavior. |
| `agent/docs/knowledge/dry-coding.md`, style sections of `variables.md` | Consolidate into `CODING_CONVENTIONS.md`; retain FileMaker scope facts in `variables.md`. Remove redundant examples after preserving intent. |
| `agent/docs/knowledge/{single-pass-loop,script-parameters,record-locking}.md` | Keep behavioral facts; replace or clearly scope generic examples so default scripts cannot copy incompatible patterns. |
| `agent/docs/knowledge/terminology.md`, `agent/docs/reference/legacy/*.md` | Remove only after incoming links and unique information are handled; retain `reference/terminology.md`. Do not create an archive merely to avoid a disposition. |
| `agent/scripts/generate-step-catalog.ts.old` | Remove after catalog maintenance path is verified; historical code remains in Git history. |
| `agent/catalogs/function-catalog.json`, `agent/scripts/{extract_steps,bench_analyze}.py` | Investigate actual consumer/update process, then keep with a clear route, move to developer tooling, or remove. No unsupported deletion claim. |
| `agent/catalogs/`, `agent/fixtures/`, `agent/snippet_examples/`, `agent/fmlint/`, generated context paths, `webviewer/`, `filemaker/` | Keep existing paths unless an independently justified change includes all code and FileMaker references. |

## Phased changes requiring separate approval

The only authorized edit so far is **this review document**. Each phase below is a proposal; approve a phase and exact path list before implementation. Within a phase, preserve unrelated working-tree content. No phase changes example XML without a separate request.

| Phase | Exact files/directories affected | Required checks and risk |
|---|---|---|
| **A — Load the error topic by default and move its resources** | `.claude/CLAUDE.md` (and its existing symlink entry points); tighten `agent/docs/knowledge/error-framework.md` in place; move `filemaker/error-framework/{FileMaker Script Error Handling Specification.md,custom-functions/,examples/}` → `agent/docs/knowledge/error-framework/`; update the moved README files, `agent/docs/knowledge/MANIFEST.md`, `agent/docs/CODING_CONVENTIONS.md`, `agent/config/webviewer-system-prompt.example.md`, `webviewer/server/api.ts`, `webviewer/src/ai/prompt/system-prompt.ts`, and any install instructions or links to the moved files; local ignored `PROJECT.md` only after inspecting its current content. | Compare every old article rule with the tightened version. Audit moved-file links and install paths. Test CLI/IDE routing and webviewer prompt payload; verify the topic loads for every script task. Preserve template XML and custom-function content. Risk: broken references or installation instructions, webviewer prompt/API behavior, and local status notes. |
| **B — Correct script workflows and lint** | `.cursor/skills/{script-refactor,script-review,script-preview,script-debug,fm-debug,fmlint,implementation-plan}/SKILL.md`; `agent/docs/{AGENTIC_DEBUG.md,AUTOMATION.md}` where incompatible instructions occur; `agent/docs/knowledge/{single-pass-loop,script-parameters,record-locking}.md`; `agent/fmlint/rules/best_practices.py`; `agent/fmlint/fmlint.config.json`; a focused offline test in `agent/scripts/`. | Test framework and generic detection separately, including the shipped config rather than relying on the local ignored override. Check absence of broken `error-data-capture.md` references. Risk: preserving generic linter behavior for other users while making this repo’s script contract default. |
| **C — Build the obvious core agent path** | New `.cursor/skills/script-create/SKILL.md`; `.claude/CLAUDE.md`; `.cursor/skills/{script-refactor,script-lookup,script-preview,implementation-plan,multi-script-scaffold}/SKILL.md`; `README.md`; `QUICKSTART.md`. | New script and refactor smoke prompts in each supported agent; inspect which skill actually triggered and which docs loaded. Verify context absent/stale cases and generic framework-template exception. Risk: skill discovery differs by platform; keep symlink paths stable until tested. |
| **D — Consolidate style and behavior** | `agent/docs/CODING_CONVENTIONS.md`; `agent/docs/knowledge/{MANIFEST.md,CONTRIBUTING.md,dry-coding.md,variables.md,field-references.md,script-parameters.md,terminology.md}.md`; `agent/docs/reference/{terminology.md,legacy/error-data-capture.md,legacy/error-handling.md}`; `agent/docs/knowledge/{file-operations.md,found-sets.md,json-functions.md,line-endings.md,return-delimited-lists.md,script-ids.md,executesql.md,disambiguation.md,paste-dependency-order.md,custom-menu-corruption.md,theme-layout-css.md,record-locking.md,single-pass-loop.md` **only where a concrete conflict/reference fix is identified**. | Run manifest/link/reference audit and style-example review. Keep untouched behavior articles untouched when no conflict exists. Risk: silently changing FileMaker semantics while removing duplication. |
| **E — Decide floating candidates and public docs** | `agent/scripts/{generate-step-catalog.ts.old,extract_steps.py,bench_analyze.py,clipboard.py,install_menus.py}`; `agent/catalogs/{function-catalog.json,UPDATING_CATALOGS.md}`; `agent/docs/{CONVERTERS.md,SCHEMA_GUIDANCE.md,CUSTOM_MENUS.md}`; `README.md`, `ARCHITECTURE.md`, `webviewer/WEBVIEWER_INTEGRATION.md`, relevant `website/src/pages/*.astro`. | Prove candidate consumers or absence first. Run converter conformance and webviewer tests/build if their contracts change; require live FileMaker round-trip for a catalog change. Risk: named-reference search misses dynamic loading, and site/docs drift. |
| **F — Acceptance** | Disposable output in `agent/sandbox/` only; no example changes. | In FileMaker-capable environment, perform one new-script and one refactor path: correct skill, minimal relevant docs, HR review, reference resolution, valid XML, FMLint, clipboard/deploy, and paste/copy-back where required. Record any platform-specific gaps before calling migration done. |

### Decisions to discuss before phase A

1. Keep `agent/docs/knowledge/error-framework.md` alongside the other FileMaker rule topics. Move its supporting assets into `agent/docs/knowledge/error-framework/`, and make default loading explicit in the agent entry point and webviewer. Do not create a special top-level framework folder.
2. Should the shipped tool support scripts that do not use this framework? Recommendation: preserve generic linter capability, while making this repository’s agent workflow and webviewer prompt use the framework by default. The contract is a repo default, not a claim about all FileMaker solutions.
3. What is the intended role of the tracked `agent/sandbox/script.xml` and `agent/catalogs/function-catalog.json`? Their current consumers are unclear; decide after direct inspection, not from the directory names.

**Next authorization boundary:** ask for approval of **Phase A and its exact file list** before changing any file other than this working document. Do not interpret approval to save this report as approval for Phase A.
