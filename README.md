# Texas Legal Document Similarity Finder

Prototypecase voor een AI-consultancy: voer een juridisch document, een zoekvraag of beide in en bekijk de drie hoogst scorende uitspraken uit het aangeleverde Texas-corpus. De frontend toont per zaak de volledige tekst van het meerderheidsoordeel (majority opinion) en markeert de gevonden passages.

**Status: de React-frontend werkt lokaal met een gesimuleerde backend. De Rust-backend en HTTP-/CLI-koppeling zijn geïmplementeerd en eerder technisch gecontroleerd. De begrensde BGE-index is vooraf berekend; de gezamenlijke live UI-doorloop en definitieve demo-overdracht worden nog afgerond.** De JSON-fixtures zijn synthetische voorbeelden, geen modelresultaten of echte uitspraken.

## Begin hier

- [AGENTS.md](AGENTS.md): werkafspraken, eigenaarschap en onderhoud van documentatie.
- [Backendafspraak voor de frontend](docs/FRONTEND_BACKEND.md): korte overdracht om parallel te kunnen bouwen.
- [OpenAPI](docs/openapi.yaml): het canonieke API-contract, ook beschikbaar via `/openapi.json`.
- [Architectuurgids](docs/CODEBASE_GUIDE.md): ontwerp, zoekmethode, grenzen en actuele implementatiestatus.
- [Hoofdissues en subissues](https://github.com/Daanvdplas/adami-case/issues): uitvoering en voortgang.

## Afgesproken scope

- Rust/Axum-backend, SQLite en lokale embeddings via fastembed.
- PDF/TXT-upload, alleen een vraag of beide; minimaal één bruikbare invoer.
- Precies drie unieke zaken met metadata, overeenkomstscore en gemarkeerde passage in de volledige tekst van het meerderheidsoordeel.
- Exact zoeken over alle geïndexeerde passages. De garantie is de hoogste drie scores volgens onze zoekmethode binnen dit corpus; inhoudelijke juridische relevantie wordt apart beoordeeld.
- De Rust-backend staat in `backend/`; de gemergde React/TypeScript-frontend met Vite staat in `frontend/`.
- Geen gegenereerd juridisch antwoord of Orq/Codex-aanroep in deze versie. Docker is optioneel en geen voorwaarde voor de eerste demo.
- Operationele invoergrenzen: document 10 MiB, vraag 1 MiB UTF-8, totale multipartrequest 12 MiB en uitgelezen PDF-tekst 20 MiB. Overschrijdingen geven een fout; tekst wordt niet stil afgekapt.

## Data en hergebruik

Het aangeleverde corpus staat lokaal in `/Users/R0GUE/Downloads/texas-criminal-reports`: 135 uitspraken van het Texas Court of Criminal Appeals uit 1892–1893, in JSON met volledige tekst en bijbehorende HTML. Gebruik de uitspraakdatum (`decision_date`); de volumemetadata noemt foutief 1992–1993. Ruwe data, uploads en databases zijn nog niet opgenomen in deze repo.

De aangeleverde [CAP-link](https://case.law/caselaw/#florida) heeft een Florida-anchor; de lokale dataset is Texas en is het afgesproken corpus. Bewaar bij import de bronidentificatie en metadata. De demo geeft geen overzicht van actuele of volledige Texas-jurisprudentie.

`../coa` bevat een herbruikbare Rust-zoekkern en een voorbeeld van eerst zoeken en daarna passages aan een model aanbieden. De nieuwe app neemt gericht zoekonderdelen over; de Codex/MCP-aansturing en COA-specifieke dataset niet. Zie de architectuurgids voor de gecontroleerde codepaden.

## Backendbasis controleren

Benodigd: Rust 1.94.1 met clippy en rustfmt; nightly met rustfmt voor de formatteringsafspraak. De eerste build downloadt Rust-dependencies en de ONNX-runtime, maar geen embeddingmodel. Voer vanuit de reporoot uit:

```sh
cargo +nightly fmt --manifest-path backend/Cargo.toml --all
cargo +1.94.1 fmt --manifest-path backend/Cargo.toml --all --check
cargo +1.94.1 clippy --manifest-path backend/Cargo.toml --locked --all-targets -- -D warnings
cargo +1.94.1 test --manifest-path backend/Cargo.toml --locked
cargo +1.94.1 build --manifest-path backend/Cargo.toml --locked
```

De tests gebruiken de echte router, multipartverwerking en PDF/TXT-extractie. Alleen de zoekengine wordt bij de HTTP-tests vervangen door de synthetische contractfixtures; deze tests bewijzen geen modelkwaliteit. De [backendworkflow](.github/workflows/backend-checks.yml) voert formattering, clippy, deterministische tests en build uit zonder embeddingmodel te laden.

## Nu parallel beginnen

De frontend gebruikt [de korte backendafspraak](docs/FRONTEND_BACKEND.md) en de fixtures. De bestaande frontend is via de gewone main-integratie overgenomen; de backend-PR voegt geen nieuwe frontendfunctionaliteit toe.

## Backend gebruiken

Bouw eerst de binary, zonder gelijktijdige modeljob. Gebruik per worktree een eigen targetmap; gedeelde artifacts van dezelfde crate kunnen tests uit een andere checkout hergebruiken.

```sh
export CARGO_BUILD_JOBS=2
export CARGO_TARGET_DIR="$HOME/Library/Caches/adami-case/cargo-api"
cargo +1.94.1 build --manifest-path backend/Cargo.toml --locked
export ADAMI_BINARY="$CARGO_TARGET_DIR/debug/texas-case-finder"
export ADAMI_DB_PATH="$HOME/Library/Caches/adami-case/bge-static-q-safe/cases.sqlite"
export ADAMI_CACHE_DIR="$HOME/Library/Caches/adami-case/fastembed"
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

Open `http://127.0.0.1:5173/`. De ontwikkelserver luistert alleen lokaal. Typ/plak eigen tekst, voeg een PDF/TXT van maximaal 10 MiB toe, of combineer beide. Versturen toont na een korte laadstatus altijd dezelfde drie verzonnen zaken als klikbare documentvoorbeelden onder de invoerbox, op desktop naast elkaar. Een nieuwe zoekopdracht vervangt de vorige resultaten. Open een document om in een aparte leesweergave de volledige aangeleverde meerderheidstekst met markering te lezen; de terugknop brengt je naar de resultaten. Het blok ‘Waarom dit document?’ toont de exacte gevonden bronpassage en overeenkomstscore, geen gegenereerde juridische verklaring of daadwerkelijke analyse van je invoer in de demostand.

De standaarddemostand leest of verstuurt bestandsinhoud niet en slaat uploads of gesprekken niet op. De bijlage wordt in de mock alleen op naam, extensie en grootte gecontroleerd; inhoudelijke PDF/TXT-validatie en echte zoekresultaten verlopen via de Rust-backend in API-modus. De fixtureteksten zijn kort en bewijzen geen leesbaarheid van lange echte uitspraken.

Gecontroleerde frontendchecks:

```sh
npm test
npm run build
```

`npm test` controleert invoermodi en grenzen, mock/API-uitwisseling, React-interacties en UTF-16-markeringen met versiecontrole. De build voert TypeScript-controle uit en schrijft `frontend/dist/` (genegeerd door Git).

Voor de echte API-koppeling: kopieer `frontend/.env.example` naar `frontend/.env.local`, zet `VITE_API_MODE=api`, configureer `VITE_API_BASE_URL` en herstart Vite. Deze modus verstuurt uploads naar die ingestelde backend; de gezamenlijke end-to-end-controle wacht nog op de goedgekeurde, begrensde BGE-index. De standaard blijft `mock`. Zie [de backendafspraak](docs/FRONTEND_BACKEND.md).
