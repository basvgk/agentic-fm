# Single-Pass Loop (Try/Catch Equivalent)

This article covers loop structure only. For script changes in a project with
an error framework, read [`error-framework.md`](error-framework.md) first.
That document defines which steps need error checks, how errors are captured,
and how the loop should respond to framework error state. Do not copy native
error-capture examples from other sources into a framework script.

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
  #// Guard conditions
  Exit Loop If [ IsEmpty ( $requiredValue ) ]

  #// Main work
  # Insert business logic and any required framework-based early exits here.

  Set Variable [ $success ; True ]
  Exit Loop If [ True ]
End Loop
```

The final `Exit Loop If [ True ]` is not optional. Without it, the loop repeats indefinitely. Every single-pass loop MUST end with this step.

## Passing Error State Out of the Loop

Variables set inside the loop remain in scope after it exits. Track business
success separately when the caller needs it. In a framework script, leave
failure state in the framework and use its documented check; do not copy native
error codes into a parallel `$error` variable.

Shared cleanup belongs after `End Loop`, where it runs for both normal and
early exits. Error logging and the final response follow the project's
framework rules.

## Multiple Exit Points for Different Conditions

Each `Exit Loop If` represents a distinct exit scenario. Add a descriptive comment above each one to document what it represents. This is far more readable than a deeply nested If/Else chain:

Use separate exits for separate outcomes, such as a missing required
parameter, an expected no-results condition, or an error recorded by the
framework. Give each exit a short comment explaining why the remaining work
must stop.

## When NOT to Use This Pattern

The single-pass loop is not always necessary. Do not add it reflexively to every script:

- **Simple, non-critical scripts** — if a script has no error-sensitive steps and no meaningful recovery path, a plain sequence of steps is clearer
- **Read-only lookups** — scripts that only read data and have no side effects rarely need formal error handling
- **Already wrapped in an outer handler** — if a sub-script is always called from an error-handling parent, the sub-script itself may not need the full pattern

Reserve the single-pass loop for scripts that modify data, perform finds with meaningful no-records cases, or call external resources (scripts, APIs, file imports).

## The Inferior Alternative: Nested If/Else

A common mistake — especially for developers coming from other languages — is to nest `If` **(step)** and `Else If` **(step)** chains to handle each error condition:

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
