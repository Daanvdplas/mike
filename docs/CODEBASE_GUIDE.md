# Architectuurgids

## Huidige stand

De React/TypeScript-frontend in [`frontend/`](../frontend/) werkt lokaal met Vite en synthetische [fixtures](examples/search-response.json). De frontend heeft een chatinvoer, PDF/TXT-bijlage, drie klikbare documentvoorbeelden onder de invoerbox en een aparte leesweergave met exacte tekstmarkeringen. De [evaluatieviewer](evals/index.html) toont 25 concrete ontwerpbeschrijvingen; vaste kandidaatlabels en de runner ontbreken nog. Er zijn nog geen Rust-bronbestanden, SQLite-database of werkende backendendpoints. De backendroute hieronder is **voorgenomen ontwerp**; de frontend- en viewerhoofdstukken beschrijven bestaande uitvoering.

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

## Bestaande frontend: invoer, documentvoorbeelden en leesweergave

[`frontend/src/main.tsx`](../frontend/src/main.tsx) kiest bij het starten een client en rendert de React-app. Standaard is dit de lokale mock in [`client.ts`](../frontend/src/client.ts); alleen `VITE_API_MODE=api` kiest de HTTP-client met configureerbare `VITE_API_BASE_URL` (standaard `http://127.0.0.1:8000`). Er zijn geen externe modelaanroepen, accounts of extra UI-libraries.

```mermaid
flowchart LR
  U[Eigen tekst en/of bijlage] --> A[React App: invoer en gesprek]
  A --> V[validateInput: bruikbare invoer, type en grootte]
  V --> M[Mockclient: vaste JSON-fixtures]
  M --> R[Drie documentvoorbeelden onder de invoerbox]
  R --> D[Klik opent aparte reader en haalt detail op]
  D --> G[Corpus-/tekstversie en exacte UTF-16-uitsnede controleren]
  G --> T[Volledige tekst met markering en brononderbouwing]
  T --> B[Terug naar resultaten en oorspronkelijke focus]
```

[`App` in `app.tsx`](../frontend/src/app.tsx) houdt de invoer, bijlage en laatste succesvolle zoekresponse alleen in browsergeheugen. De naam Mike, huidige vraag en invoerbox blijven het vertrekpunt. Een zoekopdracht blokkeert dubbele verzending tijdens laden en toont daaronder precies drie klikbare documentvoorbeelden. Op desktop staan ze naast elkaar; op smalle schermen onder elkaar. Een volgende succesvolle zoekopdracht vervangt de vorige resultaten. Er is geen stapelende chatgeschiedenis boven de invoerbox. Mislukte zoekopdrachten houden de invoer en eventuele vorige resultaten beschikbaar. Enter verstuurt, Shift+Enter maakt een nieuwe regel.

Klikken op een document opent `DocumentReader` als aparte leesweergave op dezelfde pagina. De invoer en resultaten zijn dan verborgen, niet verwijderd. De reader haalt de zaak pas op bij openen, toont laad-/foutstatus en negeert een nog lopende detailresponse na sluiten. De volledige aanwezige meerderheidstekst blijft onverkort beschikbaar in de gewone paginascroll. ‘Terug naar resultaten’ herstelt focus op het gekozen document en de eerdere scrollpositie; readeropenen verplaatst focus naar de documenttitel. Upload-, document- en terugknoppen hebben toegankelijke namen.

De voorbeelden gebruiken een sober pagina-icoon, zaakmetadata en een excerpt uit de exacte gevonden passage. Ze stellen geen originele PDF, officiële paginering of gerechtszegel voor. In de reader toont ‘Waarom dit document?’ die bronpassage en de overeenkomstscore. Dit is brononderbouwing, geen vergelijking met een aangewezen uploadpassage en geen gegenereerde juridische uitleg. Het huidige contract levert daarvoor geen velden. De mock meldt compact bij de resultaten dat het voorbeelden zijn en geen analyse van de invoer; ook de reader benoemt zijn onderbouwing als voorbeeld. Er zijn geen extra fictieve juridische verklaringen of nieuwe contractvelden toegevoegd.

[`validateInput` in `search.ts`](../frontend/src/search.ts) trimt de vraag en accepteert PDF/TXT-extensies tot en met 10 MiB. Lege bestanden en ongeldige meegegeven bestanden blokkeren ook een geldige vraag. De mock leest de bestandsinhoud niet: een verkeerd benoemde, onleesbare PDF of scan wordt hier niet inhoudelijk herkend. Dat blijft backendwerk. De mock past `mode` wel aan naar `query`, `document` of `combined`, maar geeft voor elke invoer dezelfde drie **synthetische** resultaten. Dit is geen implementatie of validatie van de juridische zoekmethode.

[`getPassageParts` in `search.ts`](../frontend/src/search.ts) vergelijkt corpusversie, tekstversie en zaak-ID en controleert dat de exacte UTF-16-uitsnede overeenkomt met `passage.text`. De bron wordt niet opnieuw genormaliseerd en React rendert tekst veilig met een `<mark>`. Bij oude versies of onjuiste posities toont de UI een fout met het verzoek opnieuw te zoeken; de gebruiker start die nieuwe opdracht zelf.

De HTTP-client gebruikt `FormData` zonder een eigen multipart-Content-Type, volgt de aangeboden `case_url` en toont backendfoutberichten. Deze code is met een onderschepte HTTP-grens getest; een echte backendintegratie is nog niet uitgevoerd. De API-schemas blijven vastgelegd in [OpenAPI](openapi.yaml).

Vanuit `frontend/`: `npm ci`, `npm run dev`, `npm test` en `npm run build`. De devserver bindt aan `127.0.0.1:5173`; Vite wisselt niet stilzwijgend naar een andere poort. Tests in [`search.test.ts`](../frontend/src/search.test.ts) controleren invoermodi, bestandgrenzen, mock/details, multipart en versie-/Unicode-markeringen; [`app.test.ts`](../frontend/src/app.test.ts) controleert de React-route van eigen tekst naar drie documenten onder de invoerbox, volledige veilige bronweergave en brononderbouwing, terugkeerfocus, vervanging van de vorige resultaten en herstel na invoer-/zoekfouten. De productiebuild voert ook TypeScript-controle uit. De lokale frontend is hiermee uitvoerbaar; backendimport en backendtests ontbreken nog.

## Evaluatiedocumentatie en viewer

[EVALUATIEOPDRACHT.md](EVALUATIEOPDRACHT.md) is de canonieke specificatie van de beoordelingsafspraken. [evals/scenarios.json](evals/scenarios.json) bevat 25 concrete ontwerpbeschrijvingen met invoermodus, bronzaak, exact invoerfragment, Engelse zoekvraag waar van toepassing, verwacht juridisch gedrag en onderbouwing. [evals/index.html](evals/index.html) is de gegenereerde, klikbare leesweergave uit beide bronnen. De viewer hoort bij de projectdocumentatie en staat los van de React-productinterface en de synthetische productfixtures.

Het startoverzicht toont alle 25 ontwerp-evals als compacte rijen met ID, titel en invoermodus. Een klik toont de concrete input, het verwachte gedrag, waarom dit wordt getest en het bronbewijs. Bij query-only staat de bronzaak alleen onder herkomst; de exacte Engelse vraag is de invoer en de Nederlandse versie uitsluitend een leesvertaling. Bij documentinvoer verwijzen veld en SHA-256 naar de volledige majority opinion; de zichtbare quote is een leesfragment. Testcategorieën, varianten en de volledige opdracht staan secundair onder Afspraken.

[evals/build.py](evals/build.py) maakt de HTML uit de canonieke opdracht en scenariocatalogus. De generator controleert onder meer scenario-ID’s, verplichte inhoud en invoermodi; hij beoordeelt geen juridische kandidaatmatches. Voer vanuit de reporoot `python3 docs/evals/build.py` uit na inhoudswijzigingen; `python3 docs/evals/build.py --check` controleert of de opgeslagen weergave nog overeenkomt. Generatorchecks draaien met `python3 -m unittest discover -s docs/evals -p 'test_*.py'`. Onderhoud bron en afgeleide HTML in dezelfde changeset. De [AGENTS-afspraken](../AGENTS.md#evaluatiedocumentatie-onderhouden) bepalen hoe toekomstige wijzigingen aan invoermodi, beoordelingsregels, status, labels en runs worden verwerkt.

[De documentatieworkflow](../.github/workflows/eval-docs-checks.yml) voert synchronisatie- en generatorchecks uit op pull requests en pushes naar `main` die de bron, viewerbestanden of workflow veranderen. De check genereert niet eerst opnieuw: verouderde opgeslagen HTML faalt dus zichtbaar. Er worden geen corpusdata, modellen of benchmarkruns geladen.

De viewer presenteert concrete ontwerpbeschrijvingen, geen beoordeelde retrievalbenchmark of gemeten scores. Kandidaten met gecontroleerde relevantielabels, een metriekberekening en een uitvoerbare evaluatierunner moeten nog worden gebouwd. De zichtbare ontwerpen zijn ontwikkelmateriaal en kunnen niet als verborgen testset worden gepresenteerd. Een statische HTML-pagina start geen lokaal backendproces. De generatiecheck controleert alleen documentatiesynchronisatie; daadwerkelijke retrievalkwaliteit vraagt later onafhankelijke labels en echte runs volgens de opdracht.

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

De frontendchecks draaien lokaal. De evaluatiedocumentatie heeft een automatische synchronisatiecheck; backendcontract- en fixturechecks moeten later op de gekozen backendtools aansluiten. Een geslaagde documentatiecheck bewijst geen correcte backend of juridische zoekkwaliteit.

## Recente architectuurwijzigingen

- 2026-11-11: centrale evaluatiedocumentatie toegevoegd met canonieke Markdownbron, gegenereerde HTML-viewer en synchronisatiecheck in CI. De scenariocatalogus toont 25 concrete brononderbouwde ontwerpen; kandidaatlabels en runner blijven gepland. Er zijn geen benchmarkresultaten toegevoegd.

- 2026-11-11: documentpresentatie herzien: laatste zoekresultaten onder de invoerbox, drie pagina-voorbeelden en een aparte volledige reader met terugkeerfocus. Bronpassage en score vormen de onderbouwing; de simulatie voegt geen juridische vergelijkredenen toe.

- 2026-11-11: minimale React/TypeScript-chatfrontend met Vite toegevoegd. Lokale mock en toekomstige HTTP-client zijn gescheiden; eigen tekst/bijlage, laad-/foutstatus, drie synthetische documenten en versiegecontroleerde UTF-16-markeringen zijn lokaal geïmplementeerd. Backend en zoekkwaliteit blijven ongeïmplementeerd.

- 2026-11-11: repo-overdracht en API-ontwerp toegevoegd. Scope vastgelegd als document en/of vraag, exact drie unieke zaken en volledige majority-opinionteksten met UTF-16-markeerposities. Nog geen runtime-implementatie.
