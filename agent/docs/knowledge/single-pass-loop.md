# Single-Pass Loop (Try/Catch Equivalent)

## Project error-framework override

When `PROJECT.md` activates the project error framework, use the single-pass
loop structure in this article, but do not use its direct `Get ( LastError )`
examples. Framework scripts capture native errors through `FMError.Set` and
use `$_error` to determine their loop exits, as specified in
`error-framework.md`. The examples below remain generic reference patterns for
solutions without the framework.

**NOTE:** Items marked with **(step)** are script steps. Items marked with **(function)** are calculation functions used inside expressions. This distinction matters: script steps become `<Step>` elements in fmxmlsnippet output, while functions appear inside `<Calculation><![CDATA[...]]></Calculation>` blocks.

## Why This Pattern Exists

FileMaker has no native try/catch/finally construct. There is no mechanism to jump to an error handler block or guarantee cleanup code runs after a failure. The single-pass loop fills this gap. It is FileMaker's idiomatic way to write error-aware, early-exit script logic.

A `Loop` **(step)** that is guaranteed to run exactly once — because every branch ends with an `Exit Loop If` **(step)** or the loop ends with `Exit Loop If [ True ]` — provides:

- **Multiple exit points** at any point in the script body, analogous to `throw` in other languages
- **A guaranteed exit** at the end, analogous to `finally`
- **Shared cleanup** after the loop, which runs regardless of which exit was taken

## Pattern Structure

```
Loop
  #// MARK: Guard conditions
  Exit Loop If [ $condition1 ]           ← early exit on error/invalid state

  #// MARK: Main work
  Set Field [ Table::field ; $value ]
  Set Variable [ $error ; Value: Get ( LastError ) ]
  Exit Loop If [ $error ≠ 0 ]            ← exit on step failure

  Perform Script [ "Sub-task" ; ... ]
  Set Variable [ $error ; Value: Get ( LastError ) ]
  Exit Loop If [ $error ≠ 0 ]            ← exit on sub-script failure

  #// All work succeeded
  Set Variable [ $success ; Value: True ]

  Exit Loop If [ True ]                  ← guaranteed exit — REQUIRED
End Loop
```

The final `Exit Loop If [ True ]` is not optional. Without it, the loop repeats indefinitely. Every single-pass loop MUST end with this step.

## Passing Error State Out of the Loop

Variables set inside the loop remain in scope after the loop exits. The standard approach is to set a `$error` or `$success` variable before each exit, then branch on it after `End Loop`:

```
Loop
  Exit Loop If [ IsEmpty ( $requiredParam ) ]     ← $error stays 0, $success stays False

  #// ... do work ...

  Set Variable [ $error ; Value: Get ( LastError ) ]
  Exit Loop If [ $error ≠ 0 ]                     ← $error is non-zero

  Set Variable [ $success ; Value: True ]
  Exit Loop If [ True ]
End Loop

If [ $success ]
  #// post-success steps
Else
  #// error handling / user feedback
End If
```

When more detail is needed, capture the error code before exiting:

```
  Set Variable [ $error ; Value: Get ( LastError ) ]
  Set Variable [ $errorStep ; Value: "Perform Find" ]
  Exit Loop If [ $error ≠ 0 ]
```

## Multiple Exit Points for Different Conditions

Each `Exit Loop If` represents a distinct exit scenario. Add a descriptive comment above each one to document what it represents. This is far more readable than a deeply nested If/Else chain:

```
Loop
  #// Missing parameter — nothing to do
  Exit Loop If [ IsEmpty ( Get ( ScriptParameter ) ) ]

  #// Record locked by another user — cannot edit
  Set Variable [ $error ; Value: Get ( LastError ) ]
  Exit Loop If [ $error = 301 ]

  #// Validation failed — field rejected the value
  Set Variable [ $error ; Value: Get ( LastError ) ]
  Exit Loop If [ $error = 500 ]

  Set Variable [ $success ; Value: True ]
  Exit Loop If [ True ]
End Loop
```

## When NOT to Use This Pattern

The single-pass loop is not always necessary. Do not add it reflexively to every script:

- **Simple, non-critical scripts** — if a script has no error-sensitive steps and no meaningful recovery path, a plain sequence of steps is clearer
- **Read-only lookups** — scripts that only read data and have no side effects rarely need formal error handling
- **Already wrapped in an outer handler** — if a sub-script is always called from an error-handling parent, the sub-script itself may not need the full pattern

Reserve the single-pass loop for scripts that modify data, perform finds with meaningful no-records cases, or call external resources (scripts, APIs, file imports).

## The Inferior Alternative: Nested If/Else

A common mistake — especially for developers coming from other languages — is to nest `If` **(step)** and `Else If` **(step)** chains to handle each error condition:

```
#// Anti-pattern — avoid this
If [ Not IsEmpty ( $param ) ]
  Set Field [ ... ]
  If [ Get ( LastError ) = 0 ]
    Perform Script [ ... ]
    If [ Get ( LastError ) = 0 ]
      Set Variable [ $success ; Value: True ]
    End If
  End If
End If
```

Problems with this approach:
- Indentation grows with each check, making the script hard to read
- There is no guaranteed cleanup point — cleanup code must be duplicated in every branch
- Error state is implicit rather than explicit — the absence of success is ambiguous
- Adding a new error condition requires restructuring the nesting

The single-pass loop keeps the happy path linear and makes each exit condition an explicit, named event.

## References

| Name             | Type     | Local doc                                                           | Claris help                                                                                         |
| ---------------- | -------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Loop             | step     | `agent/docs/filemaker/script-steps/loop.md`                         | [loop](https://help.claris.com/en/pro-help/content/loop.html)                                       |
| End Loop         | step     | `agent/docs/filemaker/script-steps/end-loop.md`                     | [end-loop](https://help.claris.com/en/pro-help/content/end-loop.html)                               |
| Exit Loop If     | step     | `agent/docs/filemaker/script-steps/exit-loop-if.md`                 | [exit-loop-if](https://help.claris.com/en/pro-help/content/exit-loop-if.html)                       |
| If               | step     | `agent/docs/filemaker/script-steps/if.md`                           | [if](https://help.claris.com/en/pro-help/content/if.html)                                           |
| Set Variable     | step     | `agent/docs/filemaker/script-steps/set-variable.md`                 | [set-variable](https://help.claris.com/en/pro-help/content/set-variable.html)                       |
| Get ( LastError ) | function | `agent/docs/filemaker/functions/get/get-lasterror.md`              | [get-lasterror](https://help.claris.com/en/pro-help/content/get-lasterror.html)                     |
