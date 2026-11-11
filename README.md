# Texas Legal Document Similarity Finder

Prototypecase voor een AI-consultancy: voer een juridisch document, een zoekvraag of beide in en bekijk de drie hoogst scorende uitspraken uit het aangeleverde Texas-corpus. De frontend toont per zaak de volledige tekst van het meerderheidsoordeel (majority opinion) en markeert de gevonden passages.

**Status: de volledige Rust/SQLite/BGE-demo is onafhankelijk via echte HTTP en de browser gecontroleerd en klaar voor de gebruiker om te testen.** Open de [demo op 5173](http://127.0.0.1:5173/); de frontend gebruikt standaard de echte lokale API. De backend draait op `127.0.0.1:8000` onder de resourceguard, maximaal twee uur. De afzonderlijke API-preview op 5174 kan daarnaast beschikbaar zijn. Fictieve resultaten zijn uitsluitend beschikbaar via een expliciete mockstart. JSON-fixtures zijn synthetisch; de API-preview gebruikt de 135 echte corpuszaken.

## Begin hier

- [AGENTS.md](AGENTS.md): werkafspraken, eigenaarschap en onderhoud van documentatie.
- [Backendafspraak voor de frontend](docs/FRONTEND_BACKEND.md): korte overdracht om parallel te kunnen bouwen.
- [OpenAPI](docs/openapi.yaml): het canonieke API-contract, ook beschikbaar via `/openapi.json`.
- [Architectuurgids](docs/CODEBASE_GUIDE.md): ontwerp, zoekmethode, grenzen en actuele implementatiestatus.
- [Evaluatieoverzicht](docs/evals/index.html): alle 25 concrete ontwerp-evals, met input en verwacht gedrag na aanklikken; [de opdracht](docs/EVALUATIEOPDRACHT.md) bevat de beoordelingsafspraken.
- [Hoofdissues en subissues](https://github.com/Daanvdplas/adami-case/issues): uitvoering en voortgang.

## Afgesproken scope

- Rust/Axum-backend, SQLite en lokale embeddings via fastembed.
- PDF/TXT-upload, alleen een vraag of beide; minimaal één bruikbare invoer.
- Precies drie unieke zaken met metadata, overeenkomstscore en gemarkeerde passage in de volledige tekst van het meerderheidsoordeel.
- Exact zoeken over alle geïndexeerde passages. De garantie is de hoogste drie scores volgens onze zoekmethode binnen dit corpus; inhoudelijke juridische relevantie wordt apart beoordeeld.
- De Rust-backend staat in `backend/`; de gemergde React/TypeScript-frontend met Vite staat in `frontend/`.
- Geen gegenereerd juridisch advies. Een optionele, expliciet geautoriseerde Orq-sidecar kan de bestaande lokale zoekresultaten toelichten; de gewone zoek-API blijft zonder modelgeneratie werken. Geen Codex/MCP nodig. Docker is optioneel.
- Operationele invoergrenzen: document 10 MiB, vraag 1 MiB UTF-8, totale multipartrequest 12 MiB en uitgelezen PDF-tekst 20 MiB. Overschrijdingen geven een fout; tekst wordt niet stil afgekapt.

## Data en hergebruik

Het aangeleverde corpus staat lokaal in `/Users/R0GUE/Downloads/texas-criminal-reports`: 135 uitspraken van het Texas Court of Criminal Appeals uit 1892–1893, in JSON met volledige tekst en bijbehorende HTML. Gebruik de uitspraakdatum (`decision_date`); de volumemetadata noemt foutief 1992–1993. Ruwe data, uploads en databases zijn nog niet opgenomen in deze repo.

De aangeleverde [CAP-link](https://case.law/caselaw/#florida) heeft een Florida-anchor; de lokale dataset is Texas en is het afgesproken corpus. Bewaar bij import de bronidentificatie en metadata. De demo geeft geen overzicht van actuele of volledige Texas-jurisprudentie.

`../coa` bevat een herbruikbare Rust-zoekkern en een voorbeeld van eerst zoeken en daarna passages aan een model aanbieden. De nieuwe app neemt gericht zoekonderdelen over; de Codex/MCP-aansturing en COA-specifieke dataset niet. Zie de architectuurgids voor de gecontroleerde codepaden.

## Backendbasis controleren

Benodigd: Rust 1.94.1 met clippy en rustfmt; nightly met rustfmt voor de formatteringsafspraak. De eerste build downloadt Rust-dependencies en de ONNX-runtime, maar geen embeddingmodel. Voer vanuit de reporoot uit:

```sh
export CARGO_BUILD_JOBS=2
cargo +nightly fmt --manifest-path backend/Cargo.toml --all
cargo +1.94.1 fmt --manifest-path backend/Cargo.toml --all --check
cargo +1.94.1 clippy --manifest-path backend/Cargo.toml --locked --all-targets -- -D warnings
cargo +1.94.1 test --manifest-path backend/Cargo.toml --locked -- --test-threads=2
python3 -m unittest discover -s backend/scripts -p 'test_*.py'
cargo +1.94.1 build --manifest-path backend/Cargo.toml --locked
```

Op de gereviewde codehead `9ef3bf9` slaagden 45 Rust-tests, vijf Python-beleidstests, fmt, clippy, build en Linux-CI. Zes echte model-/diagnosticchecks staan bewust apart van de standaardtestset. De standaardtests gebruiken de echte router, multipartverwerking en PDF/TXT-extractie. Alleen de zoekengine wordt bij de HTTP-tests vervangen door de synthetische contractfixtures; deze tests bewijzen geen modelkwaliteit. De [backendworkflow](.github/workflows/backend-checks.yml) voert formattering, clippy, deterministische tests en build uit zonder embeddingmodel te laden.

## Nu parallel beginnen

De frontend gebruikt [de korte backendafspraak](docs/FRONTEND_BACKEND.md); fixtures zijn alleen voor expliciete mockmodus. De bestaande frontend is via de gewone main-integratie overgenomen; de backend-PR voegt geen nieuwe frontendfunctionaliteit toe.

## Backend gebruiken

De normale frontend gebruikt 5173/8000; de aparte API-preview op 5174 kan daarnaast draaien. De onderstaande commando’s zijn voor een latere herstart: stop eerst de bestaande guard en voer nooit twee modeljobs tegelijk uit. Binary, index en model zijn op deze Mac vooraf voorbereid; er wordt niet binnen het modelbudget gecompileerd.

```sh
export ADAMI_BINARY="$HOME/Library/Caches/adami-case/cargo-final-review/debug/texas-case-finder"
export ADAMI_DB_PATH="$HOME/Library/Caches/adami-case/final-q-review/cases.sqlite"
export ADAMI_CACHE_DIR="$HOME/Library/Caches/adami-case/fastembed"
export ADAMI_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
```

Op deze Mac is de nieuwe index vooraf berekend: 135 zaken en 578 passages. Een eerste import downloadt het model als het ontbreekt. Voor een verse index voer je de volgende import afzonderlijk uit, zonder draaiende modelserver; bij hergebruik van de bestaande index is dit niet nodig.

```sh
python3 backend/scripts/resource_guard.py \
  --label adami-import --timeout-seconds 600 \
  --report "$HOME/Library/Caches/adami-case/import-guard.json" \
  --log "$HOME/Library/Caches/adami-case/import.log" \
  -- "$ADAMI_BINARY" import /Users/R0GUE/Downloads/texas-criminal-reports
```

Import vervangt de index in één transactie. Start de server opnieuw na import; de server herindexeert nooit stilzwijgend. De demo gebruikt alleen de bestaande database en lokale modelcache. Start de server voor maximaal twee uur met dezelfde geheugenbewaking:

```sh
python3 backend/scripts/resource_guard.py \
  --label adami-preview --serve-preview --timeout-seconds 7200 \
  --report "$HOME/Library/Caches/adami-case/preview-guard.json" \
  --log "$HOME/Library/Caches/adami-case/preview.log" \
  -- "$ADAMI_BINARY" serve
```

Stop de preview met **Ctrl+C in die terminal**. De guard ruimt uitsluitend zijn eigen procesgroep op. Zonder `--serve-preview` blijven tests en imports begrensd op maximaal 600 seconden. De langere modus accepteert alleen een concreet backendpad gevolgd door `serve`; geen shell, Cargo of losse PATH-alias. De RSS-grens blijft 1536 MiB, geheugendruk moet normaal blijven en swap mag niet met 128 MiB groeien. De guard stopt ook bij meetfouten of de deadline. Dit is geen procesisolatie of absolute garantie dat een korte geheugenpiek onmogelijk is.

In een tweede terminal kun je de HTTP-API gebruiken:

```sh
curl http://127.0.0.1:8000/api/health
curl --form-string 'query=trial evidence' http://127.0.0.1:8000/api/search
curl -F 'document=@/pad/naar/zaak.pdf' --form-string 'query=witness testimony' http://127.0.0.1:8000/api/search
```

Gebruik voor zaakdetails de `case_url` uit het zoekresultaat, op dezelfde backendbasis-URL. Een ontbrekende, corrupte of onvolledige database geeft 503-readiness en geen fictieve zoekresultaten; `/openapi.json` blijft bereikbaar. Het CLI-commando `search QUESTION` gebruikt dezelfde engine en hoort, net als import, uitsluitend in een aparte bewaakte job wanneer de server niet draait.

| Instelling | Standaard |
|---|---|
| `ADAMI_DB_PATH` | `data/cases.sqlite3`, relatief aan de huidige werkmap |
| `ADAMI_CACHE_DIR` | `.fastembed_cache`, relatief aan de huidige werkmap |
| `ADAMI_BIND_ADDR` | `127.0.0.1:8000` |
| `ADAMI_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |

CORS-origins zijn kommagescheiden HTTP(S)-origins zonder pad. Er zijn geen API-sleutels of externe modelaanroepen nodig. De modelcache, database en guardverslagen horen buiten Git.

## Frontend lokaal proberen

Gebruik Node.js 22.12+ (of 20.19+). Vanuit de repository:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/`. De ontwikkelserver luistert alleen lokaal en gebruikt standaard de echte backend op `http://127.0.0.1:8000`. Typ/plak eigen tekst, voeg een PDF/TXT van maximaal 10 MiB toe, of combineer beide. De backend moet met een complete index gereed zijn. Zoeken toont precies drie echte corpuszaken als documentvoorbeelden onder de invoerbox. Open een document om de volledige aangeleverde meerderheidstekst met markering te lezen; de terugknop brengt je naar de resultaten. ‘Waarom dit document?’ toont de exacte gevonden bronpassage en overeenkomstscore, geen gegenereerde juridische verklaring.

Een API-, index- of verbindingsfout wordt als fout getoond. De frontend schakelt nooit stilzwijgend over op fixtures. Met `VITE_API_BASE_URL` kun je een andere backendbasis instellen; `frontend/.env.example` toont de normale API-configuratie. Een eventuele bestaande `frontend/.env.local` met `VITE_API_MODE=mock` kiest nog steeds expliciet de fictieve modus: verwijder die instelling of zet haar op `api` voor echt zoeken.

Alleen voor los frontendwerk zonder backend:

```sh
npm run dev:mock
```

Deze expliciete mockstart gebruikt dezelfde poort 5173; stop eerst de eigen frontendserver. De mock toont altijd dezelfde drie verzonnen zaken en leest, verstuurt of bewaart bestandsinhoud niet. De UI benoemt de resultaten als voorbeelden zonder analyse van je invoer. Een bestand wordt daarin alleen op extensie en grootte gecontroleerd. Inhoudelijke PDF/TXT-validatie en echte zoekresultaten verlopen uitsluitend via de backend. Mockteksten zijn kort en bewijzen geen leesbaarheid van lange echte uitspraken.

Gecontroleerde frontendchecks:

```sh
npm test
npm run build
```

`npm test` controleert de standaardkeuze voor de echte API, expliciete mockkeuze, foutdoorgifte zonder fictieve terugval, invoermodi en grenzen, mock/API-uitwisseling, React-interacties en UTF-16-markeringen met versiecontrole. De build voert TypeScript-controle uit en schrijft `frontend/dist/` (genegeerd door Git).

Een extra API-preview kan naast de gewone frontend afzonderlijk op 5174 worden gestart. Dit is niet nodig om op 5173 echte zoekresultaten te krijgen. Start die zo vanuit de reporoot, nadat de bewaakte backend draait en CORS voor 5174 is toegestaan:

```sh
cd frontend
VITE_API_MODE=api VITE_API_BASE_URL=http://127.0.0.1:8000 node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort
```

Deze modus verstuurt uploads naar de lokale backend en toont echte corpusresultaten. Stop alleen deze Vite-preview met Ctrl+C in zijn eigen terminal. De standaardmodus is de echte API; uitsluitend `VITE_API_MODE=mock` kiest fixtures. Zie [de backendafspraak](docs/FRONTEND_BACKEND.md).

## Optionele Orq-uitleg apart proberen

De Orq-uitbreiding draait als kleine Python-stdlib-adapter op `127.0.0.1:18000`, naast de bestaande bewaakte Rust-zoekbackend op 8000. Hij laadt geen tweede embeddingmodel en bouwt geen index. Een taalmodel roept de vaste `search_cases`-tool aan; de adapter stuurt daarbij de oorspronkelijke multipartinvoer ongewijzigd naar de lokale backend. De drie zaak-ID’s, volgorde, scores, bronteksten en versies blijven behouden.

Gebruik uitsluitend een serverzijdige `ORQ_API_KEY`, of `ORQ_API_KEY_FILE` naar een privébestand buiten Git. Voorbeeldstart vanuit de aparte checkout, terwijl de bestaande backend draait:

```sh
ORQ_API_KEY_FILE=/pad/buiten/de/repo/private-orq-key \
  python3 backend/scripts/orq_proxy.py --max-model-requests 20
```

Model: `openai/gpt-4.1-mini-2025-04-14`, via `https://my.orq.ai/v3/router/responses`. Dit exacte catalogusmodel is met echte tool- en schema-aanroepen gecontroleerd. Een andere keuze kan met `ORQ_MODEL` of `--model`, maar die modeltoegang en functies moeten apart worden gecontroleerd. Normaal zijn er twee providerrequests per zoekopdracht; elke providerrequest heeft 30 seconden timeout en de adapter verwerkt één zoekopdracht tegelijk. Het procesbudget telt maximaal twintig providerrequests standaard en is instelbaar; na uitputting blijven echte zoekresultaten beschikbaar met uitlegstatus `unavailable`. Het budget is geen prijsplafond.

In een tweede terminal:

```sh
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:18000 node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175 --strictPort
```

Open `http://127.0.0.1:5175/`. De bestaande hoofdmapdemo op 5173 en extra preview op 5174 blijven afzonderlijk werken. De Orq-reader toont één compacte modeltoelichting met noodzakelijke beperkingen boven de volledige tekst; de gevonden passage blijft daarin gemarkeerd, zonder extra quote of spronglink. Het model retourneert alleen bestaande passage-ID’s; de server vult de citaten uit de oorspronkelijke passage in. Onbekende zaken, verkeerde passage-ID’s of ongeldige modeluitvoer maken de uitleg `unavailable`; er worden nooit zaken of citaten verzonnen als terugval.

Alleen de vraag en gevonden bronpassages gaan naar Orq. Uploadinhoud wordt niet aan het taalmodel gegeven; bij uploads meldt iedere uitleg dit expliciet. Deze toelichting bewijst geen juridische relevantie of juistheid. De bestaande UTF-16- en versiecontrole beschermt de volledige bronweergave. Sleutels, uploads en providerresponses worden niet naar Git of de frontend geschreven. `store: false` wordt meegestuurd; dit is geen garantie over logs of bewaarbeleid van de modelgateway/provider.

Modelvrije adapterchecks: `python3 -m unittest discover -s backend/scripts -p 'test_orq_proxy.py'`. Echte Orq-aanroepen verbruiken API-budget en horen uitsluitend bij een expliciet geautoriseerde live controle.

## Uitgevoerde controle en indicatieve zoekkwaliteit

De onafhankelijke eindcontrole omvatte 26 echte HTTP-controles en een browsertour op desktop en mobiel: vijf succesvolle zoek-POSTs, vijftien zaakdetails, alle drie volledige documenten met exacte markeringen, query/TXT/PDF/combinatie en herstel na een 422-fout. Zie [technisch bewijs en browserartefacten](https://github.com/Daanvdplas/adami-case/issues/16#issuecomment-6795249357).

De nieuwe, vooraf vastgelegde AI-doelmatchindicatie was 3/5 voor alleen een vraag, 4/5 voor alleen een document en 4/5 voor beide. De oude MiniLM-baseline van 0/15 blijft bewaard. De sets verschillen: deze aantallen vormen geen causale modelvergelijking, accuracy of recall. Er zijn onvolledige AI-relevantielabels en geen menselijke juridische referentie. Zie [evaluatiebewijs en beperkingen](https://github.com/Daanvdplas/adami-case/issues/15#issuecomment-6795249012).

## Evals bekijken en bijhouden

Open het [klikbare evaluatieoverzicht](docs/evals/index.html) in een browser. De startpagina toont alle 25 concrete ontwerpbeschrijvingen. Klik op een eval voor document en/of vraag, verwacht juridisch gedrag, reden en bronfragmenten uit het Texas-corpus. Dit zijn zichtbare ontwikkelontwerpen, geen verborgen testset. Vaste benchmarklabels en algemene meetresultaten ontbreken nog. De lokale evalserver hieronder maakt de vaste B1-referentiecontrole en E06 uitvoerbaar; de overige 24 ontwerpen blijven gepland.

Onderhoud de beoordelingsafspraken in [docs/EVALUATIEOPDRACHT.md](docs/EVALUATIEOPDRACHT.md) en de concrete ontwerpbeschrijvingen in [docs/evals/scenarios.json](docs/evals/scenarios.json). Genereer daarna de leesweergave opnieuw en controleer dat bron en HTML overeenkomen:

```sh
python3 docs/evals/build.py
python3 docs/evals/build.py --check
python3 -m unittest discover -s docs/evals -p 'test_*.py'
```

De [documentatie-CI](.github/workflows/eval-docs-checks.yml) voert de synchronisatiecheck en generatortests automatisch uit bij wijzigingen aan deze evaldocumentatie. Een verouderde HTML-weergave laat de check falen. Dit valideert de documentatie, niet de kwaliteit of uitvoering van de toekomstige evals. Zie de [onderhoudsafspraken](AGENTS.md#evaluatiedocumentatie-onderhouden).

## Evals uitvoeren op de webpagina

De lokale evalpagina biedt twee afzonderlijke controles. **Beroepsborgstelling met een opgeheven rechtbank** gebruikt een bestaande vraag uit de eerdere B1-queryset, zonder document of uitsluiting. Vóór de eerste run zijn **Cummings v. State (156040)** en **Neubauer v. State (156042)** als ongeordende verwachte resultaten vastgelegd in `docs/evals/deterministic_b1.json` (preregistratiecommit `f3d80b6`). De controle slaagt als beide tussen precies drie geldige unieke corpusresultaten staan. Een andere match blijft onbeoordeeld; er is geen AI-beoordelaar, precisiescore of claim over volledige juridische relevantie. Ongeldige resultaten geven een technische fout.

Daarnaast blijft **E06: bewijs van andere delicten** de aparte AI-eval uit de scenariolijst. Een klik haalt drie echte zoekresultaten op en doet één Orq-beoordeling met scores 0–3, korte redenen en letterlijke bronfragmenten. Het model kiest bronfragment-IDs; de code kopieert de tekst zelf. Dit blijft een AI-indicatie, geen menselijke juridische referentie of Recall/nDCG-benchmark.

Bouw eerst de backend met de gewone commando’s. Start daarna vanuit de reporoot met de bestaande index en modelcache:

```sh
python3 backend/scripts/evals_web.py --port 8798 \
  --binary "$PWD/backend/target/debug/texas-case-finder" \
  --database "$HOME/Library/Caches/adami-case/bge-static-q-safe/cases.sqlite" \
  --model-cache "$HOME/Library/Caches/adami-case/fastembed" \
  --corpus "$HOME/Downloads/texas-criminal-reports"
```

Gebruik bij een andere `CARGO_TARGET_DIR` de bijbehorende binary. Open **http://127.0.0.1:8798/**. B1 werkt zonder Orq-key en gebruikt alleen de gewone Rustzoekserver op 8000, onder de bestaande resourceguard. Voor de E06 AI-eval kun je `--ask-key` toevoegen (invoer zonder echo), of `ORQ_API_KEY` instellen; de key gaat niet naar de browser. Het vaste standaardmodel is `openai/gpt-4.1-mini-2025-04-14`; `ORQ_MODEL` en `ORQ_BASE_URL` zijn instelbaar. De Orq-uitlegadapter op 18000 wordt niet gebruikt.

E06 gebruikt uitsluitend de exacte Engelse vraag uit `docs/evals/scenarios.json`. De bronzaak 156133 wordt **vóór** de top drie uitgesloten via `search --exclude-case-id ID QUESTION`; er wordt geen verborgen brondocument aan de vraag toegevoegd. Deze afzonderlijke Rustzoekactie draait maximaal 600 seconden onder de bestaande resourceguard, zonder herindexering. De demo-server mag hierbij in rust blijven draaien; start geen andere modeljob of zoekactie tegelijk. De evalserver staat zelf slechts één run tegelijk toe.

Resultaten, bron-/modelversies en eventuele foutdiagnose blijven lokaal buiten Git onder `~/Library/Caches/adami-case/web-evals/`. De pagina onderscheidt een technisch voltooide run van de AI-scores: een afgeronde run kan zwakke of niet-relevante matches bevatten. Fouten worden getoond en niet als geslaagd ingevuld. Stop de evalserver met Ctrl+C in de eigen terminal. De bestaande docsservers blijven ongemoeid.

De losse commandlinetool `backend/scripts/retrieval_relevance.py` uit PR36 blijft beschikbaar voor één eigen vraag en/of UTF-8-tekstbestand; gebruik `--help`. Zij gebruikt dezelfde judge- en bronfragmentcontrole als de webpagina.
