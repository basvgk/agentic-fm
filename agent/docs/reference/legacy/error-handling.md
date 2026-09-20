# Error Handling

**NOTE:** Items marked with **(step)** are script steps. Items marked with **(function)** are calculation functions used inside expressions. This distinction matters: script steps become `<Step>` elements in fmxmlsnippet output, while functions appear inside `<Calculation><![CDATA[...]]></Calculation>` blocks.

## The Critical Constraint: `Get ( LastError )` Resets After Every Step

`Get ( LastError )` **(function)** returns the error code from the most recently executed script step. This is not a persistent error object — it is cleared and replaced after **every** step, including steps that succeed.

This means error checking must happen **immediately** after the step that might fail. Any intervening step — even a harmless `Set Variable` — overwrites the error code with its own result (typically 0).

```
#// Correct — capture immediately after the risky step
Perform Find [ Restore ]
Set Variable [ $error ; Value: Get ( LastError ) ]

#// Wrong — the Set Variable call has already replaced Get ( LastError ) by the time it is read
Perform Find [ Restore ]
Set Variable [ $someOtherThing ; Value: "x" ]
Set Variable [ $error ; Value: Get ( LastError ) ]   ← this is $someOtherThing's error, not Perform Find's
```

Always follow this pattern:

```
<risky step>
Set Variable [ $error ; Value: Get ( LastError ) ]
Exit Loop If [ $error ≠ 0 ]
```

### Capturing full error data (error + location + detail)

`Get ( LastError )` also resets the error state for its companion functions `Get ( LastErrorLocation )` and `Get ( LastErrorDetail )`. If you need location or detail data alongside the error code, all three must be captured in a **single expression** — see `agent/docs/knowledge/error-data-capture.md` for the full pattern and rationale.

## Script Header Steps for Server-Side Scripts

Two steps should appear at the top of every script that runs on FileMaker Server or in a background context:

### `Set Error Capture [ On ]` **(step)**

Suppresses FileMaker's built-in error dialogs. Without this, a runtime error on the server produces a dialog that no one can see or dismiss, hanging the script indefinitely. On a desktop client, it suppresses the dialog but still allows the script to handle the error programmatically.

### `Allow User Abort [ Off ]` **(step)**

Prevents the user from pressing Escape to cancel the script. On the server there is no user, but this step also prevents the server runtime from treating certain interruptions as abort signals. On a desktop client it prevents the user from cancelling a long-running script at an inopportune moment.

Always pair these two steps at the start of any script that runs server-side, performs data modification, or must complete atomically:

```
Allow User Abort [ Off ]
Set Error Capture [ On ]
```

The order matters only as a convention — both should be present before the first data-modifying step.

## Core Error-Checking Pattern

```
Allow User Abort [ Off ]
Set Error Capture [ On ]

Loop
  #// Guard: validate inputs before doing any work
  Exit Loop If [ IsEmpty ( Get ( ScriptParameter ) ) ]

  #// Risky step — check immediately
  Perform Find [ Restore ]
  Set Variable [ $error ; Value: Get ( LastError ) ]
  Exit Loop If [ $error ≠ 0 ]

  #// Another risky step
  Set Field [ Table::status ; "Active" ]
  Set Variable [ $error ; Value: Get ( LastError ) ]
  Exit Loop If [ $error ≠ 0 ]

  Set Variable [ $success ; Value: True ]
  Exit Loop If [ True ]
End Loop

If [ $success ]
  Commit Records/Requests [ With dialog: Off ]
Else
  Revert Record/Request [ With dialog: Off ]
  #// Log or surface $error here
End If
```

The `Loop`/`End Loop` structure is FileMaker's idiomatic try/catch equivalent. See `agent/docs/knowledge/single-pass-loop.md` for the full pattern and rationale.

## Common Error Codes

Not all non-zero error codes represent failures. Some are expected outcomes that scripts must distinguish:

| Code | Meaning | Common context |
| ---- | ------- | -------------- |
| 0    | No error | Success |
| 1    | User cancelled | `Perform Find` when user presses Escape |
| 9    | Insufficient privileges | Security restriction on a step |
| 112  | Window not found | `Select Window` targeting a non-existent window |
| 301  | Record locked by another user | `Open Record/Request`, `Set Field` on a locked record |
| 401  | No records match the find request | `Perform Find` with no matching records |
| 500  | Date value does not meet validation criteria | General field validation failure |
| 501  | Minimum number of characters not met | Field validation |
| 502  | Maximum number of characters exceeded | Field validation |
| 503  | Value in field is not within the range specified | Field validation |
| 504  | Value in field failed "of type" validation | Field validation |
| 505  | Invalid value entered in Find mode | Find request with an invalid search value |
| 802  | Unable to open file | File path not found or inaccessible |

Error 401 (no records found) deserves special attention: it is a common, expected outcome of `Perform Find` **(step)** and is almost never a script-terminating failure. Handle it explicitly rather than treating all non-zero errors identically:

```
Perform Find [ Restore ]
Set Variable [ $error ; Value: Get ( LastError ) ]
If [ $error = 401 ]
  #// No records — this is a valid outcome, handle gracefully
  Exit Script [ Result: JSONSetElement ( "{}" ; "count" ; 0 ; JSONNumber ) ]
Else If [ $error ≠ 0 ]
  #// Genuine error
  Exit Loop If [ True ]
End If
```

## OnFirstWindowOpen Scripts and Server Guard

When creating or modifying an `OnFirstWindowOpen` script (a startup script triggered by the file open event), consider whether it should exit immediately if running on FileMaker Server. Server-side file opens (e.g., from scheduled scripts or Data API connections) do not need client-side startup logic such as setting UI formats, opening card windows, or navigating to a home layout.

A standard guard pattern at the top of a startup script:

```
Set Error Capture [ On ]
Allow User Abort [ Off ]
Set Use System Formats [ On ]
#
If [ RunningOnServer ]
  Exit Script [ Result: "" ]
End If
```

`RunningOnServer` is a common custom function defined as:

```
LeftWords ( Get ( ApplicationVersion ) ; 1 ) = "Server"
```

It returns `True` when the script is executing on FileMaker Server and `False` on a desktop client.

**Agent guidance:** When composing or reviewing a startup script, ask whether a server guard is appropriate. If the script performs any client-only work (UI navigation, system format configuration, window management), a server guard should appear near the top — after `Set Error Capture [ On ]` and `Allow User Abort [ Off ]` but before any client-specific steps. Verify that a `RunningOnServer` custom function exists in the solution before referencing it; if it does not, the equivalent inline calculation is `LeftWords ( Get ( ApplicationVersion ) ; 1 ) = "Server"`.

## FileMaker Server vs FileMaker Pro Differences

Scripts that run on FileMaker Server (via `Perform Script on Server` **(step)**, scheduled scripts, or Data API triggers) have significant behavioral differences from scripts run on a desktop client:

- **No UI.** There are no dialogs, alerts, or layout interactions. Any step that would show a dialog (e.g., `Show Custom Dialog`, an unhandled error dialog) either silently skips or hangs.
- **`Set Error Capture [ On ]` is mandatory** on the server. Without it, an unhandled error produces an irrecoverable hang.
- **`Allow User Abort [ Off ]` is mandatory** on the server. Without it, the server may terminate the script prematurely under certain conditions.
- **No clipboard.** Steps that interact with the clipboard (`Copy`, `Paste`, `Set Field` from clipboard) do not function on the server.
- **No interactive finds.** `Perform Find` with `Pause` will not pause; it will execute immediately with whatever find requests are stored.
- Layout-dependent steps (`Go to Field`, `Go to Object`, `Set Next Serial Value` via UI) behave differently or fail silently on the server. Script steps that do not require a layout context are always preferred for server-side scripts.

## References

| Name                   | Type     | Local doc                                                                    | Claris help                                                                                                   |
| ---------------------- | -------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Set Error Capture      | step     | `agent/docs/filemaker/script-steps/set-error-capture.md`                     | [set-error-capture](https://help.claris.com/en/pro-help/content/set-error-capture.html)                       |
| Allow User Abort       | step     | `agent/docs/filemaker/script-steps/allow-user-abort.md`                      | [allow-user-abort](https://help.claris.com/en/pro-help/content/allow-user-abort.html)                         |
| Set Variable           | step     | `agent/docs/filemaker/script-steps/set-variable.md`                          | [set-variable](https://help.claris.com/en/pro-help/content/set-variable.html)                                 |
| Exit Loop If           | step     | `agent/docs/filemaker/script-steps/exit-loop-if.md`                          | [exit-loop-if](https://help.claris.com/en/pro-help/content/exit-loop-if.html)                                 |
| Perform Find           | step     | `agent/docs/filemaker/script-steps/perform-find.md`                          | [perform-find](https://help.claris.com/en/pro-help/content/perform-find.html)                                 |
| Perform Script on Server | step   | `agent/docs/filemaker/script-steps/perform-script-on-server.md`              | [perform-script-on-server](https://help.claris.com/en/pro-help/content/perform-script-on-server.html)         |
| Commit Records/Requests | step    | `agent/docs/filemaker/script-steps/commit-records-requests.md`               | [commit-records-requests](https://help.claris.com/en/pro-help/content/commit-records-requests.html)           |
| Revert Record/Request  | step     | `agent/docs/filemaker/script-steps/revert-record-request.md`                 | [revert-record-request](https://help.claris.com/en/pro-help/content/revert-record-request.html)               |
| Get ( LastError )      | function | `agent/docs/filemaker/functions/get/get-lasterror.md`                        | [get-lasterror](https://help.claris.com/en/pro-help/content/get-lasterror.html)                               |
| Get ( LastErrorLocation ) | function | `agent/docs/filemaker/functions/get/get-lasterrorlocation.md`             | [get-lasterrorlocation](https://help.claris.com/en/pro-help/content/get-lasterrorlocation.html)               |
| Get ( LastErrorDetail ) | function | `agent/docs/filemaker/functions/get/get-lasterrordetail.md`                | [get-lasterrordetail](https://help.claris.com/en/pro-help/content/get-lasterrordetail.html)                   |
