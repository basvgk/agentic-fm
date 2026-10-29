# Mandatory Error Framework and Call-Chain Tracing

This solution uses a standard error, response, logging, and tracing framework.
This is the minimum error-handling knowledge required before giving
instructions or drafting any script creation, edit, or refactor in this
project. Load it for every script change, independent of task keywords.
The canonical human-readable design is
[`FileMaker Script Error Handling Specification`](../../../filemaker/error-framework/FileMaker%20Script%20Error%20Handling%20Specification.md).
This document is its concise, agent-executable interpretation.
These rules are the single active source for native-error capture, error
responses, and logging in every business script that is created, updated, or
refactored. Other knowledge articles cover topic behavior such as record-lock
retry decisions or single-pass loop structure; they do not define competing
capture patterns.

The generic `Get ( LastError )` capture pattern remains applicable only inside
the implementation of `FMError.Set` itself.

In the VanGenabeek solution, the logger is `(94000) Creeer foutmelding`,
script ID `1330`. The calls below pass `Error.Get` and set Wait for completion
to Off. Rebind the script reference when porting the templates to another
solution.

## Required custom functions

The following documented public contracts are sufficient to generate reusable
framework script templates. Do not require solution context, an exported
custom-function index, or custom-function implementation code merely to
generate such a template. Never substitute direct calculations or legacy
functions for these contracts.

When integrating a template into a specific solution, verify that the required
functions and logger exist when a solution export or context is available.

```text
FMError.Set, FMError.Get, FMError.GetCode, FMError.Clear, FMError.SetCompleteError
Trace.Init, Trace.Get
Environment.Get, RecordContext.Get
Error.Make, Error.Get, Error.GetID, Error.GetCode, Error.GetUserMessage
Param.Make, Param.Payload
Response.Make, Response.Capture, Response.Get, Response.IsOK,
Response.GetData, Response.GetError, Response.GetErrorCode,
Response.GetErrorMessage, Response.GetErrorUserMessage
ShortId, JSON.IsValid
```

The framework's dotted custom-function names are an intentional namespace
exception to the general custom-function naming convention.

## Custom-function contracts

Framework variables are private implementation state. Trigger a side-effect
function with disposable `$r`, then read its state only through its documented
getter. Do not assign or read `$_error`, `$_FMError`, `$_trace`,
`$_child_params`, or `$_child_result` directly.

| Function | Input | Output and script contract |
|---|---|---|
| `FMError.Set` | none | Captures the immediately preceding native error, sets `$_FMError`, and returns its numeric code. Use directly as `If [ FMError.Set ≠ 0 ]`, or call as `$r` and inspect through `FMError.GetCode` or `FMError.Get`. |
| `FMError.Get`, `FMError.GetCode`, `FMError.Clear` | none | Return the native-error object, its code, or a cleared empty result. |
| `FMError.SetCompleteError` | code, message, userMessage, context object | Captures the native error and, when its code is non-zero, creates the current script's complete error through `Error.Make`; returns the native code. |
| `Trace.Init`, `Trace.Get` | none | Start or continue trace from the script parameter, or return it. `Trace.Init` sets internal trace state. |
| `Environment.Get`, `RecordContext.Get` | none | Return a current environment or record/found-set snapshot. |
| `Error.Make` | code, message, userMessage, context object | Creates the log-ready error, sets internal error state, and returns it. Call as `$r`; read only through the `Error.Get*` accessors. |
| `Error.Get`, `Error.GetID`, `Error.GetCode`, `Error.GetUserMessage` | none | Return the current script's complete log-ready error, its human-reportable ID, application code, or user-facing message; return an empty value when no error exists. |
| `Param.Make` | business JSON value or plain text | Returns a child-parameter envelope with separate `payload` and `trace` values; valid JSON retains its type and plain text is preserved. Use directly as the child call parameter. |
| `Param.Payload` | none | Returns the current script parameter's business `payload` value, preserving JSON or plain text; returns empty when unavailable. |
| `Response.Make` | business data | Returns the final response envelope using current internal error state. |
| `Response.Capture` | none | Captures the child result, sets internal child-response state, and returns it. Call as `$r`. |
| `Response.Get`, `Response.IsOK`, `Response.GetData`, `Response.GetError*` | none | Read captured child response, success state, data, or stable child-error values. |
| `ShortId`, `JSON.IsValid` | documented parameters | Return a short identifier or JSON-validity result. |

## Reserved script variables

These names are private framework state. `$_` variables are script-local in
FileMaker; the underscore is a framework reservation, not a global scope.
Scripts do not assign or read them directly.

```text
$_data, $_error, $_FMError, $_context, $_params, $_trace,
$_child_params, $_child_result, $_child_error, $_child_data, $_paramPayload
```

## Required script flow

Every framework script has one final exit point. By default, its opening turns
off user abort and turns on error capture. A task prompt may explicitly
override either default. It then initializes the parameter, trace, response
data and context in this order:

```text
Allow User Abort [ Off ]
Set Error Capture [ On ]
Set Variable [ $params ; Get ( ScriptParameter ) ]
Set Variable [ $r ; Trace.Init ]
Set Variable [ $data ; "" ]
Set Variable [ $context ; "{}" ]
Loop
  # Validate, work, and call children.
  # Exit the loop when Error.Get is nonempty.
  Exit Loop If [ True ]
End Loop
# Cleanup must not replace framework error state.
If [ not IsEmpty ( Error.Get ) ]
  Perform Script on Server [ "(94000) Creeer foutmelding" ; Parameter: Error.Get ; Wait for completion: Off ]
End If
Exit Script [ Response.Make ( $data ) ]
```

Use the project coding-convention documentation comments and a single-pass
loop. Do not add early `Exit Script` steps after initialization. Log the
current script's error once after the main loop and cleanup, immediately
before the final `Exit Script`.

## Native FileMaker errors

Immediately after every relevant error-prone script step, call `FMError.Set`
before any other executable script step. Comment and blank-comment steps may
appear between the risky step and `FMError.Set`:

```text
<error-prone step>
If [ FMError.Set ]
  # Build this script's own error with Error.Make.
End If
```

`FMError.Set` captures the native error code, detail, location, line, and step
in one expression, sets `$_FMError`, and returns the captured numeric code. `$r` is a
deliberately disposable result variable. Do not set `$_FMError` from the
function's return value. Framework scripts never call `Get ( LastError )`,
`Get ( LastErrorDetail )`, or `Get ( LastErrorLocation )` directly; those
calls are internal implementation details of `FMError.Set`.

**FMError.Set Usage (General Rule):**
- Use `If [ FMError.Set ]` directly — it evaluates to True when the captured error code is non-zero.
- Do not use an intermediate `$r` variable solely to check `FMError.Set ≠ 0`.

If a native error is deliberately handled without creating an application
error, clear it before later work using `Set Variable [ $r ; FMError.Clear ]`.
Error 401 is also captured through `FMError.Set`, but no matching records can
be an expected outcome. Do not create an application error with `Error.Make`
or log solely because a find returned 401 when an empty found set is valid.
Clear the captured native error before later work. Create an application error
only when the requested behavior requires a match.

### Common steps and likely errors

Capture after each listed operation when its failure can change data, control
flow, or the result promised to the caller. This table lists common codes, not
an exhaustive mapping; consult the step catalog or Claris help for the specific
step and its options.

| Step or operation | Capture/check immediately after | Likely errors to consider |
|---|---|---|
| `Open Record/Request` before editing | `FMError.Set` immediately after; this is the preferred explicit lock check | 200 record access denied; 301 record is in use by another user |
| First `Set Field` on the current record when it is not already open | `FMError.Set` immediately after; `Set Field` implicitly opens the record | 200–202 record/field access or privilege; 301 record is in use by another user |
| Further `Set Field` steps on that successfully opened record | No repeated check solely for the same record lock. If field privileges, field-specific access, or another independent failure is relevant, call `FMError.Set` after each step | 201 field cannot be modified; 202 field access denied; other field-specific errors |
| `Set Field` targeting a related record | `FMError.Set` immediately after each related-record update | 200–202 access or privilege; 301 related record is in use by another user |
| `Commit Records/Requests` | `FMError.Set` after each commit | 301 lock; 306 or 512 concurrent modification; 500–507, 509–511, or 513 validation/value errors |
| `Perform Find`, `Perform Quick Find` | `FMError.Set` immediately after, before another executable step | 400 empty find criteria; 401 no records match. If empty results are valid, do not call `Error.Make` just for 401; clear the native error and continue |
| `Go to Layout`, record navigation, `Go to List of Records` | `FMError.Set` before relying on the destination or current record | 105 missing layout; 101 missing record; 401 no records match |
| `Open Transaction`, `Commit Transaction` | `FMError.Set` after each transaction step, as well as after risky writes inside it | 307 transaction lock communication error; record conflicts such as 301, 306, or 512 |
| Import/export, file, URL, or mail steps | `FMError.Set` immediately after each operation | Step-specific: 102 only for the legacy `Export Field Contents` file-clearing hack; 409/410 import/export order, 729 import failure, 800/802 file access, 1629–1631 URL, or 1501–1507 mail |
| `Perform Script`, `Perform Script on Server` | Use `Response.Capture` immediately; do not use `FMError.Set` to inspect the child result | Check `Response.IsOK` and `Response.GetErrorCode`; the child error is in its response, not native error state |

Use `Error.Make` only when the condition is an actual failure against the
script's business contract. An expected outcome such as a valid empty found set
needs neither an application error nor an error log. Avoid speculative capture
and logging branches for outcomes that cannot affect the requested result.

## Application errors and logging

Every failure made by the current script must have its own stable application
code and be created where it is detected with:

```text
Set Variable [ $r ; Error.Make ( code ; message ; userMessage ; $context ) ]
```

`Error.Make` builds the log-ready object, assigns a per-error `errorID`, and
obtains the native error, environment, record context, trace, incoming
parameter, and timestamps internally. When the most recently captured child
response has non-empty `data`, it automatically adds `childResponseData` at the
root of the log-only object. Objects and arrays are embedded as `JSONRaw`; all
other values are embedded as `JSONString`. `message` is developer-facing;
`userMessage` is optional and must never cause a dialog automatically.

Do not mutate framework error state before logging and do not put a nested
child error in the error object. A logger integration must not replace the
current script's internal error state.

Do not call the logger at each `Error.Make`. After the main loop and cleanup,
check the current script's error once and call the logger at most once, just
before the final `Exit Script`. Each script in a parent/child chain may log its
own error once; this is one logging call per script, not one per error created
inside that script.

```text
If [ not IsEmpty ( Error.Get ) ]
Perform Script on Server [ "(94000) Creeer foutmelding" ; Parameter: Error.Get ; Wait for completion: Off ]
End If
Exit Script [ Response.Make ( $data ) ]
```

## $context Handling

- Initialize `$context` as `"{}"`. Include all relevant instantiated variables or field values into the context when an error occurs.
- The framework automatically includes the incoming parameter, trace, native error (from `FMError.Set`), environment, and record context in the error object created by `Error.Make`. **Do not** include these in the `$context`.

## Error Codes

- Use concise, stable codes without the script name as prefix (e.g., `INVALID_PARAMETER`, `WINDOW_ERROR`, `RECORD_LOCKED`).
- Reserve prefixed codes (e.g., `PARENT.CHILD_ERROR`) for errors created **because a child script returned an error**.

## Child scripts and trace propagation

Build a child parameter only through `Param.Make ( payload )`; it returns an
envelope with a distinct `payload` value and current `trace` object. The payload
may be valid JSON or plain text. A child reads its business input only through
`Param.Payload`. Call `Response.Capture` immediately
after every child script call, before any other script call:

```text
Perform Script [ child script ; Parameter: Param.Make ( <business JSON payload> ) ]
Set Variable [ $r ; Response.Capture ]
If [ not Response.IsOK ]
  # Create this parent script's own Error.Make result.
  # The logger runs once after this script's main loop.
End If
```

The parent reads `Response.GetErrorCode` or related accessors to decide its
own error. `Error.Make` automatically places non-empty `Response.GetData` in
the log-only root field `childResponseData`, irrespective of the response's
`ok` value. It is not part of `error.context` and is not returned to a higher
parent. A child returns its application error through its response; native
error state after `Perform Script` is irrelevant and must never be captured.
On success, assign `Response.GetData` to a normal local variable when it is
needed.
Never read `Get ( ScriptResult )` directly in a framework script.

## Worked parent/child templates

The [child script example](../../../filemaker/error-framework/examples/template-framework-child.xml)
and [parent script example](../../../filemaker/error-framework/examples/template-framework-parent.xml)
show the parent/child response flow as fmxmlsnippet files. Each example makes
errors in its main flow and calls its logger once after the loop. Their
VanGenabeek logger reference is script ID `1330`; rebind it when porting.

## Response and trace contracts

Every final result is produced by `Response.Make ( $data )`:

```json
{ "schemaVersion": 1, "ok": true, "data": "", "error": {} }
```

For an error, `ok` is false and `error` contains only the stable response
error: `errorID`, `code`, `message`, `userMessage`, `context`, and `fmError`.
The complete logger object additionally contains record context, environment,
trace, parameter, timestamps, and (when the most recent captured child response
has non-empty data) the log-only `childResponseData` field.

One root execution receives a UUID `traceID`; every child retains it and
appends its current script name to `scriptPath`. `errorID` is unique per error
and must not be reused as the trace identifier.

## Incremental Migration of Existing Scripts

When refactoring an **existing script** (not creating a new template) to use the error framework, follow these rules to maintain backward compatibility with parent scripts that have not yet been migrated:

### Parameter Handling
- Keep the original `Get ( ScriptParameter )` step **active** to read the incoming parameter.
- Add `Param.Payload` as a **disabled** (commented-out) step for future migration.
- Use the same variable name (`$payload`) for both so the rest of the script is unchanged.

```text
Set Variable [ $payload ; Get ( ScriptParameter ) ]
# Set Variable [ $payload ; Param.Payload ]  // disabled — enable when parent migrates
```

### Response Format
- Keep the original response format (e.g., `$return` JSON) **active** with the final `Exit Script`.
- Add `Response.Make ( $data )` as a **disabled** step for future migration.
- Add disabled `Set Variable` steps for `Response.GetData`, `Response.GetErrorCode`, `Response.GetErrorMessage`, `Response.GetErrorUserMessage` so parent scripts can extract values after they migrate.

### Business Logic Steps
- **Never remove** existing business logic steps (e.g., `Commit Records/Requests`, `Set Field`, navigation steps) during framework migration.
- Add native-error capture only where a failure can affect the promised result, data, or control flow. Create an `Error.Make` application error only for an actual failure against the script's business contract; do not add speculative captures or logs for expected outcomes.

## References

| Name | Type | Claris help |
|---|---|---|
| Set Error Capture | step | [set-error-capture](https://help.claris.com/en/pro-help/content/set-error-capture.html) |
| Perform Script | step | [perform-script](https://help.claris.com/en/pro-help/content/perform-script.html) |
| Perform Script on Server | step | [perform-script-on-server](https://help.claris.com/en/pro-help/content/perform-script-on-server.html) |
| Exit Script | step | [exit-script](https://help.claris.com/en/pro-help/content/exit-script.html) |
| Get ( LastError ) | function | [get-lasterror](https://help.claris.com/en/pro-help/content/get-lasterror.html) |
| Get ( ScriptResult ) | function | [get-scriptresult](https://help.claris.com/en/pro-help/content/get-scriptresult.html) |
| FileMaker error codes | reference | [error-codes](https://help.claris.com/en/pro-help/content/error-codes.html) |
