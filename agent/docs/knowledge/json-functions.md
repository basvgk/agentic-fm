# JSON Function Patterns

Practical guidance for using FileMaker's JSON functions in script calculations, covering common gotchas and correct patterns.

---

## JSONGetElementType — valid return constants

`JSONGetElementType ( json ; keyOrIndex )` returns an integer indicating the type of the referenced element:

| Constant | Value | Meaning |
|---|---|---|
| `JSONString` | 1 | String value |
| `JSONNumber` | 2 | Number value |
| `JSONObject` | 3 | Object (`{}`) |
| `JSONArray` | 4 | Array (`[]`) |
| `JSONBoolean` | 5 | Boolean (`true`/`false`) |
| `JSONNull` | 6 | Null (`null`) |
| *(none)* | 0 | Key not found or JSON is invalid |

**`JSONUndefined` and `JSONMissing` do not exist as FileMaker constants.** Do not use them.

When a key is absent or the JSON is malformed, the function returns `0` — a bare integer with no named constant.

---

## Checking whether a key exists

### Positive check — enter a branch when a key is present

Test for the expected type directly. This is the idiomatic pattern:

```
// Enter server mode only if task key exists and is a string
If [ JSONGetElementType ( $input ; "task" ) = JSONString ]
  // ... server mode steps ...
  Exit Script [ result ]
End If
// falls through to interactive mode
```

### Negative check — guard/bail when a key is missing

Use `not` on the return value, since `0` is falsy:

```
// Exit with error if required key is absent
If [ not JSONGetElementType ( $input ; "layout" ) ]
  Exit Script [ JSONSetElement ( "{}" ;
    [ "success" ; False ; JSONBoolean ] ;
    [ "error" ; "Missing required key: layout" ; JSONString ]
  ) ]
End If
```

Alternatively, compare against `0` explicitly if that reads more clearly:

```
If [ JSONGetElementType ( $input ; "layout" ) = 0 ]
```

## Empty values versus JSON false and zero

In FileMaker, `IsEmpty ( value )` is false for the numeric value `0` and the
boolean value `False`; both are present values. Do not use a truthiness test
when a JSON response may legitimately contain `0` or `False`.

```filemaker
// Correct: 0 and False are retained as non-empty child-response data
If [ not IsEmpty ( Response.GetData ) ]
	// Attach the data to the log.
End If
```

Use `JSONGetElementType ( json ; key )` when the distinction between a missing
key (`0`) and a present, empty JSON string (`JSONString`) matters.

### Do NOT use

```
// Wrong — JSONUndefined does not exist
If [ JSONGetElementType ( $input ; "task" ) ≠ JSONUndefined ]

// Wrong — JSONMissing does not exist
If [ JSONGetElementType ( $input ; "task" ) = JSONMissing ]
```

---

## Checking the type of the root element

Pass an empty string as the key to check the type of the root value:

```
// Guard: input must be a JSON object
If [ JSONGetElementType ( $input ; "" ) ≠ JSONObject ]
  Exit Script [ JSONSetElement ( "{}" ;
    [ "success" ; False ; JSONBoolean ] ;
    [ "error" ; "Invalid parameter: expected JSON object" ; JSONString ]
  ) ]
End If
```

This is the pattern used in `AGFMScriptBridge` to validate that the parameter is an object before extracting keys.

---

## References

| Name | Type | Local doc | Claris help |
|------|------|-----------|-------------|
| JSONGetElementType | function | `agent/docs/filemaker/functions/json/jsongetelementtype.md` | [jsongetelementtype](https://help.claris.com/en/pro-help/content/jsongetelementtype.html) |
| JSONGetElement | function | `agent/docs/filemaker/functions/json/jongetelement.md` | [jsongetelement](https://help.claris.com/en/pro-help/content/jsongetelement.html) |
| JSONSetElement | function | `agent/docs/filemaker/functions/json/jsonsetelement.md` | [jsonsetelement](https://help.claris.com/en/pro-help/content/jsonsetelement.html) |
