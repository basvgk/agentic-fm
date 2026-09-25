# Custom functions

Lijst van CF's in deze map. Volledige implementatie + header (Purpose/Returns/Parameters/Author/Version/
Updated/Remarks/Changelog) staat in het bijbehorende `.txt`-bestand. Zie
`../FileMaker Script Error Handling Specification.md` voor het volledige ontwerp.

## Actueel (conform de spec)

```text
FMError.Set                  Legt Get ( LastError )-info vast, zet en retourneert $_FMerror.
FMError.Get                  Geeft $_FMerror terug.
FMError.GetCode              Geeft de FileMaker errorcode terug.
FMError.Clear                Wist $_FMerror.
ShortId ( lengthId )         Genereert een kort, leesbaar, willekeurig ID.
JSON.IsValid ( json )        Is json niet-leeg en geldige JSON? (bestaat live, geen los .txt hier)

Trace.Init                   Bouwt/vervolgt het traceobject; zet $_trace.
Trace.Get                    Geeft $_trace terug.

Environment.Get              Geeft de execution environment terug.
RecordContext.Get            Geeft de found set/record-context terug.

Error.Make ( code ; message ; userMessage ; context )
                              Bouwt het volledige log-ready error-object; logt non-empty data van de meest
                              recente child-response als childResponseData; zet $_error.
Error.Get                    Geeft $_error terug.
Error.GetID                  Geeft de errorID van $_error terug (`Error.GetID.txt` + paste-ready XML).
Error.GetCode                Geeft de application errorcode van $_error terug (`Error.GetCode.txt` + paste-ready XML).
Error.GetUserMessage         Geeft de userMessage van $_error terug (`Error.GetUserMessage.txt` + paste-ready XML).

Param.Make ( payload )       Bouwt het childparameter als envelope met afzonderlijke payload- en
                              trace-waarden; ondersteunt JSON en platte tekst; zet $_child_params.
Param.Payload                Geeft de business-payloadwaarde van het huidige scriptparameter terug;
                              zet $_paramPayload.

Zie `Param.Tests.md` voor paste-ready FileMaker-berekeningen en een volledige testmatrix.

Response.Make ( data )       Bouwt de response envelope uit data en $_error.
Response.Capture             Leest Get ( ScriptResult ), zet en retourneert $_child_result (geldige JSON,
                              anders "{}").
Response.Get                 Geeft $_child_result terug (leeg object bij lege/ongeldige data).
Response.IsOK                Was de laatste child-response ok?
Response.GetData             Data-deel van de laatste child-response.
Response.GetError            Error-deel van de laatste child-response.
Response.GetErrorCode        code van de fout in de laatste child-response.
Response.GetErrorMessage     message van de fout in de laatste child-response.
Response.GetErrorUserMessage userMessage van de fout in de laatste child-response.
```
