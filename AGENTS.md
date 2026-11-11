# Werken in deze repo

Lees eerst [README.md](README.md) voor scope en status. Lees daarna de relevante delen van de [architectuurgids](docs/CODEBASE_GUIDE.md).

- **Frontend:** begin bij [de backendafspraak](docs/FRONTEND_BACKEND.md), het [API-contract](docs/openapi.yaml) en de bijbehorende fixtures. Werk in de toekomstige map `frontend/`.
- **Backend/database:** werk in `backend/`. Het API-contract ligt vast voor parallel frontendwerk; stem wijzigingen eerst af met de coördinator.
- **Evaluaties:** begin bij het [klikbare overzicht](docs/evals/index.html). Onderhoud de afspraken in de [canonieke evaluatieopdracht](docs/EVALUATIEOPDRACHT.md) en concrete ontwerpbeschrijvingen in [scenarios.json](docs/evals/scenarios.json); de HTML wordt uit beide bronnen gegenereerd.
- **Taakverdeling en voortgang:** gebruik de hoofdissues en gekoppelde subissues op GitHub. Claim een subissue vóór je begint; houd wijzigingen beperkt tot die taak.

## Rollen en werkwijze

- De coördinator verduidelijkt de opdracht en stuurt agents aan; deze schrijft geen bestanden en voert geen reviews of tests uit. Uitvoerende agents implementeren; andere agents reviewen en testen onafhankelijk.
- Alle productcodewijzigingen, inclusief tests, dependencies, build, CI en productconfiguratie, gaan via een branch en pull request. Commit deze wijzigingen nooit rechtstreeks naar `main`. Merge pas na expliciet akkoord van de gebruiker. Alleen de initiële documentatiebootstrap mag als eerste commit op `main` landen.
- Commits zijn bewust unsigned: `commit.gpgsign=false`.
- Verander geen werk van andere agents. Houd frontend- en backendwijzigingen gescheiden en stem gedeelde contractwijzigingen af.
- Gebruik de `dev-browser`-skill en `dev-browser`-CLI nooit, ook niet via subagents.
- Houd uitleg kort en begrijpelijk. Gebruik in de UI weinig kleur, alleen voor betekenis of status. UI-werk moet later lokaal in de browser worden getoond en via echte gebruikershandelingen worden getest met een ander beschikbaar hulpmiddel.

## Productafspraken

- Invoer: document **en/of** vraag. Uitvoer: precies **drie unieke uitspraken**, met de volledige tekst van het meerderheidsoordeel (majority opinion) en markeerbare bronpassages.
- De garantie betreft de hoogste scores binnen het volledige afgesproken corpus volgens de vastgelegde zoekmethode; beloof geen absolute juridische relevantie.
- Volg [OpenAPI](docs/openapi.yaml) voor veldnamen, foutgevallen en tekstposities. Verander die niet stilzwijgend.
- De eerste versie gebruikt lokale embeddings. Orq-antwoordgeneratie en Codex/MCP horen niet bij deze scope.
- Commit nooit sleutels, uploads, modelcaches of de lokale database. Gebruik geen externe modeldienst zonder taakautorisatie.

## Architectuurgids onderhouden

- [docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md) is de canonieke architectuurgids. Verifieer relevante beschrijvingen aan de broncode vóór codewijzigingen.
- Werk bij veranderd gedrag of architectuur de betrokken hoofdstukken in dezelfde taak, pull request en changeset bij. Houd diagrammen, codeverwijzingen, ontwerpafwegingen, beperkingen en recente architectuurwijzigingen actueel; integreer wijzigingen in de bestaande uitleg.
- Onderscheid geverifieerde implementatie, voorgenomen ontwerp en onbekenden. Claim geen werkende endpoints, setup of tests zolang die niet bestaan.
- Rapporteer bij afronding of de gids is bijgewerkt en waarom. Laat de gids bij wijzigingen zonder documentatie-impact ongemoeid en leg dat kort uit.
- Laat een onafhankelijke agent relevante checks uitvoeren. De echte backendchecks staan in README; voeg bij nieuw gedrag passende tests toe en houd tests met modeldownloads buiten de deterministische standaardchecks.

## Evaluatiedocumentatie onderhouden

- Houd invoermodi, verwacht gedrag, beoordelingsregels, metrics en status actueel in [docs/EVALUATIEOPDRACHT.md](docs/EVALUATIEOPDRACHT.md). Werk bij toekomstige wijzigingen ook betrokken dataset-, label- en runverwijzingen in dezelfde changeset bij.
- Onderhoud concrete scenario-invoer, verwacht gedrag, reden en bronbewijs in [docs/evals/scenarios.json](docs/evals/scenarios.json). Ontwerpbeschrijvingen zijn geen kandidaatlabels of meetresultaten; voeg die niet onder dezelfde status toe. Engelse zoekvragen zijn exacte invoer, Nederlandse tekst is uitsluitend leesvertaling.
- Wijzig de gegenereerde HTML niet met de hand. Genereer opnieuw met `python3 docs/evals/build.py` en controleer synchronisatie met `python3 docs/evals/build.py --check`.
- De [documentatie-CI](.github/workflows/eval-docs-checks.yml) controleert bron-/HTML-synchronisatie en de generator bij wijzigingen aan de evaluatiedocumentatie. Dit zijn geen benchmarkruns.
- Onderscheid gepland, gebouwd en daadwerkelijk uitgevoerd. Een beschikbare viewer bewijst geen beschikbare evalset, runner of meetresultaten; toon uitsluitend bestaande resultaten met hun herkomst.
