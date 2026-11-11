# Wat de frontend van de backend kan verwachten

**Status: de volledige Rust/SQLite/BGE-demo is onafhankelijk via echte HTTP en de browser gecontroleerd.** Fixtures blijven beschikbaar voor los frontendwerk. [OpenAPI](openapi.yaml) is het canonieke contract; wijzigingen stemmen frontend- en backend-agent samen af.

## Zoeken

`POST /api/search` gebruikt `multipart/form-data`:

| Veld | Waarde |
|---|---|
| `document` | Optioneel PDF- of UTF-8-TXT-bestand, maximaal 10 MiB. |
| `query` | Optionele UTF-8-tekst, maximaal 1 MiB vóór trimmen; omringende witruimte wordt verwijderd. |

Document-only, vraag-only en beide zijn ondersteund. Minstens één moet bruikbaar zijn. Een meegestuurd ongeldig bestand geeft een fout, ook wanneer de vraag wel geldig is. Laat de browser bij `FormData` zelf de multipart `Content-Type` met boundary zetten.

De volledige multipartrequest mag maximaal 12 MiB zijn; het document zelf blijft maximaal 10 MiB. Uitgelezen PDF-tekst is begrensd op 20 MiB. De backend weigert overschrijdingen en kapt tekst niet stil af.

Een succesvolle response bevat `mode`, `corpus_version`, `ranking_version` en precies drie `results`. Elk resultaat bevat `case_id`, `title`, `court`, `decision_date`, `citation`, `case_url`, `text_version`, `score` en `passage`.

- `mode`: `document`, `query` of `combined`.
- `score`: overeenkomst tussen -1 en 1, geen percentage of juridische zekerheid.
- `passage`: `passage_id`, oorspronkelijke `text`, `start_utf16`, `end_utf16`.
- De drie zaken zijn uniek en staan op aflopende score. We tonen de hoogste scores uit het volledige corpus volgens de afgesproken methode, ook wanneer de overeenkomst inhoudelijk zwak is. Er is nog geen gevalideerde relevantiedrempel.

## Volledige documenten met markering

Haal voor ieder resultaat `GET /api/cases/{case_id}` op via `case_url`. De response bevat dezelfde zaakmetadata, `corpus_version`, `text_version` en de volledige canonieke `text` van het meerderheidsoordeel (majority opinion). Afwijkende of aanvullende opinions horen niet bij deze detailtekst.

Markeer `text.slice(passage.start_utf16, passage.end_utf16)` in de detailtekst. De posities zijn **JavaScript/UTF-16-eenheden**, beginnen bij nul en het einde is exclusief. De uitsnede is exact gelijk aan `passage.text`. De frontend mag de tekst vóór het toepassen van de posities niet normaliseren of inkorten. Render tekst met veilige tekstnodes en bijvoorbeeld `<mark>`; ruwe HTML injecteren is niet nodig.

Controleer dat `text_version` en `corpus_version` van zoekresultaat en detail overeenkomen. Bij een verschil: ververs de zoekopdracht; pas oude posities niet op nieuwe tekst toe. Iedere zaak heeft in deze versie één best scorende passage. Dit ondersteunt drie leesbare documenten met een markering; er worden geen originele PDF's of PDF-coördinaten geleverd.

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

`SearchResponse.explanation_status` is optioneel: `available` betekent dat alle drie modeltoelichtingen gevalideerd zijn, `unavailable` betekent echte resultaten zonder toelichting. Alleen bij `available` heeft elk resultaat `explanation: {text, citations: [{passage_id, quote}], limitations: string[]}`. Het model kiest uitsluitend een bestaande passage-ID per zaak; de server vult `quote` met de exacte bronpassage. Bij een mislukte model/provider/schema-stap blijft de oorspronkelijke top drie beschikbaar met `unavailable`. Als de eigenlijke zoekbackend faalt, geldt het bestaande HTTP-foutcontract. De normale backend op 8000 hoeft deze optionele velden niet te leveren.

Uploadinhoud gaat niet naar het taalmodel, alleen een eventuele vraag en teruggegeven bronpassages. De adapter voegt deze beperking expliciet aan uploaduitleg toe. De frontend toont modeltekst en noodzakelijke beperkingen compact boven de volledige meerderheidstekst; de gevalideerde passage blijft daarin gemarkeerd. Extra quoteblokken en citaatlinks worden niet herhaald, maar de bronverwijzingen blijven in de API aanwezig. Versies en UTF-16-markeringen blijven behouden. Geen modeltekst als bewijs van juridische juistheid presenteren.
