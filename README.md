# Texas Legal Document Similarity Finder

Prototypecase voor een AI-consultancy: voer een juridisch document, een zoekvraag of beide in en bekijk de drie hoogst scorende uitspraken uit het aangeleverde Texas-corpus. De frontend toont per zaak de volledige tekst van het meerderheidsoordeel (majority opinion) en markeert de gevonden passages.

**Status: de React-frontend werkt lokaal met een gesimuleerde backend. Er is nog geen uitvoerbare backend of database.** De JSON-fixtures zijn synthetische voorbeelden, geen modelresultaten of echte uitspraken.

## Begin hier

- [AGENTS.md](AGENTS.md): werkafspraken, eigenaarschap en onderhoud van documentatie.
- [Backendafspraak voor de frontend](docs/FRONTEND_BACKEND.md): korte overdracht om parallel te kunnen bouwen.
- [OpenAPI](docs/openapi.yaml): het canonieke, nog te implementeren API-contract.
- [Architectuurgids](docs/CODEBASE_GUIDE.md): ontwerp, zoekmethode, grenzen en actuele implementatiestatus.
- [Evaluatieoverzicht](docs/evals/index.html): klikbare uitleg van de geplande evals; [de opdracht](docs/EVALUATIEOPDRACHT.md) is de canonieke inhoud.
- [Hoofdissues en subissues](https://github.com/Daanvdplas/adami-case/issues): uitvoering en voortgang.

## Afgesproken scope

- Rust/Axum-backend, SQLite en lokale embeddings via fastembed.
- PDF/TXT-upload, alleen een vraag of beide; minimaal één bruikbare invoer.
- Precies drie unieke zaken met metadata, overeenkomstscore en gemarkeerde passage in de volledige tekst van het meerderheidsoordeel.
- Exact zoeken over alle geïndexeerde passages. De garantie is de hoogste drie scores volgens onze zoekmethode binnen dit corpus; inhoudelijke juridische relevantie wordt apart beoordeeld.
- De React/TypeScript-frontend staat in `frontend/` en gebruikt Vite. De toekomstige Rust-backend komt in `backend/`; deze map bestaat nog niet.
- Geen gegenereerd juridisch antwoord of Orq/Codex-aanroep in deze versie. Docker is optioneel en geen voorwaarde voor de eerste demo.

## Data en hergebruik

Het aangeleverde corpus staat lokaal in `/Users/R0GUE/Downloads/texas-criminal-reports`: 135 uitspraken van het Texas Court of Criminal Appeals uit 1892–1893, in JSON met volledige tekst en bijbehorende HTML. Gebruik de uitspraakdatum (`decision_date`); de volumemetadata noemt foutief 1992–1993. Ruwe data, uploads en databases zijn nog niet opgenomen in deze repo.

De aangeleverde [CAP-link](https://case.law/caselaw/#florida) heeft een Florida-anchor; de lokale dataset is Texas en is het afgesproken corpus. Bewaar bij import de bronidentificatie en metadata. De demo geeft geen overzicht van actuele of volledige Texas-jurisprudentie.

`../coa` bevat een herbruikbare Rust-zoekkern en een voorbeeld van eerst zoeken en daarna passages aan een model aanbieden. De nieuwe app neemt gericht zoekonderdelen over; de Codex/MCP-aansturing en COA-specifieke dataset niet. Zie de architectuurgids voor de gecontroleerde codepaden.

## Frontend lokaal proberen

Gebruik Node.js 22.12+ (of 20.19+). Vanuit de repository:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/`. De ontwikkelserver luistert alleen lokaal. Typ/plak eigen tekst, voeg een PDF/TXT van maximaal 10 MiB toe, of combineer beide. Versturen toont na een korte laadstatus altijd dezelfde drie verzonnen zaken als klikbare documentvoorbeelden onder de invoerbox, op desktop naast elkaar. Een nieuwe zoekopdracht vervangt de vorige resultaten. Open een document om in een aparte leesweergave de volledige aangeleverde meerderheidstekst met markering te lezen; de terugknop brengt je naar de resultaten. Het blok ‘Waarom dit document?’ toont de exacte gevonden bronpassage en overeenkomstscore, geen gegenereerde juridische verklaring of daadwerkelijke analyse van je invoer in de demostand.

De standaarddemostand leest of verstuurt bestandsinhoud niet en slaat uploads of gesprekken niet op. De bijlage wordt alleen op naam, extensie en grootte gecontroleerd; inhoudelijke PDF/TXT-validatie en echte zoekresultaten vereisen de toekomstige backend. De fixtureteksten zijn kort en bewijzen geen leesbaarheid van lange echte uitspraken.

Gecontroleerde frontendchecks:

```sh
npm test
npm run build
```

`npm test` controleert invoermodi en grenzen, mock/API-uitwisseling, React-interacties en UTF-16-markeringen met versiecontrole. De build voert TypeScript-controle uit en schrijft `frontend/dist/` (genegeerd door Git).

Voor de latere echte API-koppeling: kopieer `frontend/.env.example` naar `frontend/.env.local`, zet `VITE_API_MODE=api`, configureer `VITE_API_BASE_URL` en herstart Vite. Deze modus verstuurt uploads naar die ingestelde backend; er is nog geen backend om deze koppeling end-to-end te proberen. De standaard blijft `mock`. Zie [de backendafspraak](docs/FRONTEND_BACKEND.md).

## Evals bekijken en bijhouden

Open het [klikbare evaluatieoverzicht](docs/evals/index.html) in een browser. Het beschrijft geplande tests en hun verwachte gedrag. De concrete benchmarkdataset, geverifieerde labels, evaluatierunner en meetresultaten zijn nog niet gebouwd; de viewer voert geen evals uit.

Onderhoud de inhoud in [docs/EVALUATIEOPDRACHT.md](docs/EVALUATIEOPDRACHT.md). Genereer daarna de leesweergave opnieuw en controleer dat bron en HTML overeenkomen:

```sh
python3 docs/evals/build.py
python3 docs/evals/build.py --check
python3 -m unittest discover -s docs/evals -p 'test_*.py'
```

De [documentatie-CI](.github/workflows/eval-docs-checks.yml) voert de synchronisatiecheck en generatortests automatisch uit bij wijzigingen aan deze evaldocumentatie. Een verouderde HTML-weergave laat de check falen. Dit valideert de documentatie, niet de kwaliteit of uitvoering van de toekomstige evals. Zie de [onderhoudsafspraken](AGENTS.md#evaluatiedocumentatie-onderhouden).
