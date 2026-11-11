# Architectuurgids

## Huidige stand

De React/TypeScript-frontend in [`frontend/`](../frontend/) werkt lokaal met Vite en synthetische [fixtures](examples/search-response.json). De frontend heeft een chatinvoer, PDF/TXT-bijlage en drie openklapbare voorbeeldzaken met exacte tekstmarkeringen. Er zijn nog geen Rust-bronbestanden, SQLite-database, CI of werkende backendendpoints. De backendroute hieronder is **voorgenomen ontwerp**; alleen het frontendhoofdstuk beschrijft bestaande uitvoering.

De [README](../README.md) is het startpunt; [AGENTS.md](../AGENTS.md) bepaalt hoe agents samenwerken. Het contract is een productafspraak. Deze gids legt de samenhang, afwegingen en grenzen uit.

## Gebruik en geplande hoofdroute

Een gebruiker geeft een document en/of vraag. De app toont drie verschillende uitspraken, met per zaak de volledige tekst van het meerderheidsoordeel (majority opinion) en de best scorende passage gemarkeerd.

```mermaid
flowchart LR
  C[Texas JSON-corpus] --> I[Import en passageverdeling]
  I --> E[Lokale embeddings]
  E --> DB[(SQLite)]
  DB --> X[Volledige index in geheugen]
  U[Document en/of vraag] --> API[Rust / Axum]
  API --> Q[Invoer uitlezen en embedden]
  Q --> S[Alle passages vergelijken]
  X --> S
  S --> R[Top 3 unieke zaken en tekstposities]
  R --> F[Frontend toont volledige documenten]
  DB --> D[Volledige canonieke zaaktekst]
  D --> F
```

De React-interface staat in `frontend/`; `backend/` voor de Rust-service is nog gepland. Gedeeld werk zit in `docs/`; contractwijzigingen worden afgestemd voordat een agent erop gaat bouwen.

## Bestaande frontend: gesprek met lokale simulatie

[`frontend/src/main.tsx`](../frontend/src/main.tsx) kiest bij het starten een client en rendert de React-app. Standaard is dit de lokale mock in [`client.ts`](../frontend/src/client.ts); alleen `VITE_API_MODE=api` kiest de HTTP-client met configureerbare `VITE_API_BASE_URL` (standaard `http://127.0.0.1:8000`). Er zijn geen externe modelaanroepen, accounts of extra UI-libraries.

```mermaid
flowchart LR
  U[Eigen tekst en/of bijlage] --> A[React App: invoer en gesprek]
  A --> V[validateInput: bruikbare invoer, type en grootte]
  V --> M[Mockclient: vaste JSON-fixtures]
  M --> R[Drie openklapbare voorbeeldzaken]
  R --> D[Detail ophalen uit fixturearray]
  D --> G[Corpus-/tekstversie en exacte UTF-16-uitsnede controleren]
  G --> T[React-tekstnodes en markering]
```

[`App` in `app.tsx`](../frontend/src/app.tsx) houdt alleen het huidige gesprek en de bijlage in browsergeheugen. Een zoekopdracht voegt de eigen tekst en bestandsnaam toe aan het gesprek, blokkeert dubbele verzending tijdens laden en toont vervolgens de drie fixturezaken. Iedere `CaseResult` laadt zijn detail pas bij openen. Mislukte zoekopdrachten houden de invoer beschikbaar; fouten bij details worden bij die zaak getoond. Enter verstuurt, Shift+Enter maakt een nieuwe regel. Uploadknoppen, velden en uitklapknoppen hebben toegankelijke namen; de lay-out past zich aan kleinere schermen aan.

[`validateInput` in `search.ts`](../frontend/src/search.ts) trimt de vraag en accepteert PDF/TXT-extensies tot en met 10 MiB. Lege bestanden en ongeldige meegegeven bestanden blokkeren ook een geldige vraag. De mock leest de bestandsinhoud niet: een verkeerd benoemde, onleesbare PDF of scan wordt hier niet inhoudelijk herkend. Dat blijft backendwerk. De mock past `mode` wel aan naar `query`, `document` of `combined`, maar geeft voor elke invoer dezelfde drie **synthetische** resultaten. Dit is geen implementatie of validatie van de juridische zoekmethode.

[`getPassageParts` in `search.ts`](../frontend/src/search.ts) vergelijkt corpusversie, tekstversie en zaak-ID en controleert dat de exacte UTF-16-uitsnede overeenkomt met `passage.text`. De bron wordt niet opnieuw genormaliseerd en React rendert tekst veilig met een `<mark>`. Bij oude versies of onjuiste posities toont de UI een fout met het verzoek opnieuw te zoeken; de gebruiker start die nieuwe opdracht zelf.

De HTTP-client gebruikt `FormData` zonder een eigen multipart-Content-Type, volgt de aangeboden `case_url` en toont backendfoutberichten. Deze code is met een onderschepte HTTP-grens getest; een echte backendintegratie is nog niet uitgevoerd. De API-schemas blijven vastgelegd in [OpenAPI](openapi.yaml).

Vanuit `frontend/`: `npm ci`, `npm run dev`, `npm test` en `npm run build`. De devserver bindt aan `127.0.0.1:5173`; Vite wisselt niet stilzwijgend naar een andere poort. Tests in [`search.test.ts`](../frontend/src/search.test.ts) controleren invoermodi, bestandgrenzen, mock/details, multipart en versie-/Unicode-markeringen; [`app.test.ts`](../frontend/src/app.test.ts) controleert de React-route van eigen tekst tot drie documenten en bronmarkering, plus herstel na invoer-/zoekfouten. De productiebuild voert ook TypeScript-controle uit. De lokale frontend is hiermee uitvoerbaar; backendimport en backendtests ontbreken nog.

## Corpus, opslag en index

Het lokale corpus staat in `/Users/R0GUE/Downloads/texas-criminal-reports`. De eerdere data-inspectie vond 135 historische uitspraken van het Texas Court of Criminal Appeals uit 1892–1893, volledige JSON-teksten en bijbehorende HTML. De volumemetadata vermeldt foutief 1992–1993; import gebruikt `decision_date` per zaak.

De import moet zaak-ID, metadata, bronidentificatie en oorspronkelijke opinion-typen bewaren. De eerste zoekindex gebruikt de majority opinion, het oordeel van de meerderheid. Concurrence en dissent blijven herkenbaar en worden niet ongemerkt met het meerderheidsoordeel vermengd.

SQLite zal zaken, canonieke tekst, passages en embeddings bewaren. Per zaak bepaalt `text_version` de versie van de canonieke tekst; `corpus_version` identificeert de complete geïmporteerde dataset en verwerking. Model, modelversie en passageverdeling worden bij de index vastgelegd. Herimport is herhaalbaar en mag geen dubbele zaken maken. Uploads worden alleen voor de zoekopdracht verwerkt en hoeven niet duurzaam te worden opgeslagen.

De hele index wordt bij serverstart in geheugen geladen. Readiness volgt pas nadat alle 135 afgesproken zaken en hun geldige passages aanwezig zijn. Een partiële of kapotte index geeft een fout; die mag niet als volledige top-driezoekfunctie worden gepresenteerd.

## Embeddings en zoekmethode

Corpus en invoer gebruiken hetzelfde lokale embeddingmodel via fastembed. De COA-kern is technisch herbruikbaar; de precieze modelkeuze en geschiktheid voor juridisch Engels moeten bij implementatie en kwaliteitsevaluatie worden vastgelegd. Een modeldownload en compilatie kunnen nodig zijn; er zijn nog geen doorlooptijden gemeten.

Uitspraken en uploads worden in korte, deels overlappende passages verdeeld, binnen de invoerlimiet van het gekozen model. Tekstposities moeten naar de opgeslagen canonieke tekst blijven verwijzen. Niet stilzwijgend lange teksten afkappen.

De eerste rankingmethode, `cosine-max-v1`, werkt als volgt:

1. **Vraag:** cosinusovereenkomst tussen vraagvector en iedere corpuspassage.
2. **Document:** normaliseer het gemiddelde van de documentpassagevectoren opnieuw en vergelijk dat met iedere corpuspassage.
3. **Beide:** `0.7 * query_score + 0.3 * document_score`, met bovenstaande cosinusovereenkomsten.
4. Vergelijk alle passages. De score van een zaak is de hoogste passagescore binnen die zaak. Kies bij gelijke passagescores de laagste `passage_id` (lexicografisch).
5. Sorteer alle zaken op score aflopend; bij gelijke scores op `case_id` lexicografisch oplopend. Geef precies de eerste drie terug.

De gewichten zijn een voorlopige ontwerpkeuze, geen gevalideerd optimum. Nulvectoren en onbruikbare invoer mogen geen NaN-scores opleveren; geef dan een duidelijke fout.

Er is geen benaderende vectorindex of voorafgaande kandidaatselectie nodig bij deze corpusomvang. De harde garantie is **de drie hoogst scorende unieke zaken binnen de volledige afgesproken index, volgens deze methode**. Deze garantie zegt niet dat de drie zaken voor iedere juridische vraag inhoudelijk de meest relevante zijn. Er is nog geen gevalideerde ondergrens voor relevantie; een succesvolle zoekopdracht kan lage scores bevatten.

## Documenten en markeerbare passages

Het zoekresultaat geeft per zaak één originele passage, een stabiele passage-ID en `start_utf16`/`end_utf16` terug. Het detailendpoint geeft de volledige canonieke tekst van het meerderheidsoordeel; afwijkende of aanvullende opinions horen niet bij deze tekst. Tekstposities gelden voor die exacte tekst en `text_version`; het einde is exclusief. UTF-16-eenheden sluiten aan bij JavaScript `slice`, ook bij tekens buiten de BMP. Rust moet de eenheden expliciet bepalen; UTF-8-byteposities zijn niet uitwisselbaar met deze posities.

De backend normaliseert tekst één keer bij import, bewaart die tekst en berekent alle passagegrenzen daarop. De frontend normaliseert deze tekst niet opnieuw en controleert versies vóór het markeren. Dit levert leesbare volledige documenten met markeringen op; een originele PDF-layout of PDF-coördinaten zijn niet onderdeel van dit corpuscontract.

## Gericht hergebruik uit COA

De code-inspectie in `../coa` wees deze bestaande bouwstenen aan:

| Onderdeel | Gecontroleerd bestaand codepad | Betekenis voor deze app |
|---|---|---|
| Embeddings en zoeken | `../coa/src/lib.rs`, `Index::load`, `Index::search_with_top_k` | Zoekkern als vertrekpunt; ingebouwde datasetloader vervangen. |
| Cosinus en sortering | `../coa/src/ranking.rs` | Domeinonafhankelijke berekening gericht overnemen. |
| Eerst zoeken, dan modelcontext | `../coa/src/experiment/runner.rs`, `dense_once` | Alleen patroon; de experimentrunner niet meenemen. |
| Bron/citaatcontrole | `../coa/src/experiment/arms.rs`, `validate_answer` | Pas relevant bij een latere uitbreiding met antwoordgeneratie. |

Deze paden liggen buiten deze repo en zijn daarom oriëntatiepunten, geen beschikbare projectmodules. Verifieer de actuele COA-code opnieuw voordat je iets overneemt. De COA-parser verwerkt maximaal vijf ingebouwde Markdown-documenten en biedt geen algemene PDF-upload of SQLite-opslag. Codex-processen, MCP, activiteitprompts en experimentinfrastructuur worden niet overgenomen.

## Scope en beperkingen

- Alleen UTF-8-TXT en PDF met uitleesbare tekst. OCR voor scans is niet onderdeel van de eerste versie.
- Lokale embeddings en ophalen van zaken; geen gegenereerd juridisch advies en geen Orq- of Codex-aanroep nodig.
- Het corpus is klein en historisch; resultaten zijn geen volledig of actueel overzicht van Texas-rechtspraak.
- Een gemiddelde documentvector kan deelonderwerpen vervagen. De beste passage per zaak kan lange uitspraken bevoordelen. Beoordeel beide met inhoudelijke voorbeelden.
- Overeenkomende scores en tekstmarkeringen bewijzen geen juridische juistheid, volledigheid of toepasselijkheid.

## Verificatie bij implementatie

Frontendtestcommando's staan hierboven; voor de backend is er nog geen projecttestcommando. De volledige implementatie moet aantoonbaar maken:

- alle drie invoermodi, PDF/TXT en duidelijke fouten bij onbruikbare invoer;
- precies drie unieke zaken, volledige scoring en deterministische gelijke scores;
- dezelfde corpus- en tekstversies, met UTF-16-posities die exact de aangeboden passage selecteren;
- herhaalbare import en dezelfde beschikbare index na herstart;
- onafhankelijke controle van ranking met bekende vectoren én aparte inhoudelijke beoordeling;
- een echte HTTP-upload, zoeken en ophalen van volledige documenten.

De frontendchecks draaien lokaal; CI bestaat nog niet. Backendcontract- en fixturechecks moeten later op de gekozen backendtools aansluiten. De canonieke documenten zijn nog geen mechanisch afgedwongen mergegate.

## Recente architectuurwijzigingen

- 2026-11-11: minimale React/TypeScript-chatfrontend met Vite toegevoegd. Lokale mock en toekomstige HTTP-client zijn gescheiden; eigen tekst/bijlage, laad-/foutstatus, drie synthetische documenten en versiegecontroleerde UTF-16-markeringen zijn lokaal geïmplementeerd. Backend en zoekkwaliteit blijven ongeïmplementeerd.

- 2026-11-11: repo-overdracht en API-ontwerp toegevoegd. Scope vastgelegd als document en/of vraag, exact drie unieke zaken en volledige majority-opinionteksten met UTF-16-markeerposities. Nog geen runtime-implementatie.
