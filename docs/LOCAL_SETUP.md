# Lokale setup en technische bediening

Gebruik vanuit de reporoot `./start` voor de gezamenlijke lokale start. De pagina’s zijn Mike op `http://127.0.0.1:5176/` en evaluaties op `http://127.0.0.1:8798/`. De launcher start één bewaakte Rustbackend, de Orq-uitlegadapter, Mike en de evalserver; hij opent beide pagina’s nadat de services bereikbaar zijn. De handmatige commando’s hieronder blijven beschikbaar voor ontwikkeling en herstel.

## Eén gezamenlijke start

Vereist: macOS of Linux, Python 3, Rust 1.94.1 via rustup, Node.js 22.12+ met npm, de bestaande schema-3-database, bijbehorende lokale modelcache en aangeleverde corpusbestanden. De launcher controleert vereisten en bouwt ontbrekende Rust-/frontendonderdelen. Een build kan dependencies downloaden; de launcher importeert geen corpus en haalt geen ontbrekend embeddingmodel stilzwijgend op. Een onbruikbare index of ontbrekende cache vereist expliciete setup.

Mike moet naar de echte Orq-adapter op 18000 wijzen: het gezamenlijke startprofiel zet `VITE_API_MODE=api` en `VITE_API_BASE_URL=http://127.0.0.1:18000`. Zo blijven lokale bronselectie en B-ranking op Rust8000, met de optionele brongebonden toelichting via Orq. E06 gebruikt de lokale engine rechtstreeks; met een geconfigureerde sleutel staat de uitschakelbare AI-beoordeling standaard aan. Alleen de startknop doet een zoek- of provideraanroep. B1 heeft geen AI-beoordelaar.

De servercredential komt uit `ORQ_API_KEY`, een privébestand via `ORQ_API_KEY_FILE` of `./start --orq-key-file /pad/buiten/de/repo/key`. De volledige gezamenlijke start vereist een sleutel. Zonder ingestelde sleutel vraagt de launcher die verborgen in een interactieve terminal; zonder terminal en zonder sleutel stopt hij met een fout. Een ingevoerde sleutel wordt niet stil opgeslagen en komt niet in de frontend. Een geldige Orq-sleutel en toegang tot het gekozen model zijn nodig voor echte Mike-uitleg en E06-AI-scores. Een losse handmatige Rust-/evalstart kan zonder sleutel lokaal zoeken; dat is niet het volledige `./start`-profiel. Ontbrekende toegang mag niet als een succesvolle AI-beoordeling worden gepresenteerd. Een bestaande sleutelfile wordt nooit verwijderd. Een via omgeving of prompt aangeleverde sleutel wordt alleen tijdelijk met rechten `0600` gedeeld en bij stoppen opgeruimd.

De draagbare standaardpaden zijn `data/cases.sqlite3`, `.fastembed_cache` en `data/texas-criminal-reports`, relatief aan de reporoot. Stel voor bestaande bestanden elders `ADAMI_DB_PATH`, `ADAMI_CACHE_DIR` en `ADAMI_CORPUS_DIR` in. Het genegeerde `start.local.json` gebruikt dezelfde `ADAMI_DB_PATH`-, `ADAMI_CACHE_DIR`- en `ADAMI_CORPUS_DIR`-sleutels voor lokale paden; omgevingsinstellingen hebben voorrang. Het is geen sleutelopslag. Eventuele `CARGO_TARGET_DIR` en `ADAMI_BINARY` verwijzen naar een bestaande buildcache. Op deze Mac verwijst die configuratie naar de bestaande index, cache en corpusbestanden, zonder kopieën te maken.

Opties: `--orq-key-file PATH`, `--no-open`, `--backend-port`, `--orq-port`, `--mike-port` en `--eval-port`. De standaardpoorten zijn respectievelijk 8000, 18000, 5176 en 8798. Beide Orq-services gebruiken dezelfde `ORQ_BASE_URL` (standaard de echte Orq-cloudgateway). Een lokale providerstub is uitsluitend een expliciete contracttest, geen productfallback of bewijs van werkende cloudtoegang.

De resourceguard behoudt op macOS de bestaande systeemmetingen. Op Linux leest hij `/proc/meminfo`: minder dan 10% `MemAvailable` ten opzichte van `MemTotal` stopt de job volgens onze expliciete Linux-regel. Dit is geen identieke kernel-pressuremeting als op macOS. Groeps-RSS blijft begrensd op 1536 MiB en swapgroei op 128 MiB; ontbrekende of ongeldige meetgegevens stoppen de job. Windows wordt niet ondersteund. Houd de terminal open. Ctrl+C stopt uitsluitend door deze launcher gestarte processen. De launcher neemt bezette poorten of bestaande native modeljobs niet stil over. Start geen import, CLI-zoekactie of tweede modelserver naast de lopende engine. Sleutels, uploads, indexen, caches, logs en runresultaten blijven buiten Git.

De uitgebreide handmatige inrichting, resourcegrenzen en historische verificatie hieronder blijven van toepassing. Commandoblokken worden vanuit de reporoot uitgevoerd tenzij het blok zelf een andere map kiest.

## Technische achtergrond en handmatige bediening

Prototypecase voor een AI-consultancy: voer een juridisch document, een zoekvraag of beide in en bekijk de drie hoogst scorende uitspraken uit het aangeleverde Texas-corpus. De frontend toont per zaak de volledige tekst van het meerderheidsoordeel (majority opinion) en markeert de gevonden passages.

**Status:** selecteerbare head-matterzoekmethode naast de bestaande opinion-chunks, met een gecontroleerde dual-index en API-/browserdoorloop. Het lokale startprofiel hieronder gebruikt Mike op 5176, één bewaakte Rustbackend op 8000 en evaluaties op 8798. Bestaande databases en binaries blijven behouden; zie de verificatie onderaan.

## Begin hier

- [AGENTS.md](../AGENTS.md): werkafspraken, eigenaarschap en onderhoud van documentatie.
- [Frontendcontract](CODEBASE_GUIDE.md#frontendcontract): korte overdracht om parallel te kunnen bouwen.
- [OpenAPI](openapi.yaml): het canonieke API-contract, ook beschikbaar via `/openapi.json`.
- [Architectuurgids](CODEBASE_GUIDE.md): ontwerp, zoekmethode, grenzen en actuele implementatiestatus.
- [Evaluatieoverzicht](../evals/web/index.html): B1 en E06, met lokale methodekeuze en optionele AI-beoordeling voor E06; [de opdracht](../evals/README.md) bevat de beoordelingsafspraken.
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
python3 -m unittest discover -s evals -t . -p 'test_*.py'
cargo +1.94.1 build --manifest-path backend/Cargo.toml --locked
```

Op de gereviewde codehead `9ef3bf9` slaagden 45 Rust-tests, vijf Python-beleidstests, fmt, clippy, build en Linux-CI. Zes echte model-/diagnosticchecks staan bewust apart van de standaardtestset. De standaardtests gebruiken de echte router, multipartverwerking en PDF/TXT-extractie. Alleen de zoekengine wordt bij de HTTP-tests vervangen door de synthetische contractfixtures; deze tests bewijzen geen modelkwaliteit. De [backendworkflow](../.github/workflows/backend-checks.yml) voert formattering, clippy, deterministische tests en build uit zonder embeddingmodel te laden.

## Nu parallel beginnen

De frontend gebruikt [het frontendcontract](CODEBASE_GUIDE.md#frontendcontract); fixtures zijn alleen voor expliciete mockmodus. De bestaande frontend is via de gewone main-integratie overgenomen; de backend-PR voegt geen nieuwe frontendfunctionaliteit toe.

## Backend gebruiken

Deze versie vereist indexformaat3 met zowel majority opinions als afzonderlijke head matter. Gebruik een nieuw databasepad; overschrijf de bestaande majority-only demo-index niet. Een oude of onvolledige index geeft 503 vóór modelladen en wordt nooit stil herbouwd.

Bouw eerst buiten het modelbudget met de backendchecks hierboven. Gebruik voor deze Mac vervolgens:

```sh
export ADAMI_BINARY="$HOME/Library/Caches/adami-case/cargo-head-matter/debug/texas-case-finder"
export ADAMI_DB_PATH="$HOME/Library/Caches/adami-case/head-matter-search/cases.sqlite"
export ADAMI_CACHE_DIR="$HOME/Library/Caches/adami-case/fastembed"
export ADAMI_BIND_ADDR="127.0.0.1:8000"
export ADAMI_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5176,http://127.0.0.1:5176"
```

Voer uitsluitend één native modeljob tegelijk uit. Stop de bestaande guard netjes vóór import; start geen import of CLIzoekactie naast een modelserver. De oude demo gebruikt een aparte binary en database op 8000. De nieuwe mainserver vervangt die oude demo wanneer haar guard netjes is gestopt; reserveer eerst het exclusieve modelslot. De nieuwe server hergebruikt de schema-3-index en bouwt bij starten geen nieuwe index.

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
curl http://127.0.0.1:8000/api/health
curl --form-string 'query=trial evidence' http://127.0.0.1:8000/api/search
curl --form-string 'query=trial evidence' --form-string 'retrieval_method=head_matter' http://127.0.0.1:8000/api/search
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
VITE_API_MODE=api VITE_API_BASE_URL=http://127.0.0.1:18000 node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort
```

Deze modus verstuurt uploads naar de lokale backend en toont echte corpusresultaten. Stop alleen deze Vite-preview met Ctrl+C in zijn eigen terminal. De standaardmodus is de echte API; uitsluitend `VITE_API_MODE=mock` kiest fixtures. Zie [het frontendcontract](CODEBASE_GUIDE.md#frontendcontract).

## Mike lokaal met Orq-uitleg

Start na de bewaakte backend op 8000 de frontend vanuit deze checkout. Gebruik de vrije poort 5176; laat andere previews ongemoeid.

```sh
cd frontend
VITE_API_MODE=api VITE_API_BASE_URL=http://127.0.0.1:18000 \
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5176 --strictPort
```

Open **http://127.0.0.1:5176/**. Mike gebruikt standaard opinion-chunks; de zoekmethode wordt uitsluitend op de evaluatiepagina gekozen. Een head-matterresultaat opent de gemarkeerde redactionele context plus de volledige majority opinion. De mockmodus biedt uitsluitend de bestaande opinion-fixtures en levert geen verzonnen A-resultaten.

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

De gebruiker heeft verwerking van uploadtekst door Orq expliciet geautoriseerd. Het model krijgt de volledige canonical uitgelezen uploadtekst, de eventuele vraag en de drie gevonden corpuspassages. Een minimale Rust-CLI [`document_text`](../backend/src/bin/document_text.rs) roept exact dezelfde `extract_document` aan als de bestaande HTTP-API, zonder Engine, index of embeddingmodel te laden. TXT-whitespace/CRLF blijven behouden; PDF-extractie, onleesbare/scans en 10-MiB/20-MiB-grenzen komen uit dezelfde implementatie. Python roept het hulpje via stdin/stdout aan met een 15-secondenlimiet en geeft de Orq-secretomgeving niet door.

Bouw uitsluitend dit hulpje met `cargo +1.94.1 build --manifest-path backend/Cargo.toml --bin document_text --locked`, onder de bestaande resourceguard en met een toegestane warme `CARGO_TARGET_DIR`; de uitgevoerde bewaakte build gebruikte `~/Library/Caches/adami-case/cargo-final-review`. Zet `ADAMI_DOCUMENT_EXTRACTOR` op het volledige pad naar het resulterende `debug/document_text`. De lopende zoekserver en database worden hierbij niet vervangen.

Voor deze snelle vergelijking geldt naast maximaal 10 MiB bestandsinhoud een aparte standaardlimiet van **48 KiB uitgelezen UTF-8-uploadtekst**. `--max-upload-text-bytes` configureert die grens; de volledige geserialiseerde eerste modelcontext is daarnaast begrensd op 100 KiB en ieder providerrequest op 128 KiB. Een te grote invoer geeft expliciet 413, zonder tekst af te kappen of een gedeeltelijk gelezen document te claimen. De volledige upload wordt in aaneensluitende, niet-overlappende bewijsstukken aan beide modelrequests gegeven. Het model verwijst alleen naar toegestane upload- en corpuspassage-ID’s. De server vult quotes en UTF-16-posities uit de exacte tekst in en bindt die aan een SHA-256-tekstversie. Er is geen apart veld met de volledige uploadtekst in de frontendresponse; ‘Uit je document’ toont alleen de aangehaalde fragmenten. Vraag-only blijft zonder uploadcitaten werken; document-only vergelijkt nu daadwerkelijk de uploadinhoud. Deze toelichting bewijst geen juridische relevantie of juistheid. De bestaande UTF-16- en versiecontrole beschermt de volledige bronweergave. Sleutels en ruwe providerresponses blijven serverzijdig en buiten Git. Alleen de modeluitleg en aangehaalde bronfragmenten worden naar de frontend gestuurd; uploads worden niet opgeslagen. `store: false` wordt meegestuurd; dit is geen garantie over logs of bewaarbeleid van de modelgateway/provider.

Modelvrije adapterchecks: `python3 -m unittest discover -s backend/scripts -p 'test_orq_proxy.py'`; helperchecks: `cargo +1.94.1 test --manifest-path backend/Cargo.toml --bin document_text --locked` onder dezelfde resourcebewaking. Echte Orq-aanroepen verbruiken API-budget en horen uitsluitend bij een expliciet geautoriseerde live controle.

## Uitgevoerde controle en indicatieve zoekkwaliteit

De onafhankelijke eindcontrole omvatte 26 echte HTTP-controles en een browsertour op desktop en mobiel: vijf succesvolle zoek-POSTs, vijftien zaakdetails, alle drie volledige documenten met exacte markeringen, query/TXT/PDF/combinatie en herstel na een 422-fout. Zie [technisch bewijs en browserartefacten](https://github.com/Daanvdplas/adami-case/issues/16#issuecomment-6795249357).

De nieuwe, vooraf vastgelegde AI-doelmatchindicatie was 3/5 voor alleen een vraag, 4/5 voor alleen een document en 4/5 voor beide. De oude MiniLM-baseline van 0/15 blijft bewaard. De sets verschillen: deze aantallen vormen geen causale modelvergelijking, accuracy of recall. Er zijn onvolledige AI-relevantielabels en geen menselijke juridische referentie. Zie [evaluatiebewijs en beperkingen](https://github.com/Daanvdplas/adami-case/issues/15#issuecomment-6795249012).

## Evals bekijken en bijhouden

Open het [evaluatieoverzicht](../evals/web/index.html) via de lokale evalserver hieronder. De compacte pagina behoudt de vaste B1-referentiecontrole en E06; kaarten beginnen ingeklapt en bewaren een bestaande uitslag wanneer je ze sluit. Iedere zichtbare kaart heeft één methodekeuze en één startknop. De overige25 scenario’s zijn uitsluitend bronmateriaal voor de CLI en verdere benchmarkontwikkeling. De volledige ontwerpbeschrijvingen en onderhoudsinstructies blijven in de canonieke bronnen, buiten de zichtbare kaarten. Zonder kandidaatlabels leveren de scenario’s geen juridische kwaliteitsmetrics.

Onderhoud de beoordelingsafspraken in [evals/README.md](../evals/README.md) en de concrete ontwerpbeschrijvingen in [evals/data/scenarios.json](../evals/data/scenarios.json). Genereer daarna de leesweergave opnieuw en controleer dat bron en HTML overeenkomen:

```sh
python3 -m evals.build
python3 -m evals.build --check
python3 -m unittest discover -s evals -t . -p 'test_*.py'
```

De [documentatie-CI](../.github/workflows/eval-docs-checks.yml) voert de synchronisatiecheck en generatortests automatisch uit bij wijzigingen aan deze evaldocumentatie. Een verouderde HTML-weergave laat de check falen. Dit valideert de documentatie, niet de kwaliteit of uitvoering van de toekomstige evals. Zie de [onderhoudsafspraken](../AGENTS.md#evaluatiedocumentatie-onderhouden).

## Zoekmethoden vergelijken op de evaluatiepagina

De pagina biedt uitsluitend **B1 en E06**. Kies per kaart opinion-chunks(B), head matter(A) of beide. Beide methoden krijgen dezelfde invoer en indexcontext. E06 sluit Nixon156133 vóór de top drie uit en gebruikt uitsluitend de vastgelegde Engelse vraag; B1 heeft geen bronuitsluiting. B1 gebruikt uitsluitend lokale retrieval. E06 kan dezelfde retrieval met een afzonderlijke AI-beoordeling aanvullen.

De zichtbare E06-kaart biedt dezelfde keuze A, B of beide. Bij een geconfigureerde sleutel staat de uitschakelbare AI-beoordeling standaard aan; de startknop wacht op de modelcatalogus. Alleen laden start geen beoordelingsaanroep. Zonder sleutel of met uitgevinkte AI-beoordeling blijft een losse evalserver lokaal werken.

**B1** gebruikt één normale startknop met keuze A, B of beide. De exacte oorspronkelijke vraag en twee verwachte zaken (Cummings156040 en Neubauer156042) zijn behouden. Per methode wordt werkelijk 0–2 geteld: `passed` is uitsluitend waar als beide in de echte top drie staan. De huidige v2-fixture bindt expliciet alle135 bronrecords, secties/passages/vectoren, model en indexmanifest. Oudev1 staat alleen in `evals/data/archive/deterministic_b1_v1.json`. V2 is een gemigreerde referentie na eerdere diagnostische runs, geen nieuwe preregistratie of juridische goldset. B1 heeft geen AI-beoordelaar; verwachte IDs worden nooit zoekinvoer.

```sh
python3 -m evals.evals_web \
  --port 8798 --backend http://127.0.0.1:8000 \
  --database "$HOME/Library/Caches/adami-case/head-matter-search/cases.sqlite" \
  --model-cache "$HOME/Library/Caches/adami-case/fastembed" \
  --corpus /Users/R0GUE/Downloads/texas-criminal-reports \
  --outputs "$HOME/Library/Caches/adami-case/head-matter-search/web-evals"
```

Open **http://127.0.0.1:8798/**. De webserver gebruikt `POST /api/evals/search` op de bestaande geladen engine en start geen tweede Rustproces of model. Hij bewaart invoer, bron-/scenariohashes, volledige zoekresponses, manifest, gekozen methode, uitsluitingen en timings buiten Git. De vergelijking toont echte zaak-ID’s, scores en overlap, zonder daar juridische kwaliteit of Recall/nDCG uit af te leiden. Onvolledige/mislukte runs blijven zichtbaar en worden niet met fictieve resultaten aangevuld.

De optionele **AI-beoordeling van gevonden passages** bij E06 gebruikt dezelfde serverzijdige credentialloader als Mike: `ORQ_API_KEY`, of `ORQ_API_KEY_FILE` naar een privébestand buiten Git. De environmentwaarde gaat vóór het bestand. Een expliciet onleesbaar of leeg bestand geeft een veilige startfout; zonder beide blijft lokaal zoeken werken. `--ask-key` is alleen een expliciete interactieve optie. De sleutel gaat nooit naar de browser of runartefacten.

Voor AI-beoordeling voeg je bij het startcommando bijvoorbeeld `ORQ_API_KEY_FILE=/pad/buiten/de/repo/private-orq-key` vóór `python3` toe. Het gekozen beoordelingsmodel en de werkelijk gerapporteerde provider-ID worden afzonderlijk bewaard. Per methode worden drie grades0–3 en exacte citaten gecontroleerd; A-passages blijven expliciet redactionele context. Een ontbrekende of mislukte judge kan niet als uitgevoerde AI-beoordeling worden getoond. Dit beoordeelt uitsluitend de opgehaalde passages, geen volledige opinions of juridische juistheid.

Succesvolle providerresponses worden per methode atomair en met mode0600 als `judge-response-METHOD.json` buiten Git bewaard; het runresultaat bevat de artefactverwijzing en SHA256. De responsefile bevat geen requestheaders of credential. Een nieuwe AI-smoke verbruikt providerbudget en wordt afzonderlijk geautoriseerd. De commandlinetool `retrieval_relevance.py` blijft beschikbaar met `--help`.

## Technische evals uitvoeren

De nieuwe Rust-CLI hergebruikt dezelfde engine als de app en sluit de bronzaak uit **vóór** de top drie. De 25 canonieke scenario’s worden in catalogusvolgorde uitgevoerd: vijf documentvragen, vijf losse vragen en vijftien combinaties. Alleen de exacte Engelse vraag en/of volledige meerderheidstekst gaan naar de zoekengine. Een query-only bronanker wordt uitsluitend voor herkomst en uitsluiting gebruikt.

Gebruik een bestaande, passende index en modelcache. Stop eerst de bestaande modelserver; voer één bewaakte modeljob tegelijk uit. Bouw vooraf met de gewone backendchecks. Het onderstaande binarypad geldt voor de standaard Cargo-targetmap; pas het aan wanneer `CARGO_TARGET_DIR` is ingesteld.

```sh
export ADAMI_EVAL_BINARY="$PWD/backend/target/debug/texas-case-finder"
export ADAMI_DB_PATH="$HOME/Library/Caches/adami-case/head-matter-search/cases.sqlite"
export ADAMI_CACHE_DIR="$HOME/Library/Caches/adami-case/fastembed"
python3 backend/scripts/resource_guard.py \
  --label adami-eval --timeout-seconds 600 \
  --report "$HOME/Library/Caches/adami-case/eval-guard.json" \
  --log "$HOME/Library/Caches/adami-case/eval.log" \
  -- "$ADAMI_EVAL_BINARY" eval evals/data/scenarios.json \
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
  evals/data/scenarios.json /Users/R0GUE/Downloads/texas-criminal-reports \
  "$HOME/Library/Caches/adami-case/eval-rescore-01"
```

De versie-1-catalogus verlangt dat de exacte majority-invoer al gelijk is aan de canonieke LF-/trimtekst. Bij een toekomstige normalisatieafwijking stopt de runner; hashes en aangeboden tekst mogen niet stil van elkaar verschillen. De bronkeuze wijzigt geen scenario-invoer of goldlabels. Menselijke controle en AI-labelgeneratie horen niet bij deze technische basis.

## Verificatie van de selecteerbare zoekmethoden

Onafhankelijk modelvrij gecontroleerd: **82 librarytests + 3 extractortests + 3 CLItests**, fmt, clippy met waarschuwingen als fouten en build; **40 Pythonchecks**, **32 frontendtests**, frontendbuild, **4 viewergeneratortests** en bron-/HTML-synchronisatie. Zes bestaande modelchecks blijven afzonderlijke, expliciet bewaakte jobs.

De tests controleren expliciete methodekeuze/default B, gescheiden bronsecties en tekstversies, alle drie invoermodi, uitsluiting vóór top drie, identieke A/B-invoer en manifestlineage, corrupte secties, oude schema’s en falende/gewijzigde importbatches zonder databasepublicatie. De bronarchivering bewaart exacte UTF-8-JSONbytes, inclusief getalrepresentatie en witruimte.

**Daadwerkelijk uitgevoerd:** de bewaakte sequentiële import publiceerde 135 zaken en 1368 passages (578 majority, 790 head matter) in 273,8 seconden, met 1196,9 MiB groepspiek, normale geheugendruk en geen swapgroei. De eerste import in één proces was eerder veilig gestopt bij 1573,34 MiB zonder databasepublicatie; de guardlimieten zijn niet verhoogd. Onafhankelijke vergelijking bevestigt alle 578 bestaande B-vectoren bytegelijk, alle majorityteksten en posities ongewijzigd, alle 135 ruwe bronJSONs exact en alle 25 scenariobronbindingen geldig.

De onafhankelijke echte API-/browsercontrole doorliep A en B met vraag, TXT-document en PDF plus vraag; zes volledige readers met exacte sectiehashes en UTF-16-markeringen; fout/herstel en mobiele weergave. E01 (document), E06 (vraag) en E11 (beide) zijn via de webinterface gepaard uitgevoerd met dezelfde invoer, manifesten en bronuitsluiting vóór top drie. Een afzonderlijke bewaakte CLI-run van E06 met A bevestigde artefactversie 2, 134 kandidaten na bronuitsluiting en `not_scored`/lege kwaliteitsmetrics. Er zijn geen Orq-/providercalls uitgevoerd en geen nieuwe juridische kwaliteitswinst geclaimd.

De tijdelijke featurebackend en beide bijbehorende webservers zijn na de controles gestopt. De oorspronkelijke demo op 8000 is met de behouden binary, database en CORS-instellingen hersteld. De echte zoekkern-/API-/browserbewijzen horen bij codehead `2fa5b1a`; de latere integratie verandert de Rust-engine niet. De nieuwe productfrontend-modelkeuze is afzonderlijk modelvrij gecontroleerd, inclusief combinatie met de retrievalmethode. De gewijzigde evaluatieweergave wordt afzonderlijk modelvrij met opgeslagen responses gecontroleerd; dit geldt niet als een nieuwe modelrun. Runtimeverslagen, de nieuwe database en vergelijkingsruns blijven buiten Git in `$HOME/Library/Caches/adami-case/head-matter-search/`; de onafhankelijke API-/browserartefacten staan daar onder `independent-review/`. Het lokale startprofiel hierboven hergebruikt dezelfde gecontroleerde dual-index; stop eerst een eventuele oude modelguard.

De losse commandlinetool `python3 -m evals.retrieval_relevance` uit PR36 blijft beschikbaar voor één eigen vraag en/of UTF-8-tekstbestand; gebruik `--help`. Zij gebruikt dezelfde judge- en bronfragmentcontrole als de webpagina.

## Orq-model kiezen

Mike toont bij de optionele uitlegsidecar een keuze **Model voor toelichting**. De E06-kaart gebruikt **Beoordelingsmodel**. Beide lijsten komen van `GET /api/models` op hun eigen server. De gewone Rust-API biedt die route niet; daar blijft lokaal zoeken zonder modelkiezer beschikbaar. B1 heeft geen modelkeuze en doet geen Orq-aanroep.

De serverallowlist bevat `openai/gpt-4.1-mini-2025-04-14` (bestaande standaard) en `openai/gpt-4.1-2025-04-14`. Beide exacte IDs zijn in de actuele geauthenticeerde Orq-catalogus aangetroffen. Die catalogus geeft geen tool-/schema-capabilities, daarom worden niet alle catalogusmodellen aangeboden. Met `ORQ_MODELS` kun je een kommagescheiden subset van deze ondersteunde IDs kiezen; `ORQ_MODEL`/`--model` moet daarin staan. Een onbekend gekozen model geeft 400 vóór zoeken of een providerrequest. Provider-/modeltoegangsfouten zijn zichtbaar en schakelen niet over naar een ander model.

Mike stuurt de keuze alleen via `X-Orq-Model`; de oorspronkelijke query-/documentmultipart gaat ongewijzigd naar Rust. `explanation_requested_model` registreert de keuze en `explanation_model` de werkelijk door de provider gemelde model-ID. Ontbrekende provideridentiteit blijft `null` en wordt als onbekend getoond. E06 gebruikt JSON `{"model":"..."}` en bewaart `requested_model` en de werkelijk gemelde `model` in het runartefact. De key blijft uitsluitend op de server en komt niet in deze browserverzoeken of resultaten.

De afzonderlijke modelkeuzevalidatie gebruikte previews op 5177/18002 en 8800 met opgeslagen echte retrieval. Dat controleerde modeldoorgifte en brongebonden uitvoer, zonder een nieuwe embeddingindex te claimen. Het main-profiel op5176 gebruikt de bestaande echte Orq-uitlegverbinding op18000, die de actuele Rustbackend8000 hergebruikt. Een server zonder `/api/models` toont volgens het capabilitycontract geen modelkiezer. Sleutels worden niet verplaatst.

## Laatste opleveringscorrecties

B1-v2 is op11november2026 onafhankelijk echt uitgevoerd met B, A en beide: beide methoden vonden0 van de2 verwachte zaken. De runs zijn technisch voltooid; de referentiecontrole is eerlijk niet geslaagd. E06 is toen lokaal met beide methoden uitgevoerd, zonder AI-judge. De vereenvoudigde Mike-interface en één echte Orq-uitlegresponse met drie gecontroleerde readers zijn eveneens getest. Dit zijn bestaande bewijzen, geen nieuwe AI-benchmarkresultaten.

De E06-credentialfilefix, controle op foutieve AI-success en private providerresponse-archivering zijn modelvrij getest. Een nieuwe echte E06-AI-smoke vereist een bestaande privécredential; de huidige status en herkomst staan in PR56. Deze correcties zijn via PR56 naar main gemergd; dit is geen bewijs van een nieuwe live AI-beoordeling.
