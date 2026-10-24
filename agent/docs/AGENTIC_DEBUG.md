# Agentic-fm Debug Script

## Purpose

FileMaker script execution is opaque to the agent — the agent cannot trigger scripts or observe runtime state directly. The **Agentic-fm Debug** script bridges this gap by writing runtime debug output to `agent/debug/output.json`, a file the agent can read directly without the developer needing to copy/paste anything.

## How it works

1. The failing script (or a temporary modification of it) calls **Agentic-fm Debug** via `Perform Script`, passing a JSON payload as the script parameter
2. Agentic-fm Debug sends that payload to the companion server's `/debug` endpoint
3. The companion server writes `agent/debug/output.json`
4. The agent reads the file and analyzes the output

## Critical: `Get ( LastError )` resets the error state

`Get ( LastError )` is not a passive read — **it clears the error state as a side effect.** Once evaluated, `Get ( LastErrorLocation )` and `Get ( LastErrorDetail )` can no longer return data for that error. All three functions must be captured in a **single expression** within one `Set Variable` step. See `agent/docs/knowledge/error-data-capture.md` for the full explanation and test evidence.

Additionally, `Perform Script` resets `Get ( LastError )` to 0 when it successfully begins executing the subscript. This means the debug script's own `$errorContext` capture (see below) always sees `lastError = 0`. **Callers must capture error data before calling `Perform Script` and pass it as part of the JSON parameter.**

## Script design

The script accepts a single parameter: a JSON object with any keys the calling script wants to expose. It forwards that object to the companion server along with metadata (timestamp, calling script name).

**Script parameter format** (passed by the calling script):
```json
{
  "label": "optional description of where this debug point is",
  "vars": {
    "errData": { "lastError": 102, "lastErrorDetail": "", "lastErrorLocation": "MyScript\rSet Field\r6" },
    "exitCode": "1",
    "stderr": "",
    "stdout": "..."
  }
}
```

**Important**: The `errData` object above was captured by the **calling script** using the single-expression pattern (see Calling Convention below). It is the authoritative error data. The debug script's own `lastError`/`lastErrorLocation` fields in the output will always be 0/empty because `Perform Script` resets the error state.

**Agentic-fm Debug script steps (HR format):**
```
# PURPOSE: Write runtime debug state to agent/debug/output.json for agent inspection.
# Called by other scripts via Perform Script with a JSON parameter.
#
# $errorContext capture is a safety net for edge cases only (e.g., errors within
# the Perform Script step itself). Callers should NOT rely on it — Perform Script
# resets Get(LastError) to 0 before this script's first line runs. Error data
# must be captured by the caller and passed in the parameter's "vars" key.

# Capture caller's error state (safety net — usually 0 due to Perform Script reset)
Set Variable [ $errorContext ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;
    [ "lastErrorLocation" ; Get ( LastErrorLocation ) ; JSONString ]
) ]

Set Variable [ $param ; Get ( ScriptParameter ) ]

Set Variable [ $payload ; JSONSetElement ( "{}" ;
    [ "label" ; JSONGetElement ( $param ; "label" ) ; JSONString ] ;
    [ "vars" ; JSONGetElement ( $param ; "vars" ) ; JSONRaw ] ;
    [ "timestamp" ; Get ( CurrentTimestamp ) ; JSONString ] ;
    [ "lastError" ; JSONGetElement ( $errorContext ; "lastError" ) ; JSONNumber ] ;
    [ "lastErrorLocation" ; JSONGetElement ( $errorContext ; "lastErrorLocation" ) ; JSONString ]
) ]

Insert from URL [ Verify SSL Certificates: OFF ; With dialog: OFF ; Target: $response ;
    "http://127.0.0.1:8765/debug" ;
    "-X POST -H \"Content-Type: application/json\" -d " & Quote ( $payload ) ]

If [ Get ( LastError ) ≠ 0 ]
    Show Custom Dialog [ "Agentic-fm Debug" ; "Companion server not running. Start it with:¶¶python3 agent/scripts/companion_server.py" ]
End If
```

## Calling convention: how to instrument a script

Error data must be captured **in the calling script** before `Perform Script`. Use this pattern:

```
# After the step that might fail:
# Capture ALL error data in ONE expression — Get(LastError) resets the error state
Set Variable [ $errData ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;
    [ "lastErrorDetail" ; Get ( LastErrorDetail ) ; JSONString ] ;
    [ "lastErrorLocation" ; Get ( LastErrorLocation ) ; JSONString ]
) ]
Perform Script [ "Agentic-fm Debug" ; Parameter: JSONSetElement ( "{}" ;
    [ "label" ; "after the risky step" ; JSONString ] ;
    [ "vars"  ; JSONSetElement ( "{}" ;
        [ "errData"  ; $errData  ; JSONRaw ] ;
        [ "myVar"    ; $myVar    ; JSONString ] ;
        [ "otherVar" ; $otherVar ; JSONString ]
    ) ; JSONRaw ]
) ]
```

### Interpreting the output

The output in `agent/debug/output.json` contains two sources of error data:
- **`vars.errData`** — captured by the calling script. **This is the authoritative error data.** Use this for diagnosis.
- **Top-level `lastError`/`lastErrorLocation`** — captured by the debug script itself. Always 0/empty because `Perform Script` resets the error state. Kept as a safety net for edge cases.

## Get ( LastErrorLocation ) and line numbers

`Get ( LastErrorLocation )` (added in FM 19.6.1) returns the script name, step name, and line number of the last error in the format `"ScriptName\rStepName\rLineNumber"` (carriage-return separated — `\r` / `&#xD;` / `Char(13)`).

**It works correctly** but only when captured in the same expression as `Get ( LastError )`. If captured in a separate step after `Get ( LastError )`, it returns empty because the error state has already been cleared.

**When a real error occurred:** capture `$errData` immediately after the failing step using the single-expression pattern above.

**When no error occurred but you need the current line number:** Force a harmless error, then capture immediately in one expression:

```
Set Error Capture [ On ]
Set Field []   # error 102 — no field specified
# Capture ALL error data in ONE expression immediately
Set Variable [ $errData ; JSONSetElement ( "{}" ;
    [ "lastError" ; Get ( LastError ) ; JSONNumber ] ;
    [ "lastErrorDetail" ; Get ( LastErrorDetail ) ; JSONString ] ;
    [ "lastErrorLocation" ; Get ( LastErrorLocation ) ; JSONString ]
) ]
Perform Script [ "Agentic-fm Debug" ; Parameter: JSONSetElement ( "{}" ;
    [ "label" ; "forced error for line number" ; JSONString ] ;
    [ "vars"  ; JSONSetElement ( "{}" ;
        [ "errData" ; $errData ; JSONRaw ]
    ) ; JSONRaw ]
) ]
Set Error Capture [ Off ]
```

The `$errData.lastErrorLocation` will contain the line number of the `Set Field []` step.

## Companion server endpoint

Add a `/debug` endpoint to `companion_server.py` that writes the received JSON to `agent/debug/output.json`:

```python
elif self.path == "/debug":
    self._handle_debug()
```

```python
def _handle_debug(self):
    try:
        body = self._read_body()
        payload = json.loads(body)
    except (ValueError, OSError) as exc:
        self._send_json({"success": False, "error": str(exc)}, status=400)
        return

    debug_dir = os.path.join(os.path.dirname(__file__), "..", "debug")
    os.makedirs(debug_dir, exist_ok=True)
    output_path = os.path.join(debug_dir, "output.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    log.info("Debug output written to agent/debug/output.json")
    self._send_json({"success": True, "path": output_path})
```

## Using $$DEBUG as a quick alternative

For a one-off diagnostic without creating the Agentic-fm Debug script, collect state into a `$$DEBUG` global:

```filemaker
Set Variable [ $$DEBUG ; JSONSetElement ( "{}" ;
    [ "exitCode" ; $exitCode ; JSONString ] ;
    [ "stderr"   ; $stderr   ; JSONString ] ;
    [ "stdout"   ; $stdout   ; JSONString ]
) ]
```

Then retrieve it from the Data Viewer (Tools > Data Viewer) and paste the JSON value to the agent. This is less convenient than the file-write approach but requires no script or server changes.

## Agent workflow

When the agent needs runtime debug information:

1. The agent uses the `fm-debug` skill (`agent/skills/fm-debug/SKILL.md`)
2. The skill instructs the developer to run the appropriate script
3. Once the developer confirms, the agent reads `agent/debug/output.json` directly
4. The agent analyzes the output and proposes a fix

The agent cannot trigger FileMaker scripts. The developer must always run them manually.
