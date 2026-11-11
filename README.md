# Texas Legal Document Similarity Finder

Prototypecase voor een AI-consultancy: voer een juridisch document, een zoekvraag of beide in en bekijk de drie hoogst scorende uitspraken uit het aangeleverde Texas-corpus. De frontend toont per zaak de volledige tekst van het meerderheidsoordeel (majority opinion) en markeert de gevonden passages.

**Featurestatus:** deze branch voegt een selecteerbare head-matterzoekmethode toe naast de bestaande opinion-chunks. De aparte dual-index en de API-/browserdoorloop zijn onafhankelijk gecontroleerd; zie de verificatie onderaan. De tijdelijke featurepreview op 5177/8001/8799 is daarna gestopt en de oorspronkelijke demo op 8000 is hersteld. Bestaande databases en binaries zijn behouden.

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

Deze featurebranch vereist indexformaat 3 met zowel majority opinions als afzonderlijke head matter. Gebruik een nieuw databasepad; overschrijf de bestaande majority-only demo-index niet. Een oude of onvolledige index geeft 503 vóór modelladen en wordt nooit stil herbouwd.

Bouw eerst buiten het modelbudget met de backendchecks hierboven. Gebruik voor deze Mac vervolgens:

```sh
export ADAMI_BINARY="$HOME/Library/Caches/adami-case/cargo-head-matter/debug/texas-case-finder"
export ADAMI_DB_PATH="$HOME/Library/Caches/adami-case/head-matter-search/cases.sqlite"
export ADAMI_CACHE_DIR="$HOME/Library/Caches/adami-case/fastembed"
export ADAMI_BIND_ADDR="127.0.0.1:8001"
export ADAMI_CORS_ORIGINS="http://localhost:5177,http://127.0.0.1:5177"
```

Voer uitsluitend één native modeljob tegelijk uit. Stop de bestaande guard netjes vóór import; start geen import of CLIzoekactie naast een modelserver. De oude demo gebruikt een aparte binary en database op 8000. De featurepreview mag pas starten wanneer die andere modeldemo netjes is gestopt of haar guard vanzelf is afgelopen. Na de afgeronde featurecontrole is de oorspronkelijke demo hersteld; reserveer opnieuw het exclusieve modelslot voordat je de featurebackend herstart.

```sh
python3 backend/scripts/resource_guard.py \
  --label head-matter-import --timeout-seconds 600 \
  --report "$HOME/Library/Caches/adami-case/head-matter-search/import-guard.json" \
  --log "$HOME/Library/Caches/adami-case/head-matter-search/import.log" \
  -- "$ADAMI_BINARY" import /Users/R0GUE/Downloads/texas-criminal-reports
```

Import gebruikt opeenvolgende subprocessen van maximaal 256 passages. Alleen de huidige worker laadt het model; de ouder houdt bronrecords en ontvangen vectoren bij zonder eigen ONNX-sessie. Elke worker sluit voordat de volgende start. De volledige procesboom valt onder dezelfde guard en het bestaande budget. Bronhash, offsets, batchgrootte, modelconfiguratie en uiteindelijke index worden gecontroleerd; pas daarna vervangt één transactie de nieuwe database. Een mislukte worker publiceert geen gedeeltelijke index. Hetzelfde lokale BGE-model wordt hergebruikt; ontbrekende modelbestanden kunnen worden gedownload. Er zijn geen sleutels of externe modelaanroepen nodig. Herimport vraagt een serverherstart.

```sh
python3 backend/scripts/resource_guard.py \
  --label head-matter-preview --serve-preview --timeout-seconds 7200 \
  --report "$HOME/Library/Caches/adami-case/head-matter-search/preview-guard.json" \
  --log "$HOME/Library/Caches/adami-case/head-matter-search/preview.log" \
  -- "$ADAMI_BINARY" serve
```

Stop met Ctrl+C in de guardterminal. De guard ruimt uitsluitend zijn eigen procesgroep op. Import/CLIjobs blijven maximaal 600 seconden begrensd; de preview maximaal twee uur. De RSS-grens blijft 1536 MiB, geheugendruk moet normaal blijven en swap mag niet met 128 MiB groeien. De guard stopt ook bij meetfouten of deadline; dit is geen procesisolatie of absolute piekgarantie.

```sh
curl http://127.0.0.1:8001/api/health
curl --form-string 'query=trial evidence' http://127.0.0.1:8001/api/search
curl --form-string 'query=trial evidence' --form-string 'retrieval_method=head_matter' http://127.0.0.1:8001/api/search
```

`retrieval_method` is `opinion_chunks` (standaard, B) of `head_matter` (A). Beide leveren precies drie unieke zaken. Head matter is redactionele context en krijgt eigen markeringen; de volledige majority opinion blijft beschikbaar. De CLI ondersteunt `search --retrieval-method head_matter QUESTION`; voer dit uitsluitend als aparte bewaakte job uit wanneer de server niet draait.

| Instelling | Standaard zonder feature-overrides |
|---|---|
| `ADAMI_DB_PATH` | `data/cases.sqlite3`, relatief aan de werkmap |
| `ADAMI_CACHE_DIR` | `.fastembed_cache`, relatief aan de werkmap |
| `ADAMI_BIND_ADDR` | `127.0.0.1:8000` |
| `ADAMI_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |

CORS-origins zijn kommagescheiden HTTP(S)-origins zonder pad. Modelcache, database, uploads en runverslagen blijven buiten Git. `/openapi.json` blijft bij een onbruikbare index bereikbaar.

### Bestaande demo herstellen

Stop eerst de featureguard; laat nooit twee modelservers tegelijk draaien. Vanuit de oorspronkelijke repomap herstart deze opdracht de behouden demo op 8000 met de oude binary en database:

```sh
cd /Users/R0GUE/Documents/adami-case
ADAMI_DB_PATH="$HOME/Library/Caches/adami-case/final-q-review/cases.sqlite" \
ADAMI_CACHE_DIR="$HOME/Library/Caches/adami-case/fastembed" \
ADAMI_BIND_ADDR="127.0.0.1:8000" \
ADAMI_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174" \
python3 backend/scripts/resource_guard.py \
  --label adami-orq-document-preview --serve-preview --timeout-seconds 7200 \
  --report "$HOME/Library/Caches/adami-case/head-matter-search/restored-original-guard.json" \
  --log "$HOME/Library/Caches/adami-case/head-matter-search/restored-original.log" \
  -- "$HOME/Library/Caches/adami-case/cargo-final-review/debug/texas-case-finder" serve
```

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

## Featurepreview met methodekeuze

Start na de bewaakte backend op 8001 een afzonderlijke frontend vanuit deze worktree. Gebruik poort 5177; een bestaande server op 5176 blijft ongemoeid.

```sh
cd frontend
VITE_API_MODE=api VITE_API_BASE_URL=http://127.0.0.1:8001 \
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5177 --strictPort
```

Open **http://127.0.0.1:5177/**. De methodekeuze staat bij de invoer; opinion-chunks blijft standaard. Een head-matterresultaat opent de gemarkeerde redactionele context plus de volledige majority opinion. De mockmodus biedt uitsluitend de bestaande opinion-fixtures en levert geen verzonnen A-resultaten.

## Optionele Orq-uitleg apart proberen

De Orq-uitbreiding draait als kleine Python-stdlib-adapter naast de bestaande bewaakte Rust-zoekbackend op 8000. De officiële uploadbewuste Orq-demo gebruikt 18000 met frontend 5175. Een aparte QA-preview kan daarnaast op 18001/5176 draaien. Na codewijzigingen moet de server met de bijbehorende extractorconfiguratie worden herstart. Hij laadt geen tweede embeddingmodel en bouwt geen index. Een taalmodel roept de vaste `search_cases`-tool aan; de adapter stuurt daarbij de oorspronkelijke multipartinvoer ongewijzigd naar de lokale backend. De drie zaak-ID’s, volgorde, scores, bronteksten en versies blijven behouden.

Gebruik uitsluitend een serverzijdige `ORQ_API_KEY`, of `ORQ_API_KEY_FILE` naar een privébestand buiten Git. Voorbeeldstart vanuit de aparte checkout, terwijl de bestaande backend draait:

```sh
ORQ_API_KEY_FILE=/pad/buiten/de/repo/private-orq-key \
  ADAMI_DOCUMENT_EXTRACTOR=/pad/naar/de/gebouwde/document_text \
  python3 backend/scripts/orq_proxy.py --port 18000 --max-model-requests 20
```

Model: `openai/gpt-4.1-mini-2025-04-14`, via `https://my.orq.ai/v3/router/responses`. Dit exacte catalogusmodel is met echte tool- en schema-aanroepen gecontroleerd. Een andere keuze kan met `ORQ_MODEL` of `--model`, maar die modeltoegang en functies moeten apart worden gecontroleerd. Normaal zijn er twee providerrequests per zoekopdracht; elke providerrequest heeft 30 seconden timeout en de adapter verwerkt één zoekopdracht tegelijk. Het procesbudget telt maximaal twintig providerrequests standaard en is instelbaar; na uitputting blijven echte zoekresultaten beschikbaar met uitlegstatus `unavailable`. Het budget is geen prijsplafond.

In een tweede terminal:

```sh
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:18000 node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175 --strictPort
```

Open `http://127.0.0.1:5175/`. Voor een geïsoleerde QA-preview vervang je de poorten in bovenstaande commando’s door 18001 en 5176. De gewone zoekdemos op 5173 en 5174 blijven afzonderlijk werken. De Orq-reader toont één compacte modeltoelichting met noodzakelijke beperkingen boven de volledige tekst; de gevonden passage blijft daarin gemarkeerd, zonder extra quote of spronglink. Het model retourneert alleen bestaande passage-ID’s; de server vult de citaten uit de oorspronkelijke passage in. Onbekende zaken, verkeerde passage-ID’s of ongeldige modeluitvoer maken de uitleg `unavailable`; er worden nooit zaken of citaten verzonnen als terugval.

De gebruiker heeft verwerking van uploadtekst door Orq expliciet geautoriseerd. Het model krijgt de volledige canonical uitgelezen uploadtekst, de eventuele vraag en de drie gevonden corpuspassages. Een minimale Rust-CLI [`document_text`](backend/src/bin/document_text.rs) roept exact dezelfde `extract_document` aan als de bestaande HTTP-API, zonder Engine, index of embeddingmodel te laden. TXT-whitespace/CRLF blijven behouden; PDF-extractie, onleesbare/scans en 10-MiB/20-MiB-grenzen komen uit dezelfde implementatie. Python roept het hulpje via stdin/stdout aan met een 15-secondenlimiet en geeft de Orq-secretomgeving niet door.

Bouw uitsluitend dit hulpje met `cargo +1.94.1 build --manifest-path backend/Cargo.toml --bin document_text --locked`, onder de bestaande resourceguard en met een toegestane warme `CARGO_TARGET_DIR`; de uitgevoerde bewaakte build gebruikte `~/Library/Caches/adami-case/cargo-final-review`. Zet `ADAMI_DOCUMENT_EXTRACTOR` op het volledige pad naar het resulterende `debug/document_text`. De lopende zoekserver en database worden hierbij niet vervangen.

Voor deze snelle vergelijking geldt naast maximaal 10 MiB bestandsinhoud een aparte standaardlimiet van **48 KiB uitgelezen UTF-8-uploadtekst**. `--max-upload-text-bytes` configureert die grens; de volledige geserialiseerde eerste modelcontext is daarnaast begrensd op 100 KiB en ieder providerrequest op 128 KiB. Een te grote invoer geeft expliciet 413, zonder tekst af te kappen of een gedeeltelijk gelezen document te claimen. De volledige upload wordt in aaneensluitende, niet-overlappende bewijsstukken aan beide modelrequests gegeven. Het model verwijst alleen naar toegestane upload- en corpuspassage-ID’s. De server vult quotes en UTF-16-posities uit de exacte tekst in en bindt die aan een SHA-256-tekstversie. Er is geen apart veld met de volledige uploadtekst in de frontendresponse; ‘Uit je document’ toont alleen de aangehaalde fragmenten. Vraag-only blijft zonder uploadcitaten werken; document-only vergelijkt nu daadwerkelijk de uploadinhoud. Deze toelichting bewijst geen juridische relevantie of juistheid. De bestaande UTF-16- en versiecontrole beschermt de volledige bronweergave. Sleutels en ruwe providerresponses blijven serverzijdig en buiten Git. Alleen de modeluitleg en aangehaalde bronfragmenten worden naar de frontend gestuurd; uploads worden niet opgeslagen. `store: false` wordt meegestuurd; dit is geen garantie over logs of bewaarbeleid van de modelgateway/provider.

Modelvrije adapterchecks: `python3 -m unittest discover -s backend/scripts -p 'test_orq_proxy.py'`; helperchecks: `cargo +1.94.1 test --manifest-path backend/Cargo.toml --bin document_text --locked` onder dezelfde resourcebewaking. Echte Orq-aanroepen verbruiken API-budget en horen uitsluitend bij een expliciet geautoriseerde live controle.

## Uitgevoerde controle en indicatieve zoekkwaliteit

De onafhankelijke eindcontrole omvatte 26 echte HTTP-controles en een browsertour op desktop en mobiel: vijf succesvolle zoek-POSTs, vijftien zaakdetails, alle drie volledige documenten met exacte markeringen, query/TXT/PDF/combinatie en herstel na een 422-fout. Zie [technisch bewijs en browserartefacten](https://github.com/Daanvdplas/adami-case/issues/16#issuecomment-6795249357).

De nieuwe, vooraf vastgelegde AI-doelmatchindicatie was 3/5 voor alleen een vraag, 4/5 voor alleen een document en 4/5 voor beide. De oude MiniLM-baseline van 0/15 blijft bewaard. De sets verschillen: deze aantallen vormen geen causale modelvergelijking, accuracy of recall. Er zijn onvolledige AI-relevantielabels en geen menselijke juridische referentie. Zie [evaluatiebewijs en beperkingen](https://github.com/Daanvdplas/adami-case/issues/15#issuecomment-6795249012).

## Evals bekijken en bijhouden

Open het [klikbare evaluatieoverzicht](docs/evals/index.html) in een browser. De startpagina toont alle 25 concrete ontwerpbeschrijvingen. Klik op een eval voor document en/of vraag, verwacht juridisch gedrag, reden en bronfragmenten uit het Texas-corpus. Dit zijn zichtbare ontwikkelontwerpen, geen verborgen testset. Vaste benchmarklabels en algemene meetresultaten ontbreken nog. De lokale evalserver hieronder voert ieder van de 25 zichtbare ontwerpen afzonderlijk uit, plus de losse relevantie-invoer. Een gezamenlijke webbatch over de hele set is geen onderdeel van deze pagina. De Rust-CLI kan daarnaast alle 25 ontwerpen technisch uitvoeren; zonder labels zijn er geen juridische kwaliteitsmetrics.

Onderhoud de beoordelingsafspraken in [docs/EVALUATIEOPDRACHT.md](docs/EVALUATIEOPDRACHT.md) en de concrete ontwerpbeschrijvingen in [docs/evals/scenarios.json](docs/evals/scenarios.json). Genereer daarna de leesweergave opnieuw en controleer dat bron en HTML overeenkomen:

```sh
python3 docs/evals/build.py
python3 docs/evals/build.py --check
python3 -m unittest discover -s docs/evals -p 'test_*.py'
```

De [documentatie-CI](.github/workflows/eval-docs-checks.yml) voert de synchronisatiecheck en generatortests automatisch uit bij wijzigingen aan deze evaldocumentatie. Een verouderde HTML-weergave laat de check falen. Dit valideert de documentatie, niet de kwaliteit of uitvoering van de toekomstige evals. Zie de [onderhoudsafspraken](AGENTS.md#evaluatiedocumentatie-onderhouden).

## Zoekmethoden vergelijken op de evaluatiepagina

De lokale evalpagina biedt de vaste relevantie-invoer en **alle 25 zichtbare ontwerpscenario’s** afzonderlijk. Kies een scenario en voer opinion-chunks, head matter of beide uit. De standaardvergelijking voert uitsluitend lokale retrieval uit, zonder Orq-key of modelgeneratie. Beide methoden krijgen exact dezelfde invoer en uitsluitingen; de manifesten moeten gelijk zijn. Elk ontwerpscenario sluit zijn eigen bronzaak vóór de top drie uit. De exacte Engelse vraag en/of volledige meerderheidstekst met gecontroleerde hash vormen de invoer; er wordt geen verborgen vraaganker meegestuurd. De algemene relevantie-invoer heeft geen bronuitsluiting en wordt expliciet als productdiagnostiek getoond.

```sh
python3 backend/scripts/evals_web.py \
  --port 8799 --backend http://127.0.0.1:8001 \
  --database "$HOME/Library/Caches/adami-case/head-matter-search/cases.sqlite" \
  --model-cache "$HOME/Library/Caches/adami-case/fastembed" \
  --corpus /Users/R0GUE/Downloads/texas-criminal-reports \
  --outputs "$HOME/Library/Caches/adami-case/head-matter-search/web-evals"
```

Open **http://127.0.0.1:8799/**. De webserver gebruikt `POST /api/evals/search` op de bestaande geladen engine en start geen tweede Rustproces of model. Hij bewaart invoer, bron-/scenariohashes, volledige zoekresponses, manifest, gekozen methode, uitsluitingen en timings buiten Git. De vergelijking toont echte zaak-ID’s, scores en overlap, zonder daar juridische kwaliteit of Recall/nDCG uit af te leiden. Onvolledige/mislukte runs blijven zichtbaar en worden niet met fictieve resultaten aangevuld.

Een AI-beoordeling is afzonderlijk opt-in, vereist bestaande servercredentials en verbruikt providerbudget. Zij geeft hoogstens een voorlopige AI-indicatie, geen menselijke juridische goldstandaard. Nieuwe live providercalls horen uitsluitend bij een expliciete taakautorisatie. De commandlinetool `retrieval_relevance.py` blijft beschikbaar met `--help`.

## Technische evals uitvoeren

De nieuwe Rust-CLI hergebruikt dezelfde engine als de app en sluit de bronzaak uit **vóór** de top drie. De 25 zichtbare ontwerpen worden in catalogusvolgorde uitgevoerd: vijf documentvragen, vijf losse vragen en vijftien combinaties. Alleen de exacte Engelse vraag en/of volledige meerderheidstekst gaan naar de zoekengine. Een query-only bronanker wordt uitsluitend voor herkomst en uitsluiting gebruikt.

Gebruik een bestaande, passende index en modelcache. Stop eerst de bestaande modelserver; voer één bewaakte modeljob tegelijk uit. Bouw vooraf met de gewone backendchecks. Het onderstaande binarypad geldt voor de standaard Cargo-targetmap; pas het aan wanneer `CARGO_TARGET_DIR` is ingesteld.

```sh
export ADAMI_EVAL_BINARY="$PWD/backend/target/debug/texas-case-finder"
export ADAMI_DB_PATH="$HOME/Library/Caches/adami-case/bge-static-q-safe/cases.sqlite"
export ADAMI_CACHE_DIR="$HOME/Library/Caches/adami-case/fastembed"
python3 backend/scripts/resource_guard.py \
  --label adami-eval --timeout-seconds 600 \
  --report "$HOME/Library/Caches/adami-case/eval-guard.json" \
  --log "$HOME/Library/Caches/adami-case/eval.log" \
  -- "$ADAMI_EVAL_BINARY" eval docs/evals/scenarios.json \
  /Users/R0GUE/Downloads/texas-criminal-reports \
  "$HOME/Library/Caches/adami-case/eval-run-01" --retrieval-method opinion_chunks
```

Kies `--retrieval-method opinion_chunks` of `--retrieval-method head_matter`; zonder vlag geldt de bestaande opinionmethode. Voer voor een vergelijking dezelfde scenarioselectie met beide methoden uit naar verschillende uitvoermappen. De uitvoermap moet nog niet bestaan. Voor een kleine controle voeg je bijvoorbeeld `--scenario-id E01 --scenario-id E06 --scenario-id E11` toe. De runner valideert ook dan de volledige catalogus en bronnen. Uitvoer blijft buiten Git:

- `run.json` (artifactversie 2, `rust-eval-v2`): expliciete retrievalmethode, invoerherkomst, scenario-/bronhashes, indexmanifest met modelconfiguratie, passages, uitsluitingen en zoektijd per scenario.
- `rankings.json`: geordende resultaat-ID’s per scenario, zonder verzonnen labels.
- `report.json` en `report.md`: labeldekking, ontbrekende beoordelingen, metrics en tijd per invoermodus.

Zonder kandidaatlabels zijn alle kwaliteitsmetrics `null` en is de status `not_scored`. Onbeoordeeld betekent nooit niet-relevant. De tijd omvat embedding en volledige zoekactie, zonder bron-/index-/modelladen. De eerste scenario-inferentie is apart herkenbaar aan de runvolgorde; latere scenario’s delen het geladen model. Dit zijn losse, beschrijvende metingen, geen belastingsbenchmark.

Optionele labels kunnen mee met `--labels /pad/labels.json`. De scorer controleert invoerbinding en bronbewijs tegen exacte canonieke tekst en UTF-16-posities. AI-labels blijven voorlopig; deze versie maakt geen labels. Een bestaande run kan later zonder modelladen opnieuw worden beoordeeld, met dezelfde index, catalogus en corpus:

```sh
"$ADAMI_EVAL_BINARY" score /pad/run.json /pad/labels.json \
  docs/evals/scenarios.json /Users/R0GUE/Downloads/texas-criminal-reports \
  "$HOME/Library/Caches/adami-case/eval-rescore-01"
```

De versie-1-catalogus verlangt dat de exacte majority-invoer al gelijk is aan de canonieke LF-/trimtekst. Bij een toekomstige normalisatieafwijking stopt de runner; hashes en aangeboden tekst mogen niet stil van elkaar verschillen. De bronkeuze wijzigt geen scenario-invoer of goldlabels. Menselijke controle en AI-labelgeneratie horen niet bij deze technische basis.

## Verificatie van de selecteerbare zoekmethoden

Onafhankelijk modelvrij gecontroleerd: **82 librarytests + 3 extractortests + 3 CLItests**, fmt, clippy met waarschuwingen als fouten en build; **25 Pythonchecks**, **27 frontendtests**, frontendbuild, **4 viewergeneratortests** en bron-/HTML-synchronisatie. Zes bestaande modelchecks blijven afzonderlijke, expliciet bewaakte jobs.

De tests controleren expliciete methodekeuze/default B, gescheiden bronsecties en tekstversies, alle drie invoermodi, uitsluiting vóór top drie, identieke A/B-invoer en manifestlineage, corrupte secties, oude schema’s en falende/gewijzigde importbatches zonder databasepublicatie. De bronarchivering bewaart exacte UTF-8-JSONbytes, inclusief getalrepresentatie en witruimte.

**Daadwerkelijk uitgevoerd:** de bewaakte sequentiële import publiceerde 135 zaken en 1368 passages (578 majority, 790 head matter) in 273,8 seconden, met 1196,9 MiB groepspiek, normale geheugendruk en geen swapgroei. De eerste import in één proces was eerder veilig gestopt bij 1573,34 MiB zonder databasepublicatie; de guardlimieten zijn niet verhoogd. Onafhankelijke vergelijking bevestigt alle 578 bestaande B-vectoren bytegelijk, alle majorityteksten en posities ongewijzigd, alle 135 ruwe bronJSONs exact en alle 25 scenariobronbindingen geldig.

De onafhankelijke echte API-/browsercontrole doorliep A en B met vraag, TXT-document en PDF plus vraag; zes volledige readers met exacte sectiehashes en UTF-16-markeringen; fout/herstel en mobiele weergave. E01 (document), E06 (vraag) en E11 (beide) zijn via de webinterface gepaard uitgevoerd met dezelfde invoer, manifesten en bronuitsluiting vóór top drie. Een afzonderlijke bewaakte CLI-run van E06 met A bevestigde artefactversie 2, 134 kandidaten na bronuitsluiting en `not_scored`/lege kwaliteitsmetrics. Er zijn geen Orq-/providercalls uitgevoerd en geen nieuwe juridische kwaliteitswinst geclaimd.

De tijdelijke featurebackend en beide bijbehorende webservers zijn na de controles gestopt. De oorspronkelijke demo op 8000 is met de behouden binary, database en CORS-instellingen hersteld. Runtimeverslagen, de nieuwe database en vergelijkingsruns blijven buiten Git in `$HOME/Library/Caches/adami-case/head-matter-search/`; de onafhankelijke API-/browserartefacten staan daar onder `independent-review/`. De feature kan later met bovenstaande commando’s opnieuw starten wanneer het exclusieve modelslot beschikbaar is.
