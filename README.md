# Texas Legal Document Similarity Finder

Prototypecase voor een AI-consultancy: voer een juridisch document, een zoekvraag of beide in en bekijk de drie hoogst scorende uitspraken uit het aangeleverde Texas-corpus. De frontend toont per zaak de volledige tekst van het meerderheidsoordeel (majority opinion) en markeert de gevonden passages.

**Status: de Axum-router en PDF/TXT-extractie zijn met deterministische tests geïmplementeerd. Serverstart, corpusimport en de echte zoekengine worden nog gekoppeld. Er draait nog geen backend.** De JSON-fixtures zijn synthetische voorbeelden, geen modelresultaten of echte uitspraken.

## Begin hier

- [AGENTS.md](AGENTS.md): werkafspraken, eigenaarschap en onderhoud van documentatie.
- [Backendafspraak voor de frontend](docs/FRONTEND_BACKEND.md): korte overdracht om parallel te kunnen bouwen.
- [OpenAPI](docs/openapi.yaml): het canonieke, nog te implementeren API-contract.
- [Architectuurgids](docs/CODEBASE_GUIDE.md): ontwerp, zoekmethode, grenzen en actuele implementatiestatus.
- [Hoofdissues en subissues](https://github.com/Daanvdplas/adami-case/issues): uitvoering en voortgang.

## Afgesproken scope

- Rust/Axum-backend, SQLite en lokale embeddings via fastembed.
- PDF/TXT-upload, alleen een vraag of beide; minimaal één bruikbare invoer.
- Precies drie unieke zaken met metadata, overeenkomstscore en gemarkeerde passage in de volledige tekst van het meerderheidsoordeel.
- Exact zoeken over alle geïndexeerde passages. De garantie is de hoogste drie scores volgens onze zoekmethode binnen dit corpus; inhoudelijke juridische relevantie wordt apart beoordeeld.
- De Rust-library staat in `backend/`. De frontend wordt door een aparte agent in `frontend/` gebouwd en hoort niet bij deze backendwijziging.
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

De frontend-agent kan starten met [de korte backendafspraak](docs/FRONTEND_BACKEND.md) en de fixtures. De backend- en database-agent bouwen op dezelfde librarybasis in eigen branches. Een server starten of een corpus importeren kan nog niet; die commando's worden toegevoegd zodra de werking is gecontroleerd.
