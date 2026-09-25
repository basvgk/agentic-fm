# Param.Make / Param.Payload test calculations

This test matrix covers JSON values, plain text, malformed input, reserved-key
isolation, invalid child parameters, and an end-to-end child call.

## Setup

Install `Param.Make`, `Param.Payload`, `Trace.Get`, and `JSON.IsValid`. For the
`Param.Make` cases, evaluate the shared assertion in Data Viewer before calling
`Trace.Init`; this makes the expected trace `{}`.

For `Param.Payload`, create a temporary script named `TEST_Param.Payload`:

```filemaker
Exit Script [ Param.Payload ]
```

Call it with each listed script parameter and inspect the script result.

## Shared Param.Make assertion

Replace the three marked assignments with a row from the table. `ok` must be
`true`.

```filemaker
Let (
[
	~input = /* CASE INPUT */ ;
	~expectedType = /* CASE JSON TYPE */ ;
	~expectedValue = /* CASE EXPECTED VALUE */ ;
	~actual = Param.Make ( ~input ) ;
	~actualType = JSONGetElementType ( ~actual ; "payload" ) ;
	~actualPayload = JSONGetElement ( ~actual ; "payload" ) ;
	~matchesValue =
		Case (
			~expectedType = JSONNull ; True ;
			~expectedType = JSONObject
			or ~expectedType = JSONArray ;
				JSONFormatElements ( ~actualPayload ) = JSONFormatElements ( ~expectedValue ) ;
			~actualPayload = ~expectedValue
		) ;
	~ok =
		JSONGetElementType ( ~actual ; "" ) = JSONObject
		and ~actualType = ~expectedType
		and JSONGetElementType ( ~actual ; "trace" ) = JSONObject
		and JSONFormatElements ( JSONGetElement ( ~actual ; "trace" ) ) = JSONFormatElements ( "{}" )
		and ~matchesValue
] ;

	JSONFormatElements (
		JSONSetElement ( "{}" ;
			[ "ok" ; ~ok ; JSONBoolean ] ;
			[ "actual" ; ~actual ; JSONRaw ] ;
			[ "actualPayloadType" ; ~actualType ; JSONNumber ] ;
			[ "actualPayload" ; ~actualPayload ; JSONString ]
		)
	)
)
```

## Param.Make cases

| # | Case | `~input` | `~expectedType` | `~expectedValue` |
|---|---|---|---|---|
| 1 | Flat object | `JSONSetElement ( "{}" ; [ "var1" ; "value1" ; JSONString ] ; [ "var2" ; "value2" ; JSONString ] )` | `JSONObject` | same as input |
| 2 | Empty object | `"{}"` | `JSONObject` | `"{}"` |
| 3 | Nested object | `JSONSetElement ( "{}" ; [ "customer.name" ; "Ada" ; JSONString ] ; [ "customer.active" ; True ; JSONBoolean ] )` | `JSONObject` | same as input |
| 4 | Business key named `trace` | `JSONSetElement ( "{}" ; [ "trace.source" ; "business" ; JSONString ] )` | `JSONObject` | same as input; also check `JSONGetElement ( ~actual ; "payload.trace.source" ) = "business"` |
| 5 | Nonempty array | `"[1,2,{\"name\":\"three\"}]"` | `JSONArray` | same as input |
| 6 | Empty array | `"[]"` | `JSONArray` | `"[]"` |
| 7 | Number | `42` | `JSONNumber` | `42` |
| 8 | Boolean true | `True` | `JSONBoolean` | `True` |
| 9 | Boolean false | `False` | `JSONBoolean` | `False` |
| 10 | JSON null | `"null"` | `JSONNull` | `""` |
| 11 | JSON string | `"\"Hello JSON\""` | `JSONString` | `"Hello JSON"` |
| 12 | Plain text | `"Hello plain text"` | `JSONString` | `"Hello plain text"` |
| 13 | Empty text | `""` | `JSONString` | `""` |
| 14 | Whitespace text | `"  "` | `JSONString` | `"  "` |
| 15 | Malformed JSON | `"{\"unclosed\":"` | `JSONString` | same as input |
| 16 | Unicode text | `"München — 😃"` | `JSONString` | `"München — 😃"` |

`false`, `null`, and `42` are valid JSON scalars. To force those literals to be
text, pass a JSON string such as `"\"false\""`.

## Param.Payload cases

Use every **Script parameter** below to call `TEST_Param.Payload`.

| # | Case | Script parameter | Expected result |
|---|---|---|---|
| 17 | Object | `JSONSetElement ( "{}" ; [ "payload" ; JSONSetElement ( "{}" ; [ "var1" ; "value1" ; JSONString ] ) ; JSONObject ] ; [ "trace" ; "{}" ; JSONObject ] )` | the object under `payload` |
| 18 | Array | `JSONSetElement ( "{}" ; [ "payload" ; "[1,2,3]" ; JSONRaw ] ; [ "trace" ; "{}" ; JSONObject ] )` | `[1,2,3]` (compare with `JSONFormatElements`) |
| 19 | Plain text | `JSONSetElement ( "{}" ; [ "payload" ; "Hello plain text" ; JSONString ] ; [ "trace" ; "{}" ; JSONObject ] )` | `Hello plain text` |
| 20 | Empty text | `JSONSetElement ( "{}" ; [ "payload" ; "" ; JSONString ] ; [ "trace" ; "{}" ; JSONObject ] )` | empty |
| 21 | Number | `JSONSetElement ( "{}" ; [ "payload" ; 42 ; JSONNumber ] ; [ "trace" ; "{}" ; JSONObject ] )` | `42` |
| 22 | Boolean | `JSONSetElement ( "{}" ; [ "payload" ; False ; JSONBoolean ] ; [ "trace" ; "{}" ; JSONObject ] )` | `False` |
| 23 | JSON null | `JSONSetElement ( "{}" ; [ "payload" ; "" ; JSONNull ] ; [ "trace" ; "{}" ; JSONObject ] )` | same as `JSONGetElement ( Get ( ScriptParameter ) ; "payload" )` |
| 24 | Missing payload | `JSONSetElement ( "{}" ; [ "trace" ; "{}" ; JSONObject ] )` | empty |
| 25 | Invalid parameter | `"not JSON"` | empty |
| 26 | Root array, not envelope | `"[1,2,3]"` | empty |

## End-to-end and trace tests

Use `Param.Make ( input )` as the parameter for `TEST_Param.Payload`. Run the
round trip for cases 1, 5–9, and 11–16. Compare object and array results with
`JSONFormatElements` rather than direct string equality.

After `Trace.Init`, run this calculation. It must return `PASS` and proves that
a business `trace` key cannot overwrite framework trace data:

```filemaker
Let (
[
	~payload = JSONSetElement ( "{}" ; [ "trace" ; "business value" ; JSONString ] ) ;
	~actual = Param.Make ( ~payload ) ;
	~ok =
		JSONGetElement ( ~actual ; "payload.trace" ) = "business value"
		and JSONFormatElements ( JSONGetElement ( ~actual ; "trace" ) ) = JSONFormatElements ( Trace.Get )
] ;

	If ( ~ok ; "PASS" ; JSONFormatElements ( ~actual ) )
)
```
