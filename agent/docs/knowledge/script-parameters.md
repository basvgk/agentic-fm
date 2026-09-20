# Script Parameters and Results

## Project error-framework override

When `PROJECT.md` activates the project error framework, child-script callers
must use `Response.Capture` immediately after `Perform Script` rather than the
direct `Get ( ScriptResult )` examples below. The framework response object is
the child contract; native error state after the child call is irrelevant.

**NOTE:** Items marked with **(step)** are script steps. Items marked with **(function)** are calculation functions used inside expressions. This distinction matters: script steps become `<Step>` elements in fmxmlsnippet output, while functions appear inside `<Calculation><![CDATA[...]]></Calculation>` blocks.

## One Parameter, One Result

FileMaker scripts accept exactly **one** parameter and return exactly **one** result. There is no function signature with multiple named arguments — there is a single parameter slot and a single result slot. To pass or return multiple values, encode them as JSON.

## Passing Parameters

### `Get ( ScriptParameter )` **(function)**

Returns the parameter passed to the currently executing script. It is available anywhere within the script — unlike `Get ( LastError )`, it does not reset between steps.

The parameter is set by the calling step (`Perform Script`, `Perform Script on Server`, `New Window` with script, etc.) and is fixed for the duration of the script call. It cannot be changed mid-script.

### JSON convention for multiple values

Use `JSONSetElement` **(function)** to construct a JSON object when multiple values must be passed:

```
#// Caller
Set Variable [ $parameter ; Value:
    JSONSetElement ( "{}" ;
        [ "invoiceId" ; Invoices::id ; JSONNumber ] ;
        [ "mode" ; "email" ; JSONString ] ;
        [ "sendCopy" ; True ; JSONBoolean ]
    )
]
Perform Script [ "Process Invoice" ; Parameter: $parameter ]
```

---

```
#// Callee — at the top of "Process Invoice"
#// Parameter: { "invoiceId": <number>, "mode": <string>, "sendCopy": <boolean> }

Set Variable [ $parameters ; Value: Get ( ScriptParameter ) ]

Set Variable [ $invoiceId ; Value: JSONGetElement ( $parameters ; "invoiceId" ) ]
Set Variable [ $mode ; Value: JSONGetElement ( $parameters ; "mode" ) ]
Set Variable [ $sendCopy ; Value: JSONGetElement ( $parameters ; "sendCopy" ) ]
```

Always document the expected parameter structure in a comment at the top of any script that accepts parameters. This is the only "signature" the script has.

### Flat string parameters

A flat string is acceptable when only a single value is needed — for example, passing a record ID or a mode flag. Use JSON as soon as a second value is required. Do not invent delimiter-based encodings (e.g., `"123|email|1"`) — they are fragile and hard to extend.

## Returning Results

### `Exit Script [ Result: expression ]` **(step)**

Sets the result that the calling script will receive via `Get ( ScriptResult )`. Always use `Exit Script [ Result: ... ]` to return data — not global variables. This keeps data flow explicit and eliminates the global variable cleanup burden.

```
#// Return a simple value
Exit Script [ Result: $computedId ]

#// Return a JSON object with multiple values
Exit Script [ Result:
    JSONSetElement ( "{}" ;
        [ "success" ; $success    ; JSONBoolean ] ;
        [ "error"   ; $error      ; JSONNumber  ] ;
        [ "id"      ; $newId      ; JSONNumber  ]
    )
]
```

A script that exits normally (falls off the end without an `Exit Script` step) returns an empty result.

### `Get ( ScriptResult )` **(function)**

Returns the result from the most recently completed `Perform Script` **(step)** or `Perform Script on Server` **(step)** call. Like `Get ( LastError )`, this is cleared and replaced after every script call — including calls that return an empty result.

**Capture it immediately after `Perform Script`:**

```
Perform Script [ "Calculate Total" ; Parameter: $invoiceId ]
Set Variable [ $result ; Value: Get ( ScriptResult ) ]

#// Do not call any other script before reading the result
#// Any subsequent Perform Script call replaces $result
```

This is the most common mistake with `Get ( ScriptResult )`: calling another script (or a sub-script that internally calls scripts) before capturing the result.

## Calling Scripts by Reference, Not by Name

Always use the FileMaker script reference (id + name) when calling a script via `Perform Script`. Never construct a script name as a dynamic string and pass it to a variable-based call — FileMaker does not support calling scripts by a calculated name at runtime without using a plug-in or the `Perform Script by Name` **(step)** workaround.

Using the reference picker (which embeds the script ID in the XML) is preferred:

- The call is validated at design time
- Renaming the script updates the reference automatically
- Performance is marginally better — no name resolution at runtime

`Perform Script by Name` **(step)** is appropriate when the target script is genuinely dynamic (e.g., a routing table that selects a handler based on a type field), but it bypasses design-time validation and is harder to audit.

## Documenting Parameter Structure

Because FileMaker has no formal function signature, the parameter contract is invisible to anyone reading the script name. Always add a comment block at the top of scripts that accept parameters:

```
#// MARK: Parameters
#// Expects JSON: { "invoiceId": <number>, "mode": "email|print|save", "sendCopy": <boolean> }
#// Returns JSON: { "success": <boolean>, "error": <number> }
```

This convention is enforced by `agent/docs/CODING_CONVENTIONS.md`. Apply it to every script that uses `Get ( ScriptParameter )` or `Exit Script [ Result: ... ]`.

## References

| Name                     | Type     | Local doc                                                       | Claris help                                                                                           |
| ------------------------ | -------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Perform Script           | step     | `agent/docs/filemaker/script-steps/perform-script.md`           | [perform-script](https://help.claris.com/en/pro-help/content/perform-script.html)                     |
| Perform Script on Server | step     | `agent/docs/filemaker/script-steps/perform-script-on-server.md` | [perform-script-on-server](https://help.claris.com/en/pro-help/content/perform-script-on-server.html) |
| Perform Script by Name   | step     | `agent/docs/filemaker/script-steps/perform-script-by-name.md`   | [perform-script-by-name](https://help.claris.com/en/pro-help/content/perform-script-by-name.html)     |
| Exit Script              | step     | `agent/docs/filemaker/script-steps/exit-script.md`              | [exit-script](https://help.claris.com/en/pro-help/content/exit-script.html)                           |
| Get ( ScriptParameter )  | function | `agent/docs/filemaker/functions/get/get-scriptparameter.md`     | [get-scriptparameter](https://help.claris.com/en/pro-help/content/get-scriptparameter.html)           |
| Get ( ScriptResult )     | function | `agent/docs/filemaker/functions/get/get-scriptresult.md`        | [get-scriptresult](https://help.claris.com/en/pro-help/content/get-scriptresult.html)                 |
| JSONSetElement           | function | `agent/docs/filemaker/functions/json/jsonsetelement.md`         | [jsonsetelement](https://help.claris.com/en/pro-help/content/jsonsetelement.html)                     |
| JSONGetElement           | function | `agent/docs/filemaker/functions/json/jsongetelement.md`         | [jsongetelement](https://help.claris.com/en/pro-help/content/jsongetelement.html)                     |
