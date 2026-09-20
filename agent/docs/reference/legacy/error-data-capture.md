# Error Data Capture

**NOTE:** Items marked with **(step)** are script steps. Items marked with **(function)** are calculation functions used inside expressions.

## The Problem: `Get ( LastError )` Resets the Error State

`Get ( LastError )` **(function)** is not a passive read — **evaluating it clears the error state as a side effect.** Once `Get ( LastError )` has been evaluated, `Get ( LastErrorLocation )` **(function)** and `Get ( LastErrorDetail )` **(function)** can no longer return data for that error — they return empty strings.

This is distinct from the step-level timing constraint documented in `error-handling.md` (where a *successful step* clears `Get ( LastError )`). Here, the function call itself — within the *same expression context* — clears state for the companion functions. Even within a single `Set Variable` **(step)**, the order of evaluation matters when the three functions are in separate sub-expressions.

However, when all three functions appear in a **single `JSONSetElement` expression**, FileMaker evaluates all arguments before any side effects propagate. This makes `JSONSetElement` the reliable capture mechanism.

## The Pattern: Single-Expression Capture

All error data must be captured in **one `Set Variable` step** using a single `JSONSetElement` call:

```
Set Variable [ $errData ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;
    [ "lastErrorDetail" ; Get ( LastErrorDetail ) ; JSONString ] ;
    [ "lastErrorLocation" ; Get ( LastErrorLocation ) ; JSONString ]
) ]
```

This reliably captures all three values. `Get ( LastErrorLocation )` returns the script name, step name, and line number in the format `"ScriptName\rStepName\rLineNumber"` (carriage-return separated).

### Wrong: separate steps

```
Set Variable [ $err ; Get ( LastError ) ]           # captures the error code
Set Variable [ $loc ; Get ( LastErrorLocation ) ]   # ALWAYS EMPTY — error state already cleared
Set Variable [ $det ; Get ( LastErrorDetail ) ]     # ALWAYS EMPTY
```

The first `Set Variable` evaluates `Get ( LastError )`, which clears the error state. The subsequent steps see no error.

## Timing: capture immediately after the risky step

The single-expression capture must be the **very next step** after the step that might fail. Any intervening step — even a comment step — overwrites the error state:

```
# Correct
Perform Find [ Restore ]
Set Variable [ $errData ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;
    [ "lastErrorDetail" ; Get ( LastErrorDetail ) ; JSONString ] ;
    [ "lastErrorLocation" ; Get ( LastErrorLocation ) ; JSONString ]
) ]

# Wrong — Set Variable cleared the error before the capture
Perform Find [ Restore ]
Set Variable [ $found ; Get ( FoundCount ) ]
Set Variable [ $errData ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;   # ← this is $found's error (0), not Perform Find's
    ...
) ]
```

## Cross-script boundary: `Perform Script` resets the error

`Perform Script` **(step)** resets `Get ( LastError )` to 0 when it successfully begins executing the subscript. This means a subscript (like Agentic-fm Debug) cannot observe the caller's error state — it is already cleared by the time the subscript's first line runs.

**Consequence**: error data must be captured in the **calling** script and passed as a parameter to any subscript that needs it.

```
# In the calling script — capture BEFORE Perform Script
Set Variable [ $errData ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;
    [ "lastErrorDetail" ; Get ( LastErrorDetail ) ; JSONString ] ;
    [ "lastErrorLocation" ; Get ( LastErrorLocation ) ; JSONString ]
) ]
# Pass captured error data as part of the parameter
Perform Script [ "Agentic-fm Debug" ; Parameter: JSONSetElement ( "{}" ;
    [ "label" ; "after risky step" ; JSONString ] ;
    [ "vars"  ; JSONSetElement ( "{}" ;
        [ "errData" ; $errData ; JSONRaw ]
    ) ; JSONRaw ]
) ]
```

## Forced error for line number capture

When no real error has occurred but you need the current line number (e.g., for a debug checkpoint), force a harmless error and capture immediately:

```
Set Error Capture [ On ]
Set Field []   # error 102 — no field specified
Set Variable [ $errData ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;
    [ "lastErrorDetail" ; Get ( LastErrorDetail ) ; JSONString ] ;
    [ "lastErrorLocation" ; Get ( LastErrorLocation ) ; JSONString ]
) ]
Set Error Capture [ Off ]
```

`$errData.lastErrorLocation` will contain the line number of the `Set Field` step: `"ScriptName\rSet Field\rN"`.

## `Get ( LastErrorLocation )` format

Format: `"ScriptName\rStepName\rLineNumber"` — three values separated by carriage returns (`\r` / `Char(13)` / `¶`).

Parse with `GetValue`:

```
Let ( [
    ~loc    = JSONGetElement ( $errData ; "lastErrorLocation" ) ;
    ~script = GetValue ( ~loc ; 1 ) ;
    ~step   = GetValue ( ~loc ; 2 ) ;
    ~line   = GetValue ( ~loc ; 3 )
] ;
    "Script: " & ~script & ", Step: " & ~step & ", Line: " & ~line
)
```

Added in FM 19.6.1. Confirmed working in FM Pro 22.0.4. Returns empty string when no error has occurred (or when the error state has been cleared by a prior `Get ( LastError )` call).

## `Get ( LastErrorDetail )` behavior

`Get ( LastErrorDetail )` **(function)** was empty for all error types tested (102, 104, 105). It may only populate for specific error categories such as ODBC errors, validation failures, or security violations. Do not rely on it as a primary diagnostic signal — use `lastError` and `lastErrorLocation` instead.

## Test evidence

These findings were confirmed by autonomous testing on 2026-03-22 against FM Pro 22.0.4 / FMS 21.1.5. Test details and raw output are in `plans/DEBUG_FINDINGS.md`.

**Tested error types** (all captured correctly with single-expression pattern):

| Error | Code | lastErrorLocation |
|---|---|---|
| Set Field (no field target) | 102 | `ScriptName\rSet Field\rN` |
| Perform Script (script not found) | 104 | `ScriptName\rPerform Script\rN` |
| Go to Layout (layout not found) | 105 | `ScriptName\rGo to Layout\rN` |

## References

| Name | Type | Local doc | Claris help |
|------|------|-----------|-------------|
| Set Variable | step | `agent/docs/filemaker/script-steps/set-variable.md` | [set-variable](https://help.claris.com/en/pro-help/content/set-variable.html) |
| Set Error Capture | step | `agent/docs/filemaker/script-steps/set-error-capture.md` | [set-error-capture](https://help.claris.com/en/pro-help/content/set-error-capture.html) |
| Set Field | step | `agent/docs/filemaker/script-steps/set-field.md` | [set-field](https://help.claris.com/en/pro-help/content/set-field.html) |
| Perform Script | step | `agent/docs/filemaker/script-steps/perform-script.md` | [perform-script](https://help.claris.com/en/pro-help/content/perform-script.html) |
| Get ( LastError ) | function | `agent/docs/filemaker/functions/get/get-lasterror.md` | [get-lasterror](https://help.claris.com/en/pro-help/content/get-lasterror.html) |
| Get ( LastErrorLocation ) | function | `agent/docs/filemaker/functions/get/get-lasterrorlocation.md` | [get-lasterrorlocation](https://help.claris.com/en/pro-help/content/get-lasterrorlocation.html) |
| Get ( LastErrorDetail ) | function | `agent/docs/filemaker/functions/get/get-lasterrordetail.md` | [get-lasterrordetail](https://help.claris.com/en/pro-help/content/get-lasterrordetail.html) |
| JSONSetElement | function | `agent/docs/filemaker/functions/json/jsonsetelement.md` | [jsonsetelement](https://help.claris.com/en/pro-help/content/jsonsetelement.html) |
| GetValue | function | `agent/docs/filemaker/functions/text/getvalue.md` | [getvalue](https://help.claris.com/en/pro-help/content/getvalue.html) |
