# Mandatory Error Framework and Call-Chain Tracing

This solution uses a standard error, response, logging, and tracing framework.
The canonical human-readable design is
[`FileMaker Script Error Handling Specification`](../../../docs/FileMaker%20Script%20Error%20Handling%20Specification.md).
This document is its concise, agent-executable interpretation.
These rules supersede the archived generic error-handling and error-data-capture
articles for every business script that is created, updated, or refactored.

They also supersede direct native-error and direct script-result examples in
other active knowledge articles. Those articles may still be used for their
topic-specific behavior, such as record-lock retry decisions or single-pass
loop structure.

The generic `Get ( LastError )` capture pattern remains applicable only inside
the implementation of `FMError.Set` itself.

## Required custom functions

The following documented public contracts are sufficient to generate reusable
framework script templates. Do not require solution context, an exported
custom-function index, or custom-function implementation code merely to
generate such a template. Never substitute direct calculations or legacy
functions for these contracts.

When integrating a template into a specific solution, verify that the required
functions and logger exist when a solution export or context is available.

```text
FMError.Set, FMError.Get, FMError.GetCode, FMError.Clear
Trace.Init, Trace.Get
Environment.Get, RecordContext.Get
Error.Make, Error.Get
Param.Make
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
getter. Do not assign or read `$_error`, `$_FMerror`, `$_trace`,
`$_child_params`, or `$_child_result` directly.

| Function | Input | Output and script contract |
|---|---|---|
| `FMError.Set` | none | Captures the immediately preceding native error, sets internal native-error state, and returns its object. Call as `$r`; inspect through `FMError.GetCode` or `FMError.Get`. |
| `FMError.Get`, `FMError.GetCode`, `FMError.Clear` | none | Return the native-error object, its code, or a cleared empty result. |
| `Trace.Init`, `Trace.Get` | none | Start or continue trace from the script parameter, or return it. `Trace.Init` sets internal trace state. |
| `Environment.Get`, `RecordContext.Get` | none | Return a current environment or record/found-set snapshot. |
| `Error.Make` | code, message, userMessage, context object | Creates the log-ready error, sets internal error state, and returns it. Call as `$r`; read only through `Error.Get`. |
| `Error.Get` | none | Returns the current script's complete log-ready error, or empty when none exists. |
| `Param.Make` | business JSON payload | Returns child parameter with trace attached. Use directly as the child call parameter. |
| `Response.Make` | business data | Returns the final response envelope using current internal error state. |
| `Response.Capture` | none | Captures the child result, sets internal child-response state, and returns it. Call as `$r`. |
| `Response.Get`, `Response.IsOK`, `Response.GetData`, `Response.GetError*` | none | Read captured child response, success state, data, or stable child-error values. |
| `ShortId`, `JSON.IsValid` | documented parameters | Return a short identifier or JSON-validity result. |

## Reserved script variables

These names are private framework state. `$_` variables are script-local in
FileMaker; the underscore is a framework reservation, not a global scope.
Scripts do not assign or read them directly.

```text
$_data, $_error, $_FMerror, $_context, $_params, $_trace,
$_child_params, $_child_result, $_child_error, $_child_data
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
Exit Script [ Response.Make ( $data ) ]
```

Use the project coding-convention documentation comments and a single-pass
loop. Do not add early `Exit Script` steps after initialization.

## Native FileMaker errors

Immediately after every relevant error-prone script step, call `FMError.Set`
before any other executable script step. Comment and blank-comment steps may
appear between the risky step and `FMError.Set`:

```text
<error-prone step>
Set Variable [ $r ; FMError.Set ]
If [ FMError.GetCode ≠ 0 ]
  # Build this script's own error with Error.Make.
End If
```

`FMError.Set` captures the native error code, detail, location, line, and step
in one expression, sets `$_FMerror`, and returns that same object. `$r` is a
deliberately disposable result variable. Do not set `$_FMerror` from the
function's return value. Framework scripts never call `Get ( LastError )`,
`Get ( LastErrorDetail )`, or `Get ( LastErrorLocation )` directly; those
calls are internal implementation details of `FMError.Set`.

If a native error is deliberately handled without creating an application
error, clear it before later work using `Set Variable [ $r ; FMError.Clear ]`.
Error 401 is always captured through `FMError.Set`; whether it becomes an
application error in the response depends on the script's business context.

## Application errors and logging

Every failure made by the current script must have its own stable application
code and be created with:

```text
Set Variable [ $r ; Error.Make ( code ; message ; userMessage ; $context ) ]
Perform Script on Server [ "SYS_LogError" ; Parameter: Error.Get ]
```

`Error.Make` builds the log-ready object, assigns a per-error `errorID`, and
obtains the native error, environment, record context, trace, incoming
parameter, and timestamps internally. `message` is developer-facing;
`userMessage` is optional and must never cause a dialog automatically.

Do not mutate framework error state before logging and do not put a nested
child error in the error object. A logger integration must not replace the
current script's internal error state.

## Child scripts and trace propagation

Build a child parameter only through `Param.Make ( payload )`; it adds the
current trace. Call `Response.Capture` immediately after every child script
call, before any other script call:

```text
Perform Script [ child script ; Parameter: Param.Make ( <business JSON payload> ) ]
Set Variable [ $r ; Response.Capture ]
If [ not Response.IsOK ]
  # Create and log this parent script's own Error.Make result.
End If
```

The parent reads `Response.GetErrorCode` or related accessors to decide its
own error. A child returns its application error through its response; native
error state after `Perform Script` is irrelevant and must never be captured.
On success, assign `Response.GetData` to a normal local variable when it is
needed.
Never read `Get ( ScriptResult )` directly in a framework script.

## Response and trace contracts

Every final result is produced by `Response.Make ( $data )`:

```json
{ "schemaVersion": 1, "ok": true, "data": "", "error": {} }
```

For an error, `ok` is false and `error` contains only the stable response
error: `errorID`, `code`, `message`, `userMessage`, `context`, and `fmError`.
The complete logger object additionally contains record context, environment,
trace, parameter, and timestamps.

One root execution receives a UUID `traceID`; every child retains it and
appends its current script name to `scriptPath`. `errorID` is unique per error
and must not be reused as the trace identifier.

## References

| Name | Type | Claris help |
|---|---|---|
| Set Error Capture | step | [set-error-capture](https://help.claris.com/en/pro-help/content/set-error-capture.html) |
| Perform Script | step | [perform-script](https://help.claris.com/en/pro-help/content/perform-script.html) |
| Perform Script on Server | step | [perform-script-on-server](https://help.claris.com/en/pro-help/content/perform-script-on-server.html) |
| Exit Script | step | [exit-script](https://help.claris.com/en/pro-help/content/exit-script.html) |
| Get ( LastError ) | function | [get-lasterror](https://help.claris.com/en/pro-help/content/get-lasterror.html) |
| Get ( ScriptResult ) | function | [get-scriptresult](https://help.claris.com/en/pro-help/content/get-scriptresult.html) |
