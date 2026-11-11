# Wat de frontend van de backend kan verwachten

**Status: de router en PDF/TXT-extractie zijn getest; de echte engine en serverstart worden nog gekoppeld. Er draait nog geen backend.** Bouw nu met fixtures. [OpenAPI](openapi.yaml) is het canonieke contract; wijzigingen stemmen frontend- en backend-agent samen af.

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

De voorgenomen backend-URL is `http://127.0.0.1:8000`. Maak de frontend-base-URL configureerbaar. De backend zal CORS ondersteunen voor de afgesproken ontwikkelorigins, standaard `http://localhost:5173` en `http://127.0.0.1:5173`.

`GET /api/health` geeft pas 200 met `status: ready` als het volledige corpus beschikbaar is; anders 503. De runtime zal het contract aanbieden op `GET /openapi.json`. Geen API-key nodig voor deze lokale demo; er hoort geen Orq-key in de frontend.
