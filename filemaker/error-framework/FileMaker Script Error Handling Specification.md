# FileMaker Script Error Handling

For concise, mandatory rules used while generating or refactoring scripts, see
[`error-framework.md`](../agent/docs/knowledge/error-framework.md). This
document is the canonical human-readable design; the linked document is its
agent-executable interpretation.

## Purpose

This framework standardizes script responses, application-error propagation,
logging, traceability, and future optional user dialogs. A script always
defines its own application error. A native FileMaker error is technical
evidence for that error, not the error returned to its parent.

The response carries a small, stable error object. The logger receives the
same error enriched with record context, execution environment, trace,
parameter, and timestamps.

## Standard script variables

The following script-local variables are reserved private framework state. A
calling script does not assign or read them directly; it uses the framework
custom-function contracts and `*.Get` functions instead:

```text
$_data          Data returned in the response.
$_error         Complete, log-ready error made by the current script.
$_FMerror       Native FileMaker error object.
$_context       Dynamic context passed to Error.Make.
$_params        Incoming script parameter.
$_trace         Trace object for this script execution.
$_child_params  Parameter for a child script.
$_child_result  Complete response captured from a child script.
$_child_error   Error object read from a child response.
$_child_data    Data object read from a child response.
```

## Native FileMaker errors

`FMError.Set` captures and returns this object, while setting `$_FMerror` as
a side effect:

```json
{ "code": 301, "detail": "…", "line": 42, "step": "Set Field" }
```

It must be evaluated after every relevant error-prone FileMaker script step,
before another executable script step can replace native error state. Comments
and blank-comment steps may appear between the risky step and `FMError.Set`.
Internally, `FMError.Set` captures `Get ( LastError )`,
`Get ( LastErrorDetail )`, and `Get ( LastErrorLocation )` together in one
`JSONSetElement` expression. Framework scripts never call those native Get
functions directly.

```filemaker
Set Field [ Orders::Status ; $newStatus ]
# Contextual comment is permitted here.
Set Variable [ $r ; FMError.Set ]

If [ FMError.GetCode ≠ 0 ]
	# Make this script's own application error.
End If
```

`$r` is deliberately disposable: `FMError.Set` itself owns `$_FMerror`.
When a native error is deliberately handled without making an application
error, clear it with `Set Variable [ $r ; FMError.Clear ]` before later work.

Functions in this group are `FMError.Set`, `FMError.Get`, `FMError.GetCode`,
and `FMError.Clear`.

## Response error

Every application error returned to a parent uses this stable shape:

```json
{
  "errorID": "K7X4P9",
  "code": "ORDER_STATUS_UPDATE_FAILED",
  "message": "Order status could not be updated.",
  "userMessage": "The order could not be updated.",
  "context": {
    "orderID": "ORD-1001",
    "targetStatus": "Approved"
  },
  "fmError": {
    "code": 301,
    "detail": "…",
    "line": 42,
    "step": "Set Field"
  }
}
```

`errorID` is a required human-reportable identifier made by `Error.Make`,
normally through `ShortId ( lengthId )`. Each failing layer creates its own
error ID. `code` is a stable application-defined value used by parent scripts.
`message` is developer-facing. `userMessage` is optional and never means a
dialog should be shown automatically. `context` contains only dynamic facts
needed to understand this particular failure. `fmError` is `{}` where there is
no native cause.

## Trace object

One root execution owns one UUID `traceID`; all children retain it. Every
script appends its own name to `scriptPath`, root first.

```json
{
  "traceID": "550e8400-e29b-41d4-a716-446655440000",
  "scriptPath": ["Orders_Process", "Orders_UpdateStatus"]
}
```

`Trace.Init` builds or continues this object and sets `$_trace`; `Trace.Get`
returns it. Trace is execution context, not response-error data. `Param.Make`
places it under the reserved `trace` key of child parameters; business payloads
must not construct that key themselves.

## Log-ready error

`Error.Make ( code ; message ; userMessage ; context )` sets `$_error` to:

```json
{
  "schemaVersion": 1,
  "error": { "…": "stable response error" },
  "recordContext": { "…": "current record and found set" },
  "environment": { "…": "current execution environment" },
  "trace": { "…": "current trace" },
  "parameter": { "…": "incoming script parameter" },
  "timestamp": "10-09-2026 21:22:31",
  "timestampUTCms": 63903669751432
}
```

`Error.Make` reads `FMError.Get`, `Environment.Get`, `RecordContext.Get`, and
`Trace.Get` internally. They are framework state and must never be supplied as
explicit parameters. The object must be logged unchanged:

```filemaker
Perform Script on Server [ "SYS_LogError" ; Parameter: Error.Get ]
```

Every script layer logs its own error. A parent does not nest its child's full
error as a `cause`; it makes a new error and may include the child error code
in its dynamic context.

## Environment and record context

`Environment.Get` captures current values including script, file, layout,
window, account, user, session identifier, application and host versions,
host and system network information, device and platform data, and transaction
and open-record state.

`RecordContext.Get` captures `Get ( LayoutTableName )`, `Get ( FoundCount )`,
`GetRecordIDsFromFoundSet ( 4 )`, `Get ( RecordID )`,
`Get ( ActiveRecordNumber )`, and `Get ( ActivePortalRowNumber )`. It records
the state when `Error.Make` runs, not when a later logger runs. Layout belongs
only in `environment`, never duplicated in `recordContext`.

## Child scripts

Build a child parameter through `Param.Make`, invoke the script, then capture
the result immediately with `Response.Capture`:

```filemaker
Perform Script [ "Orders_UpdateStatus" ; Parameter: Param.Make ( <business JSON payload> ) ]
Set Variable [ $r ; Response.Capture ]

If [ not Response.IsOK ]
	Set Variable [ $context ;
		JSONSetElement ( "{}" ;
			[ "childErrorCode" ; Response.GetErrorCode ; JSONString ]
		)
	]
	Set Variable [ $r ;
		Error.Make (
			"ORDER_PROCESSING_FAILED" ;
			"Order processing failed in the status update child script." ;
			"The order could not be processed." ;
			$context
		)
	]
End If
```

Do not read `Get ( ScriptResult )` directly. `Response.Capture` makes the
result durable in its internal child-response state before any later script
call can replace FileMaker's single script-result slot. The child's native error state is
irrelevant: its application error is returned in the response object. Use
`Response.GetData` only after a successful response.

## Response envelope

Every script has one final exit using `Response.Make ( $data )`:

```json
{ "schemaVersion": 1, "ok": false, "data": "", "error": {} }
```

When no error exists, `ok` is `true` and `error` is `{}`. `Response.Make`,
`Response.Capture`, `Response.Get`, `Response.IsOK`, `Response.GetData`,
`Response.GetError`, `Response.GetErrorCode`, `Response.GetErrorMessage`, and
`Response.GetErrorUserMessage` form the response API.

## Required script skeleton

```filemaker
Allow User Abort [ Off ]
Set Error Capture [ On ]

Set Variable [ $params ; Get ( ScriptParameter ) ]
Set Variable [ $r ; Trace.Init ]
Set Variable [ $data ; "" ]
Set Variable [ $context ; "{}" ]

Loop
	# Validate; make and log an own error when required.
	Exit Loop If [ not IsEmpty ( Error.Get ) ]

	# Work; capture native errors immediately and make an own error when required.
	Exit Loop If [ not IsEmpty ( Error.Get ) ]

	# Call children; make an own error when a child response is not OK.
	Exit Loop If [ not IsEmpty ( Error.Get ) ]

	# Set $data on success.
	Exit Loop If [ True ]
End Loop

# Cleanup must never replace framework error state.
Exit Script [ Response.Make ( $data ) ]
```

Initialize child variables only where they are needed. `JSON.IsValid` must
validate externally supplied JSON before it is parsed or inserted as `JSONRaw`.
Use `{}` for an empty JSON object and `""` for an empty text value; do not use
JSON null solely to represent emptiness.

`Allow User Abort [ Off ]` and `Set Error Capture [ On ]` are the defaults for
framework scripts. A task prompt may explicitly override either setting. Native
error 401 is always captured through `FMError.Set`; whether it creates an
application error in the response depends on the script's business context.

## Non-negotiable rules for generated scripts

1. Treat the reserved framework variables as private state; access it only through the documented custom functions.
2. Capture the incoming parameter in a normal local variable and run `Trace.Init` directly afterward.
3. Make every application error with `Error.Make` and a stable own code.
4. Capture every relevant native error with `FMError.Set` before another executable step; comments are permitted in between.
5. Clear intentionally ignored native errors with `FMError.Clear`.
6. Log every own error with `Error.Get` without mutating framework state.
7. Use `Param.Make` for child calls and `Response.Capture` immediately after them; do not inspect native child errors.
8. Never automatically show a `userMessage`.
9. Use no nested `cause` objects.
10. Use one final `Exit Script [ Response.Make ( $data ) ]`.
