# Wat de frontend van de backend kan verwachten

**Status: de volledige Rust/SQLite/BGE-demo is onafhankelijk via echte HTTP en de browser gecontroleerd.** Fixtures blijven beschikbaar voor los frontendwerk. [OpenAPI](openapi.yaml) is het canonieke contract; wijzigingen stemmen frontend- en backend-agent samen af.

## Zoeken

`POST /api/search` gebruikt `multipart/form-data`:

| Veld | Waarde |
|---|---|
| `document` | Optioneel PDF- of UTF-8-TXT-bestand, maximaal 10 MiB. |
| `query` | Optionele UTF-8-tekst, maximaal 1 MiB vóór trimmen; omringende witruimte wordt verwijderd. |
| `retrieval_method` | Optioneel `opinion_chunks` (standaard) of `head_matter`. |

Document-only, vraag-only en beide zijn ondersteund. Minstens één moet bruikbaar zijn. Een meegestuurd ongeldig bestand geeft een fout, ook wanneer de vraag wel geldig is. Laat de browser bij `FormData` zelf de multipart `Content-Type` met boundary zetten.

De volledige multipartrequest mag maximaal 12 MiB zijn; het document zelf blijft maximaal 10 MiB. Uitgelezen PDF-tekst is begrensd op 20 MiB. De backend weigert overschrijdingen en kapt tekst niet stil af.

Een succesvolle response bevat `retrieval_method`, `mode`, `corpus_version`, `ranking_version` en precies drie `results`. Elk resultaat bevat `case_id`, `title`, `court`, `decision_date`, `citation`, `case_url`, `text_version`, `score` en `passage`.

- `mode`: `document`, `query` of `combined`.
- `score`: overeenkomst tussen -1 en 1, geen percentage of juridische zekerheid.
- `passage`: `passage_id`, oorspronkelijke `text`, `start_utf16`, `end_utf16`. Nieuwe indexresultaten voegen `source_section` (`majority` of `head_matter`) en de eigen `text_version` toe.
- `retrieval_method`: de gekozen bronindex. Beide methoden gebruiken hetzelfde lokale model, dezelfde cosinusscore en dezelfde top-drieafspraak. Head matter is redactionele context, geen rechterlijke redenering. Een onbekende, lege of dubbele methode is een 400-fout.
- De drie zaken zijn uniek en staan op aflopende score. We tonen de hoogste scores uit het volledige corpus volgens de afgesproken methode, ook wanneer de overeenkomst inhoudelijk zwak is. Er is nog geen gevalideerde relevantiedrempel.

## Volledige documenten met markering

Haal voor ieder resultaat `GET /api/cases/{case_id}` op via `case_url`. De response bevat dezelfde zaakmetadata, `corpus_version`, `text_version` en de volledige canonieke `text` van het meerderheidsoordeel (majority opinion). Afwijkende of aanvullende opinions horen niet bij deze detailtekst.

Nieuwe detailresponses voegen de afzonderlijke `head_matter` en `head_matter_text_version` toe; `text` blijft altijd het volledige meerderheidsoordeel. Kies bij `passage.source_section: head_matter` de head-mattertekst en controleer de eigen passageversie tegen `head_matter_text_version`. Toon de gemarkeerde redactionele context apart, met het volledige meerderheidsoordeel eronder. Een head-matterpassage mag nooit in `text` worden gemarkeerd.

Markeer bij `source_section: majority` `text.slice(passage.start_utf16, passage.end_utf16)` in de detailtekst. De posities zijn **JavaScript/UTF-16-eenheden**, beginnen bij nul en het einde is exclusief. De uitsnede is exact gelijk aan `passage.text`. De frontend mag de tekst vóór het toepassen van de posities niet normaliseren of inkorten. Render tekst met veilige tekstnodes en bijvoorbeeld `<mark>`; ruwe HTML injecteren is niet nodig.

Oude synthetische opinion-fixtures zonder sectie/passagetekstversie blijven leesbaar als majority; een head-matterresultaat vereist expliciete sectie en versie. Controleer dat `text_version` en `corpus_version` van zoekresultaat en detail overeenkomen. Bij een verschil: ververs de zoekopdracht; pas oude posities niet op nieuwe tekst toe. Iedere zaak heeft in deze versie één best scorende passage. Dit ondersteunt drie leesbare documenten met een markering; er worden geen originele PDF's of PDF-coördinaten geleverd.

## Meteen met fixtures bouwen

- [search-response.json](examples/search-response.json): één volledige response met drie resultaten.
- [cases.json](examples/cases.json): drie detailresponses als array. Een lokale mock voor `GET /api/cases/{id}` kiest hieruit op `case_id` en retourneert **één object**, niet de array.

Alle fixtureteksten, namen, scores en datums zijn verzonnen. Hetzelfde responseformaat geldt voor alle invoermodi; de fixture toont `mode: query`. Verander in mocks de mode wanneer de invoer anders is.

## Fouten en verbinding

Fouten gebruiken steeds `{"error":{"code":"...","message":"..."}}`. Toon de leesbare `message`.

| HTTP | Betekenis |
|---|---|
| 400 | Geen bruikbare invoer, ongeldige multipart of vraag groter dan 1 MiB UTF-8. |
| 413 | Bestand groter dan 10 MiB of volledige multipartrequest groter dan 12 MiB. |
| 415 | Ander bestandstype dan PDF/TXT. |
| 422 | Meegegeven bestand onleesbaar, leeg, versleuteld, scan zonder uitleesbare tekst of PDF-tekst groter dan 20 MiB. |
| 404 | Gevraagde zaak bestaat niet. |
| 503 | Volledige zoekindex nog niet beschikbaar. |
| 500 | Onverwachte backendfout. |

De standaard backend-URL is `http://127.0.0.1:8000`; de gewone frontend draait op `http://127.0.0.1:5173` en kiest standaard de echte API. Een extra API-preview kan op `http://127.0.0.1:5174` draaien. Fixtures zijn uitsluitend opt-in via `VITE_API_MODE=mock` of `npm run dev:mock`; API-/netwerkfouten geven nooit fictieve resultaten. Maak de frontend-base-URL configureerbaar. De backend ondersteunt CORS voor configureerbare ontwikkelorigins, standaard `http://localhost:5173` en `http://127.0.0.1:5173`. De API-preview voegt beide 5174-origins toe via `ADAMI_CORS_ORIGINS`; de startcommando’s staan in README.

`GET /api/health` geeft pas 200 met `status: ready` als het volledige corpus beschikbaar is; anders 503. De runtime biedt het contract aan op `GET /openapi.json`. Geen API-key nodig voor deze lokale demo; er hoort geen Orq-key in de frontend.

## Optionele Orq-adapter

De afzonderlijke adapter op `http://127.0.0.1:18000` accepteert dezelfde zoekinvoer en proxy’t volledige zaakteksten/health naar de bestaande backend op 8000. Gebruik voor deze aparte preview `VITE_API_BASE_URL=http://127.0.0.1:18000` op frontendpoort 5175. Er is geen sleutel in de frontend.

`SearchResponse.explanation_status` is optioneel: `available` betekent dat alle drie modeltoelichtingen gevalideerd zijn, `unavailable` betekent echte resultaten zonder toelichting. Alleen bij `available` heeft elk resultaat `explanation: {text, citations: [{passage_id, quote}], limitations: string[]}`. Het model kiest uitsluitend een bestaande passage-ID per zaak; de server vult `quote` met de exacte bronpassage. Bij ongeldige tool-/schemauitvoer blijft de oorspronkelijke top drie beschikbaar met `unavailable`. Expliciete provider-HTTP- of modelidentiteitsfouten geven 502 `model_unavailable`, zonder een ander model te kiezen. Als de eigenlijke zoekbackend faalt, geldt het bestaande HTTP-foutcontract. De normale backend op 8000 hoeft deze optionele velden niet te leveren.

In de expliciet geautoriseerde uploadbewuste adapter op 18000 (of de afzonderlijke QA-preview op 18001) gaat de volledige canonical uitgelezen uploadtekst naast de vraag en bronpassages naar het taalmodel. Dezelfde Rust-extractor bepaalt die tekst, zonder extra normalisatie. De aparte modelcontextgrens is standaard 48 KiB UTF-8-uploadtekst, serverzijdig configureerbaar met `--max-upload-text-bytes`; overschrijding geeft expliciet 413, nooit stille truncatie. De oude niet-gelezen-uploadbeperking wordt in deze route niet meer toegevoegd. De frontend toont modeltekst en noodzakelijke beperkingen compact boven de volledige meerderheidstekst; de gevalideerde passage blijft in de juiste bronsectie gemarkeerd. Extra quoteblokken en citaatlinks worden niet herhaald, maar de bronverwijzingen blijven in de API aanwezig. Versies en UTF-16-markeringen blijven behouden. Geen modeltekst als bewijs van juridische juistheid presenteren.

Bij een upload bevat de response optioneel `input_context: {text_version, utf16_length}`. `text_version` is SHA-256 van de exacte UTF-8-extractietekst; `utf16_length` en citaatposities zijn JavaScript UTF-16-eenheden. Iedere beschikbare uploaduitleg bevat `input_citations: [{quote, start_utf16, end_utf16}]`: servergeverifieerde stukken van diezelfde upload, begin inclusief/einde exclusief. Het model kiest alleen toegestane input-ID’s en schrijft de quotes/posities niet zelf. Onbekende of verwisselde input-ID’s maken de uitleg `unavailable`; drie oorspronkelijke zoekresultaten blijven beschikbaar. Vraag-only laat `input_context` en inputcitaten weg.

De officiële Orq-frontend op 5175 wijst naar 18000; een afzonderlijke QA-frontend op 5176 kan naar 18001 wijzen. De reader behoudt één compacte toelichting en het volledige gemarkeerde corpusdocument; een ingeklapte bron ‘Uit je document’ toont alleen geverifieerde uploadcitaten als beide contextidentiteit en citaten beschikbaar zijn. Er is geen apart responseveld met de volledige upload; alleen aangehaalde fragmenten worden teruggestuurd. Bestaande API-responses zonder deze optionele velden blijven ondersteund.


## Lokale evaluatievergelijking

`POST /api/evals/search` bestaat uitsluitend op de Rust-backend en gebruikt dezelfde geladen engine als productzoeken. De multipartinvoer is gelijk aan zoeken, plus optioneel `excluded_case_ids`: een JSON-array als tekst, bijvoorbeeld `["156133"]`. Uitsluitingen worden vóór scoring en top drie toegepast. Onbekende/dubbele IDs of minder dan drie overblijvende zaken geven 400.

De response is `{response, excluded_case_ids, eligible_case_count, index_manifest}`. `response` is de gewone zoekresponse met expliciete methode; het manifest bindt corpus, modelbestanden en verwerking. Voer A en B na elkaar uit op dezelfde invoer en uitsluitingen en vergelijk de volledige manifesten. De evalserver start geen extra embeddingproces en een lokale vergelijking heeft geen Orq-key nodig. Bewaar daadwerkelijke resultaten en timings; een rangverschil of overlap is geen juridische kwaliteitsmetric.

Het main-startprofiel gebruikt backend `127.0.0.1:8000`, app `127.0.0.1:5176` en evaluatiepagina `127.0.0.1:8798`. De bestaande database en binary blijven behouden; slechts één native modeljob draait tegelijk.

## Modelkeuze op de optionele servers

`GET /api/models` op de Orq-sidecar en de evalserver geeft `{models:[{id,label}],default_model}`. De server bepaalt de ondersteunde opties. Een gewone Rustserver geeft 404; verberg dan de modelkiezer en blijf lokaal zoeken. Andere catalogusfouten mogen niet door verzonnen modelIDs worden vervangen.

Bij `POST /api/search` naar de sidecar staat de keuze in de optionele header `X-Orq-Model`; voeg geen nieuw multipartveld toe. Zonder header geldt de serverdefault. CORS staat de header voor de expliciete lokale frontendorigins toe. `SearchResponse.explanation_requested_model` bevat de keuze, `explanation_model` de werkelijk gemelde provider-ID of `null` wanneer onbekend. Toon een eerdere uitslag met zijn eigen response-ID, ook als de gebruiker daarna een andere optie kiest. Model-/toegangsfouten geven een duidelijke fout zonder ander model te kiezen. Het core-Rust-OpenAPI-contract en de bronranking veranderen niet; alleen de sidecar `/openapi.json` documenteert de extra route/header/velden.

E06 accepteert `{"model":"server-model-id"}` op zijn runroute; `{}` gebruikt de serverdefault. B1 accepteert `{}` voor standaardB of `retrieval_methods` voor A/B/beide; judge/modelvelden zijn niet toegestaan. B1 toont geen AI-modelpicker. E06-artifactvelden `requested_model` en `model` onderscheiden de keuze van de werkelijk gemelde provider-ID. Onbekende keuzes worden vóór retrieval of modelaanroepen afgewezen met 400 `unsupported_model`.
