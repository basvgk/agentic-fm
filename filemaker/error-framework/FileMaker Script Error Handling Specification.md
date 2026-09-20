# FileMaker Script Error Handling

Aangemaakt: 2026-09-10

## 1. Doel

Scripts gebruiken één gestandaardiseerde errorstructuur voor:

1. script responses;
2. error propagation naar parent scripts;
3. logging;
4. later: optionele user dialogs.

Een script definieert altijd zijn **eigen fout**. Een native FileMaker-fout kan de aanleiding zijn, maar is slechts
onderliggende technische informatie.

Logging gebruikt hetzelfde error-object als de script response, aangevuld met:

- found set/record context;
- script parameter;
- timestamp;
- UTC millisecond timestamp;
- execution environment.

---

# 2. Standaard scriptvariabelen

Gebruik onderstaande namen consequent:

```text
$_data
$_error
$_FMerror
$_context
$_params
$_trace
$_child_params
$_child_result
$_child_error
$_child_data
```

Betekenis:

```text
$_data          Data voor de response.
$_error         Eigen error-object van het huidige script.
$_FMerror       Native FileMaker error-object.
$_context       Context voor Error.Make.
$_params        Parameters waarmee het huidige script is aangeroepen.
$_trace         Traceobject van de huidige scriptuitvoering. Zie sectie 4a.
$_child_params  Parameters voor een child script.
$_child_result  Volledige response van een child script.
$_child_error   Error-object uit een child response.
$_child_data    Data-object uit een child response.
```

`$_` is gereserveerd voor framework-/script-controlvariabelen.

---

# 3. FMError

De bestaande `FMError.Set` CF retourneert:

```json
{
	"code": 301,
	"detail": "...",
	"line": 42,
	"step": "Set Field"
}
```

Structuur:

```text
code    FileMaker error code.
detail  Get ( LastErrorDetail ).
line    Scriptregel waarop de fout ontstond.
step    FileMaker scriptstep waarop de fout ontstond.
```

De CF schrijft automatisch weg naar `$_FMerror` én retourneert de JSON als resultaat: gebruik als
resultaatvariabele bij aanroep een volatiele `$r`. Geen andere informatie wordt aan FMError toegevoegd.

Additionele hulpfuncties:
* FMError.Get: retourneert als resultaat de waarde uit `$_FMError`
* FMError.ErrorCode: retourneert de filemaker error code
* FMError.Clear: Verwijdert het FMError object

## Belangrijke regel

De FMError CF moet direct na een potentieel falende FileMaker-scriptstep worden geëvalueerd, zodat de
LastError-gegevens worden vastgelegd voordat een volgende scriptstep wordt uitgevoerd. Dit mag na eventuele
`If [ Get ( LastError ) ]`:

```filemaker
Set Field [ ... ]

If [ Get ( LastError ) ]
	Set Variable [ $r ; FMError.Set ]
End If
```

Of:

```filemaker
Set Field [ ... ]
Set Variable [ $r ; FMError.Set ]

If [ JSONGetElement ( $_FMerror ; "code" ) ≠ 0 ]
	...
End If
```

---

# 4. Error-object

Een fout die een script maakt heeft twee lagen:

```text
response-error   Het kleine, stabiele object hieronder. Dit is wat naar de parent gaat: het zit in
                  response.error (sectie 9) en is wat een parent leest via Response.GetError /
                  Response.GetErrorCode / Response.GetErrorMessage (sectie 8, sectie 12).

log-object        De volledige, verrijkte vorm die in $_error zit: het response-error plus recordContext,
                  environment, trace, parameter en timestamps. Alleen bedoeld voor de logger. Zie sectie 6
                  (en 4a/7/7a) voor die volledige structuur.
```

Deze sectie beschrijft het **response-error** — het deel dat elk script zelf definieert:

```json
{
	"errorID": "K7X4P",
	"code": "ORDER_STATUS_UPDATE_FAILED",
	"message": "Order status could not be updated.",
	"userMessage": "The order could not be updated.",
	"context": {
		"orderID": "ORD-1001",
		"targetStatus": "Approved"
	},
	"fmError": {
		"code": 301,
		"detail": "...",
		"line": 42,
		"step": "Set Field"
	}
}
```

## Velden

### `errorID`

Verplicht.

Kort, uniek ID voor deze specifieke foutgebeurtenis, gegenereerd door `Error.Make` zelf (dus altijd
aanwezig, ook in de response — niet alleen in de log).

Doel: als een gebruiker een fout meldt ("werkt niet" + foto van de dialog), is dit het enige gegeven dat
nodig is om de exacte logregel terug te vinden — zonder afhankelijk te zijn van het exacte tijdstip zoals
de gebruiker dat zich herinnert.

Gegenereerd met `ShortId ( lengthId )` (sectie 8). Default lengte 6 tekens uit een leesbaar alfabet
(zonder `0/O`/`1/I`), bijv. `K7X4P9`. Zie `custom-functions/ShortId.txt` voor de collision-afweging per
lengte.

Elke laag in een cascade (Script A -> B -> C) genereert zijn eigen `errorID`, net zoals elke laag zijn
eigen fout maakt (zie sectie 5). Dit is niet hetzelfde als `traceID` (zie sectie 4a), die juist gelijk is
over alle lagen van één uitvoering.

### `code`

Verplicht.

Stabiele, door ons gedefinieerde errorcode:

```text
ORDER_STATUS_UPDATE_FAILED
MISSING_ORDER_ID
CUSTOMER_NOT_FOUND
```

Gebruik deze voor programmatische verwerking door parent scripts.

### `message`

Verplicht.

Technische, voor developer/logging geschikte beschrijving van de fout.

```text
Required parameter orderID is empty.
Customer record could not be created.
Commit failed after updating the order status.
```

Dit is niet automatisch de tekst voor een user dialog.

### `userMessage`

Optioneel.

Tekst die geschikt is om aan een eindgebruiker te tonen. Zonder specifieke user-facing melding is dit veld
leeg.

Of een dialog daadwerkelijk wordt weergegeven is geen eigenschap van Error. Dat wordt later apart geregeld door
de script-invocation/dialog-policy.

### `context`

Altijd onderdeel van Error.

Bevat alleen dynamische waarden die relevant zijn voor het begrijpen van deze specifieke fout.

Bijvoorbeeld:

```json
"context": {
	"orderID": "ORD-1001",
	"targetStatus": "Approved"
}
```

Gebruik context bijvoorbeeld voor:

- record identifiers;
- relevante parameters;
- verwachte versus gevonden waarden;
- relevante status;
- child error code indien nuttig.

Gebruik context niet als algemene variabledump.

### `fmError`

Bevat het bestaande FMError-object wanneer een FileMaker-fout aan de fout ten grondslag ligt. Zonder
native FileMaker-fout is dit een leeg object (`{}`).

---

# 4a. Trace-object

Eén `traceID` per volledige scriptuitvoering (gelijk over alle lagen van cascade Script A -> B -> C),
plus een `scriptPath`: array van scriptnamen in aanroepvolgorde, root eerst. Los van `errorID` (sectie 4),
die per fout en per laag uniek blijft.

Gebruik: alle logregels van één uitvoering terugvinden op `traceID`, en de aanroepketen zien tot aan de
fout.

```json
{
	"traceID": "550e8400-e29b-41d4-a716-446655440000",
	"scriptPath": ["Orders_Process", "Orders_UpdateStatus"]
}
```

```text
traceID     Uniek ID voor deze volledige uitvoering, gegenereerd met Get ( UUID ) door het buitenste
            (root) script. Geen leesbaar/kort ID zoals errorID: een traceID wordt nooit door een mens
            overgetypt of voorgelezen, dus een standaard UUID is voldoende.
scriptPath  Scriptnamen in aanroepvolgorde, root eerst. Een script dat zichzelf recursief aanroept komt
            meerdere keren voor — dat is bedoeld (toont recursiediepte).
```

Binnen het scriptparameter (het JSON dat `Param.Make` bouwt, sectie 8) staat dit object onder de key
`"trace"`. Business-parameters gebruiken deze key niet, en de developer typt 'm zelf nooit — dat doen
`Trace.Init` en `Param.Make`.

`trace` is uitvoeringscontext, geen onderdeel van de fout zelf: het zit niet in het response-error-object
(hierboven) en gaat niet mee naar de parent via `Response.GetError`. Het staat wel in het log-object
(sectie 6), als losse laag naast `error`/`recordContext`/`environment`.

---

# 6. Logging

`$_error` is **log-ready** vanaf het moment dat `Error.Make` het aanmaakt (sectie 8):

```json
{
	"schemaVersion": 1,
	"error": {
		"errorID": "K7X4P9",
		"code": "ORDER_STATUS_UPDATE_FAILED",
		"message": "Order status could not be updated.",
		"userMessage": "The order could not be updated.",
		"context": {
			"orderID": "ORD-1001"
		},
		"fmError": {
			"code": 301,
			"detail": "...",
			"line": 42,
			"step": "Set Field"
		}
	},
	"recordContext": {
		"...": "zie sectie 7a"
	},
	"environment": {
		"...": "zie sectie 7"
	},
	"trace": {
		"traceID": "550e8400-e29b-41d4-a716-446655440000",
		"scriptPath": ["Orders_Process", "Orders_UpdateStatus"]
	},
	"parameter": {
		"orderID": "ORD-1001",
		"targetStatus": "Approved"
	},
	"timestamp": "10-09-2026 21:22:31",
	"timestampUTCms": 63903669751432
}
```

Velden:

```text
schemaVersion   Versienummer van deze log-objectstructuur. Ophogen bij een breaking change van dit format.
error           Exact de sectie-4-structuur, ongewijzigd overgenomen in de response (zie sectie 9).
recordContext   Found set/record-info op het moment van de fout. Zie sectie 7a.
environment     Execution environment op het moment van de fout. Zie sectie 7.
trace           Traceobject van de huidige scriptuitvoering. Zie sectie 4a. Leeg object (`{}`) wanneer
                Trace.Init niet is aangeroepen.
parameter       Het scriptparameter waarmee het huidige script is aangeroepen ($_params).
timestamp       Normale FileMaker timestamp.
timestampUTCms  Get ( CurrentTimeUTCMilliseconds ) — absoluut UTC-gebaseerd millisecondetal sinds 1-1-0001.
```

De businessspecifieke `context` hoort bij het Error-object zelf (sectie 4); record-/found-set-info heet
`recordContext`; device/sessie-info heet `environment`; uitvoeringsketen-info heet `trace`. `layout` staat
alleen in `environment`, niet nogmaals in `recordContext`.

`environment` en `recordContext` worden vastgelegd op het moment dat `Error.Make` wordt aangeroepen, en
beschrijven dus de execution context van de fout zelf — niet die van het latere logging-script.

Loggen gebeurt door `$_error` ongewijzigd als parameter mee te geven aan het logging-script (zie sectie 13).

---

# 7. Environment

Standaard logging environment:

```json
{
	"script": "",
	"file": "",
	"layout": "",
	"window": "",
	"windowMode": 0,
	"account": "",
	"user": "",
	"sessionIdentifier": "",
	"applicationVersion": "",
	"hostApplicationVersion": "",
	"hostName": "",
	"hostIPAddress": "",
	"systemPlatform": 0,
	"systemVersion": "",
	"device": 0,
	"persistentID": "",
	"systemIPAddress": "",
	"transactionOpenState": false,
	"recordOpenState": 0,
	"recordOpenCount": 0
}
```

Vastgelegd met FileMaker `Get()`-functies op het moment dat `Error.Make` wordt aangeroepen, via de CF
`Environment.Get` (sectie 8), o.a.:

```text
windowMode          Get ( WindowMode )
recordOpenState     Get ( RecordOpenState )
recordOpenCount     Get ( RecordOpenCount )
```

---

# 7a. Record Context

`recordContext` legt vast in welke found set/record-situatie de fout ontstond, vastgelegd op het moment
dat `Error.Make` wordt aangeroepen via de CF `RecordContext.Get` (sectie 8).

```json
{
	"tableOccurrence": "Orders",
	"foundCount": 42,
	"foundSetRecordIDs": ["18712-18715", "18719"],
	"activeRecordID": 18713,
	"activeRecordNumber": 2,
	"activePortalRowNumber": 0
}
```

Bron van elk veld:

```text
tableOccurrence        Get ( LayoutTableName ) — de TO waarop de huidige layout is gebaseerd.
foundCount              Get ( FoundCount )
foundSetRecordIDs       GetRecordIDsFromFoundSet ( 4 ), altijd opgenomen.
activeRecordID          Get ( RecordID )
activeRecordNumber      Get ( ActiveRecordNumber )
activePortalRowNumber   Get ( ActivePortalRowNumber )
```

`layout` wordt hier niet herhaald: die staat al in `environment` (sectie 7).

---

# 8. Custom Functions

De volledige implementatie (inclusief header conform AGENTS.md) staat in `custom-functions/<Naam>.txt`.

```text
Bestaand
--------
FMError.Set                  Legt Get ( LastError )-info vast, zet en retourneert $_FMerror.
FMError.Get                  Geeft $_FMerror terug.
FMError.GetCode               Geeft de FileMaker errorcode terug.
FMError.Clear                Wist $_FMerror.
ShortId ( lengthId )          Genereert een kort, leesbaar, willekeurig ID (custom-functions/ShortId.txt).
JSON.IsValid ( json )         Bestaat al live. Waar/onwaar: is json geldige JSON.

Trace (sectie 4a)
-----------------
Trace.Init                    Bouwt/vervolgt het traceobject: nieuw bij een root-script, overgenomen +
                              aangevuld bij een child-script. Zet $_trace.
Trace.Get                     Geeft $_trace terug.

Environment / RecordContext (sectie 7/7a)
------------------------------------------
Environment.Get               Geeft de execution environment terug.
RecordContext.Get             Geeft de found set/record-context terug.

Error (sectie 4/6)
-------------------
Error.Make ( code ; message ; userMessage ; context )
                              Bouwt het volledige log-ready object (haalt fmError/environment/
                              recordContext/trace zelf op). Zet $_error.
Error.Get                     Geeft $_error terug.

Param (sectie 4a)
------------------
Param.Make ( payload )        Bouwt het childparameter uit de business-payload, met trace erin. Zet
                              $_child_params.

Response (sectie 9)
--------------------
Response.Make ( data )        Bouwt de response envelope uit data en $_error (via Error.Get).
Response.Capture              Leest Get ( ScriptResult ), zet en retourneert $_child_result (geldige JSON,
                              anders "{}").
Response.Get                  Geeft $_child_result terug (leeg object bij lege/ongeldige data).
Response.IsOK                 Was de laatste child-response ok?
Response.GetData              Data-deel van de laatste child-response.
Response.GetError             Error-deel van de laatste child-response.
Response.GetErrorCode         code van de fout in de laatste child-response.
Response.GetErrorMessage      message van de fout in de laatste child-response.
Response.GetErrorUserMessage  userMessage van de fout in de laatste child-response.
```

---

# 9. Response-object

Elk script eindigt via `Response.Make` in deze envelope:

```json
{
	"schemaVersion": 1,
	"ok": false,
	"data": "",
	"error": {}
}
```

`error` is exact de sectie-4-structuur. Zonder fout: `ok: true`, `error: {}`.

---

# 10. Eigen validatiefout

Voorbeeld: ontbrekende parameter. `$_params` komt van buiten het script en is niet gegarandeerd geldige
JSON — vandaar de `JSON.IsValid`-check vóór `JSONGetElement`, niet enkel `IsEmpty` op het resultaat.

```filemaker
If [ not JSON.IsValid ( $_params ) or IsEmpty ( JSONGetElement ( $_params ; "orderID" ) ) ]

	Set Variable [ $_context ;
		JSONSetElement ( "{}" ;
			[ "parameter" ; "orderID" ; JSONString ]
		)
	]

	Set Variable [ $_error ;
		Error.Make (
			"MISSING_ORDER_ID" ;
			"Required parameter orderID is empty." ;
			"No order was specified." ;
			$_context
		)
	]

	Perform Script on Server [
		"SYS_LogError" ;
		Parameter: $_error
	]

End If

Exit Loop If [ not IsEmpty ( $_error ) ]
```

---

# 11. FileMaker scriptstep error

Direct na de risicostap:

```filemaker
Set Field [ Orders::Status ; $newStatus ]
Set Variable [ $_FMerror ; FMError ]
```

Daarna beoordelen:

```filemaker
If [ JSONGetElement ( $_FMerror ; "code" ) ≠ 0 ]

	Set Variable [ $_context ;
		JSONSetElement ( "{}" ;
			[ "orderID" ; $orderID ; JSONString ] ;
			[ "targetStatus" ; $newStatus ; JSONString ]
		)
	]

	Set Variable [ $_error ;
		Error.Make (
			"ORDER_STATUS_UPDATE_FAILED" ;
			"FileMaker could not update the order status." ;
			"The order could not be updated." ;
			$_context
		)
	]

	Perform Script on Server [
		"SYS_LogError" ;
		Parameter: $_error
	]

End If

Exit Loop If [ not IsEmpty ( $_error ) ]
```

`Error.Make` haalt `fmError` automatisch op via `FMError.Get` (sectie 8). Wanneer een FileMaker-fout
bewust **niet** tot een eigen fout leidt (het script gaat door zonder `Error.Make` aan te roepen), wis
`$_FMerror` alsnog expliciet — anders neemt een latere, ongerelateerde `Error.Make`-aanroep verderop in
hetzelfde script deze per ongeluk mee:

```filemaker
Set Variable [ $_FMerror ; FMError.Clear ]
```

---

# 12. Child script

Call:

```filemaker
Set Variable [ $_child_params ;
	Param.Make (
		JSONSetElement ( "{}" ;
			[ "orderID" ; $orderID ; JSONString ]
		)
	)
]

Perform Script [ "Orders_UpdateStatus" ; Parameter: $_child_params ]

Set Variable [ $r ; Response.Capture ]
```

`Param.Make` (sectie 8) voegt de trace (sectie 4a) automatisch toe aan het childparameter.

Gebruik hier altijd `Response.Capture`, nooit rechtstreeks `Get ( ScriptResult )`: die stap moet als
eerste na de child-aanroep worden uitgevoerd, vóórdat een volgend subscript (bijvoorbeeld een
logging-aanroep verderop in ditzelfde script) `Get ( ScriptResult )` overschrijft. `Response.Capture` zet
`$_child_result` als side effect; `$r` is een volatiele wegwerpvariabele voor het retourresultaat (net als
bij `FMError.Set`, sectie 3). Eenmaal gezet staat `$_child_result` vast, ook als er daarna nog andere
`Perform Script`/`Perform Script on Server`-stappen volgen.

Check response:

```filemaker
If [ not Response.IsOK ]

	Set Variable [ $_context ;
		JSONSetElement ( "{}" ;
			[ "childErrorCode" ; Response.GetErrorCode ; JSONString ]
		)
	]

	Set Variable [ $_error ;
		Error.Make (
			"ORDER_PROCESSING_FAILED" ;
			"Order processing failed in the status update child script." ;
			"The order could not be processed." ;
			$_context
		)
	]

	Perform Script on Server [
		"SYS_LogError" ;
		Parameter: $_error
	]

End If

Exit Loop If [ not IsEmpty ( $_error ) ]
```

`Response.IsOK` en `Response.GetErrorCode` nemen geen parameter: ze lezen `$_child_result` intern via
`Response.Get` (sectie 8). Dit blijft correct zolang dit de eerstvolgende check is na de child-aanroep
hierboven — er is nog geen tweede child-aanroep tussendoor geweest die `$_child_result` overschrijft.

De parent gebruikt de child error om zijn eigen fout te bepalen; de volledige child error wordt niet
opgenomen als `cause`. `childErrorCode` in `context` is nuttig maar niet verplicht.

Bij succes:

```filemaker
Set Variable [ $_child_data ;
	Response.GetData
]
```

---

# 13. Loggingregels

Iedere scriptlaag logt zijn eigen error door `$_error` ongewijzigd als parameter mee te geven (`Error.Make`
heeft het al log-ready gemaakt, sectie 6/8):

```filemaker
Perform Script on Server [
	"SYS_LogError" ;
	Parameter: $_error
]
```

De logger ontvangt daarmee altijd:

```text
schemaVersion
error
recordContext
environment
trace
parameter
timestamp
timestampUTCms
```

De logging-call mag de oorspronkelijke `$_error` nooit vervangen.

---

# 14. User dialogs

`userMessage` en het daadwerkelijk tonen van een dialog zijn twee verschillende zaken:

```text
userMessage
    = wat geschikt is om eventueel te tonen

dialog policy
    = of het huidige script de melding zelf moet tonen
```

Dit is vooral relevant voor scripts die zowel zelfstandig als als child kunnen draaien: een zelfstandig
uitgevoerd script kan bijvoorbeeld zelf een foutmelding tonen, terwijl hetzelfde script als child alleen
zijn response retourneert.

De exacte standaardparameter en dialog-policy worden apart vastgelegd. Tot die tijd mag error-handling code
niet aannemen dat een aanwezige `userMessage` automatisch getoond moet worden.

---

# 15. Scriptskelet

Elk script gebruikt één centraal exitpunt, langs deze vorm:

```filemaker
Set Error Capture [ On ]

Set Variable [ $_params ; Get ( ScriptParameter ) ]
Set Variable [ $_trace ; Trace.Init ]
Set Variable [ $_data ; "" ]
Set Variable [ $_error ; "" ]
Set Variable [ $_FMerror ; "" ]
Set Variable [ $_context ; "{}" ]

Loop

	# Validate
	# Create + log error when needed

	Exit Loop If [ not IsEmpty ( $_error ) ]

	# Work
	# Capture FMError immediately after risky FileMaker steps
	# Create + log own Error when needed

	Exit Loop If [ not IsEmpty ( $_error ) ]

	# Child scripts
	# Convert child error to own error when needed

	Exit Loop If [ not IsEmpty ( $_error ) ]

	# Success
	Set Variable [ $_data ; ... ]

	Exit Loop If [ True ]

End Loop

# Cleanup here — mag $_error niet overschrijven

Exit Script [ Response.Make ( $_data ) ]
```

Childvariabelen ($_child_params, $_child_result, ...) worden pas geïnitialiseerd waar het script ze
gebruikt.

---

# 16. Kernregels voor agents

Wanneer een script wordt gemaakt of aangepast:

1. Gebruik de standaard `$_` variabelen.
2. Leg `Get ( ScriptParameter )` direct vast in `$_params`.
3. Roep direct daarna `Trace.Init` aan en zet het resultaat in `$_trace`.
4. Maak iedere applicatiefout met `Error.Make`.
5. Gebruik altijd een eigen applicatie-errorcode.
6. Maak `message` developer/logging gericht.
7. Maak `userMessage` alleen wanneer een user-facing melding zinvol is.
8. Plaats relevante dynamische waarden in `context`.
9. Capture FMError direct na iedere relevante FileMaker-scriptstep.
10. Gebruik FMError alleen als technische onderliggende fout.
11. Wis `$_FMerror` met `FMError.Clear` zodra een FileMaker-fout bewust genegeerd wordt (geen eigen fout
    tot gevolg heeft), zodat een latere `Error.Make`-aanroep 'm niet per ongeluk overneemt.
12. Log iedere door het huidige script gemaakte fout.
13. Geef `$_error` ongewijzigd mee als parameter aan het logging-script.
14. Propagate geen geneste `cause`-objecten.
15. Bouw een childparameter altijd met `Param.Make`, nooit handmatig met de key `"trace"`.
16. Een parent maakt op basis van een child error zijn eigen fout.
17. Toon `userMessage` niet automatisch.
18. Laat cleanup nooit de oorspronkelijke `$_error` overschrijven.
19. Gebruik één finale `Exit Script [ Response.Make ( $_data ) ]`.
20. Geef `$_FMerror`, `$_error`, `$_trace` en `$_child_result` nooit als expliciete parameter door aan een
    CF die er al een eigen `Get`-functie voor heeft (`FMError.Get`, `Error.Get`, `Trace.Get`,
    `Response.Get`).
21. Capture het resultaat van een child-aanroep direct erna met `Set Variable [ $r ; Response.Capture ]`,
    nooit rechtstreeks met `Get ( ScriptResult )`.
