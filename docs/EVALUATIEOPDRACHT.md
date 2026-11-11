# Opdracht voor een juridische retrievalbenchmark

## Status en leeswijzer

**Status: technische uitvoering beschikbaar; juridische benchmark nog ontwerp.** Er zijn **25 concrete ontwerpscenario’s** in [evals/scenarios.json](evals/scenarios.json). De Rust-CLI en de lokale [evalviewer](evals/index.html) kunnen ieder van deze scenario’s uitvoeren en ruwe resultaten bewaren. Kies op de webpagina een scenario en een zoekmethode, of vergelijk beide methodes naast elkaar. De compacte B1- en E06-kaarten blijven bovenaan beschikbaar, met daaronder een afzonderlijke kiezer voor de 25 scenario’s. B1 heeft een vaste referentiecontrole én een duidelijk gescheiden lokale zoekvariant. Vaste, onafhankelijk beoordeelde kandidaatlabels en juridische benchmarkmetingen ontbreken. Deze zichtbare ontwerpen zijn ontwikkelmateriaal, geen verborgen testset.

Een testgeval bestaat uit drie afzonderlijke onderdelen: de aangeboden invoer, onafhankelijk beoordeelde verwachte matches en de werkelijk gevonden resultaten na een run. Een juridisch bevestigd label is geen geslaagde run. Een afgeronde run is niet automatisch geslaagd. Beoordeelde relevante matches kunnen minder of meer dan drie zaken omvatten; onbekende kandidaten zijn niet automatisch irrelevant.

Bij iedere web-eval kies je **oordeelpassages (B)**, **head matter (A)** of **vergelijk beide**. De knop **Start eval** voert de gekozen lokale zoekacties achtereenvolgens uit via één draaiende Rust-engine; er wordt geen tweede embeddingproces gestart. Openen van de pagina start geen zoek- of modelaanroep. **AI-beoordeling via Orq staat standaard uit** en vereist een expliciete keuze plus servercredential. Zonder Orq blijven beide zoekmethodes en hun vergelijking bruikbaar.

De **zoekmethode** kiest de lokale bronindex; het **beoordelingsmodel** betreft uitsluitend de optionele AI-beoordeling. Bij inschakelen daarvan is het model te kiezen uit de serverallowlist. Het artefact bewaart de aangevraagde en werkelijk door de provider gerapporteerde model-ID afzonderlijk; ontbrekende provideridentiteit blijft expliciet onbekend. Een onbekend of ander model geeft een fout zonder modelvervanging. Een niet-beschikbare modelcatalogus blokkeert alleen AI-beoordeling, niet lokaal zoeken met die beoordeling uit. De vaste B1-referentie en B1-compare hebben geen AI-modelkeuze of providerstap.

De **25 canonieke scenario’s** gebruiken hun exacte Engelse vraag en/of volledige majority opinion volgens de vastgelegde invoermodus. De server controleert bronidentiteit, datum, oorspronkelijke JSON, canonieke tekstversie en bij documenten de vaste SHA-256; het zichtbare leesfragment en de Nederlandse vertaling zijn geen zoekinvoer. Ieder scenario sluit de eigen bronzaak vóór selectie van de top drie uit, voor beide methodes. E06 stuurt bijvoorbeeld uitsluitend de Engelse vraag en sluit Nixon (`156133`) uit; de herkomsttekst wordt niet meegestuurd. Verwacht gedrag en reden dienen alleen bij de optionele AI-beoordeling als rubric; ontwerpvoorbeelden zijn geen verplichte kandidaatmatches. De server bewaart invoerhash, methode, volledige zoekuitvoer, bronsectie, corpus-/model-/rankingversies, uitsluitingen en duur buiten Git. Iedere run krijgt een unieke map; methodes hebben afzonderlijke zoekbestanden. Vergelijken vereist dezelfde invoer en hetzelfde indexmanifest; een versieverschil maakt de vergelijking ongeldig.

De pagina toont de drie gevonden zaken per methode naast elkaar, met rangposities, lokale overeenkomstscore en letterlijke bronpassage. Overlap tussen de lijsten is een beschrijving van het resultaat, geen maat voor juridische relevantie. Alleen na expliciet ingeschakelde Orq-beoordeling verschijnen ook grade 0–3 en reden; deze zijn **AI-only, zonder menselijke juridische controle**. **Uitgevoerd** betekent technisch afgerond, ook bij zwakke matches of grade 0. De webvergelijking berekent geen Recall/nDCG/MRR- of accuracyclaims. De overige afspraken beschrijven de toekomstige, onafhankelijk gelabelde benchmark. Zonder lokale evalserver blijft de pagina een leesbaar scenario-overzicht. Verborgen testvragen en labels horen later niet in deze viewer.

De Rust-CLI biedt daarnaast de technische runner voor alle 25 ontwerpen en een modelvrije metriekberekening. Zonder labels zijn de kwaliteitsmetrics null en is de status not_scored.

**Daadwerkelijk gecontroleerd op 2026-11-11:** alle 25 bron-/hashbindingen zijn onafhankelijk tegen de nieuwe index gecontroleerd. De webpagina heeft **E01 (document)**, **E06 (query)** en **E11 (combined)** daadwerkelijk met A en B op dezelfde invoer en index uitgevoerd, met bronuitsluiting en opgeslagen resultaten naast elkaar. De bijbehorende run-ID’s zijn respectievelijk `1794410066-bc01577f`, `1794410066-8dc92025` en `1794410066-0fee0e7b`; hun bestanden staan buiten Git onder `~/Library/Caches/adami-case/head-matter-search/web-evals/<run_id>/result.json`. De echte CLI-run van E06 met A is technisch gecontroleerd en blijft zonder labels `not_scored`. Dit waren geen Orq-aanroepen of menselijke relevantiebeoordelingen; voor de overige 22 scenario’s wordt hiermee geen daadwerkelijke A/B-run geclaimd. Het onafhankelijke technische bewijs staat onder `~/Library/Caches/adami-case/head-matter-search/independent-review/`.

De voorbereide index bevat 135 zaken, 578 meerderheidspassages (B) en 790 head-matterpassages (A). Na deze controle zijn de featurepreviews op 8001, 5177 en 8799 gestopt en is de oorspronkelijke backend op 8000 hersteld. Een nieuwe run vereist een expliciete lokale herstart volgens README; openen van dit opgeslagen overzicht start niets.

| Invoervorm | Modus | Wat krijgt de zoekfunctie? | Waarop beoordelen we matches? |
|---|---|---|---|
| Alleen een document | `document` | De volledige majority opinion van de gekozen bronzaak. Geen vraag. | De centrale juridische onderwerpen, redenering en relevante feiten van het document. |
| Alleen een vraag | `query` | Alleen de juridische zoekvraag. Geen document of verborgen bronfeiten. | De zichtbare juridische vraag; de herkomstzaak is uitsluitend beoordelingscontext. |
| Document en vraag | `combined` | Het volledige brondocument én een specifieke juridische vraag. | Het document in het licht van de expliciete vraag, niet alleen algemene tekstovereenkomst. |

### Vooraf vaste referentiecontrole

Naast de 25 ontwerpscenario’s is één bestaande vraag uit de eerdere B1-queryset uitvoerbaar als vaste ID-controle: **Beroepsborgstelling met een opgeheven rechtbank**. De invoer is exact `Find decisions about an appeal bond that names a court which no longer exists after a judicial reorganization.`, zonder upload of uitsluiting. De versioned fixture [deterministic_b1.json](evals/deterministic_b1.json) legt vóór de eerste run de ongeordende referenties **156040 (Cummings)** en **156042 (Neubauer)** vast, met bronbewijs en corpus-/rankingcontext. De afzonderlijke preregistratiecommit is `f3d80b6`.

De gewone lokale Rustzoekactie moet precies drie geldige unieke corpuszaken leveren. De uitkomst is **Geslaagd** bij 2 van 2 vaste verwachte IDs, anders **Niet geslaagd** met het werkelijke aantal en rangen. Verkeerde corpusversies, onbekende IDs of duplicaten zijn technische fouten. Andere gevonden zaken zijn onbeoordeeld. Deze controle gebruikt geen Orq- of AI-beoordelaar en werkt zonder key. De referenties zijn door agents voorgesteld en onafhankelijk aan de aangeleverde brontekst gecontroleerd; zij zijn geen menselijke juridische goldset, volledige relevantielabels of precisie-/algemene kwaliteitsmeting. Query en targets worden niet achteraf aangepast om een run te laten slagen.


De originele B1-referentieactie accepteert uitsluitend een lege requestbody (`{}`). Zij blijft aan haar oorspronkelijke corpus-/pipeline-/modelcontext gebonden. De nieuwe dual-indexdatabase heeft een andere context: daarop geeft deze actie een technische contextfout vóór de zoekaanroep, geen nulscore of aangepast referentieoordeel. De fixture en referentie-ID’s worden niet herberekend.

Binnen dezelfde kaart is **B1-compare** een afzonderlijke lokale vergelijkingsvariant. Kies A, B of beide; de zoekfunctie ontvangt uitsluitend de exacte B1-vraag, zonder document, uitsluitingen, verwachte zaak-ID’s of broncitaten. De variant bewaart de oorspronkelijke fixtureversie en SHA-256 naast de actuele index-/model-/rankingconfiguratie en de gekozen zoekmethode. Iedere variant krijgt een eigen run-ID; technisch afgeronde uitvoer heeft `execution_status: completed` en `status: not_scored`. Er is geen vooraf-geregistreerde pass/fail-, hit- of relevantiescore, en een AI-beoordelaar is voor deze variant niet toegestaan. De E06-kaart heeft eveneens expliciete A/B/beide-keuze en houdt Nixon vóór top drie uitgesloten. De overige 24 scenario’s blijven via de aparte compacte kiezer beschikbaar.

Deze laatste UI-/API-integratie is modelvrij gecontroleerd met bronvaste fixtures en replay van eerder vastgelegde resultaten. Er is hiermee geen nieuwe native B1-compare-run, Orq-aanroep of juridische kwaliteitsmeting geclaimd. De eerder beschreven echte A/B-runs en hun herkomst blijven afzonderlijk vermeld.

## Technische eerste versie

De Rust-runner gebruikt expliciet `retrieval_method: opinion_chunks | head_matter`, standaard `opinion_chunks`. **B** vergelijkt passages uit de volledige meerderheidstekst; **A** vergelijkt afzonderlijke passages uit het redactionele voorwerk. Beide gebruiken hetzelfde lokale embeddingmodel, dezelfde invoerencoding, cosinusvergelijking, eventuele 70/30-weging en beste-passage-per-zaakregel. Er is geen BM25-, hybrid- of rerankingstrategie toegevoegd.

De runner sluit de bron-/ankerzaak vóór selectie van de top3 uit, legt invoer en corpus-/model-/methodeversies vast en schrijft ruwe resultaten plus JSON- en Markdownrapporten. Zoeklatency wordt apart van modelinitialisatie gemeten. Voer voor een CLI-vergelijking dezelfde scenarioselectie met iedere methode uit naar aparte uitvoermappen; de webvergelijking doet beide zoekacties in één run. De technische uitvoering maakt geen AI-labels en vereist geen externe modelaanroep. De ruimere benchmarkopdracht hieronder blijft een toekomstig ontwerp; die is niet volledig opgeleverd door een werkende technische runner.

Een gevonden head-matterpassage heeft `source_section: head_matter`, eigen tekstversie en posities in die sectie. Het is redactionele context en wordt niet als rechterlijke meerderheidstekst gemarkeerd. Bij openen blijft het volledige meerderheidsoordeel daarnaast beschikbaar. B-passages verwijzen naar `source_section: majority`. De aangeboden documentinvoer en bestaande labelbewijzen blijven majoritytekst, ongeacht de gekozen zoekindex.

De huidige dataset bevat geen kandidaatbeoordelingen. Een werkelijke run met deze ontwerpen is daarom `not_scored`: Recall@3, nDCG@3 en RR@3 zijn `null`, dekking is nul en alle onbeoordeelde kandidaat-ID’s blijven zichtbaar. De metriekvoorbeelden in de Rust-tests zijn expliciet synthetisch en bewijzen alleen de rekenregels. Er is geen menselijke juridische controle uitgevoerd of ingepland voor deze eerste versie.

Optionele labels worden gelezen als één JSON-object met `manifest` en `judgments`. Het manifest bevat `method` (`ai` of `synthetic`), `model` (verplicht bij AI), `created_at` en `description`. `judgments` bevat de onderstaande paarrecords, met exact dezelfde invoer, documenthash en herkomst als het scenario. Bewijs gebruikt in deze eerste versie `section: majority`; andere secties worden geweigerd. `judgment_status: verified` is een technische acceptatiestatus binnen het aangeleverde labelbestand en bewijst geen menselijke of juridische verificatie. Het manifest maakt AI- en synthetische herkomst zichtbaar; conceptlabels worden niet stilzwijgend meegenomen.

De evaluator controleert schema, invoerbinding, uitsluitingen en UTF-16-spanlengtes. De runner controleert daarnaast citaten en tekstversies exact tegen de canonieke brontekst voordat labels worden gebruikt. Onbekende kandidaten worden nooit grade 0. Met een volledig beoordeelde top3 en onvolledige corpuslabels toont het rapport uitsluitend **pooled/voorlopige** metrics met de bekende positieve noemer en het poolideaal. Zodra een top3-kandidaat onbeoordeeld is, blijven alle kwaliteitsmetrics voor dat scenario `null`. Complete en pooled gemiddelden staan apart.

De hoofdgemiddelden bevatten alleen scenario’s met minstens één bekende positieve kandidaat. Elk gemiddelde vermeldt zijn eigen noemer; ongedefinieerde waarden worden niet als nul meegenomen. Scenario’s zonder positieve labels blijven zichtbaar: RR is nul, Recall is ongedefinieerd en nDCG kan bij uitsluitend grade 1 wel bestaan. Een werkelijk corpus-Recallplafond wordt alleen bij volledige beoordelingen getoond. Latencypercentielen gebruiken nearest rank, met aantal waarnemingen en een waarschuwing bij minder dan twintig samples. De kleine zichtbare ontwikkelset rechtvaardigt geen algemene juridische nauwkeurigheidsclaim.

## Doel en afbakening

Bouw een reproduceerbare benchmark waarmee het ontwikkelteam kan beoordelen of de zoekfunctie juridisch relevante uitspraken vindt. Streef naar **25 basisscenario’s**, met 20–30 als toegestane bandbreedte, plus onderstaande stressvarianten. Ondersteun **een document en/of een vraag**: document-only (`document`), query-only (`query`) en beide (`combined`). Neem minstens vijf basisscenario’s per modus op binnen dit totaal. Beoordeel de eerste drie gevonden zaken op hun bruikbaarheid voor de daadwerkelijk aangeboden invoer.

Deze ruimere opdracht betreft nog te bouwen beoordelingen, verborgen scenariofamilies en diagnostische uitbreidingen boven op de technische eerste versie. De bestaande [Hit@3-proef](https://github.com/Daanvdplas/adami-case/issues/15) en [onafhankelijke rankingtests](https://github.com/Daanvdplas/adami-case/pull/21) vervangen deze benchmark niet. **Gebruik dezelfde top3 als het [productcontract](openapi.yaml).** Het systeem retourneert precies drie unieke zaken; de benchmark beoordeelt of deze ook relevant zijn. Er is geen aparte ingang voor meer resultaten nodig.

Dit test retrieval: vinden de juiste zaken en passages de weg naar de gebruiker? Het test geen volledige AI-agent met antwoordgeneratie of toolplanning. Daarvoor is later een aparte eind-tot-eindsuite nodig, onder meer voor brongetrouwheid, correcte toolresultaten en het negeren van instructies in documenten. Houd eventuele aanvalsteksten buiten de juridische brondata en labels. Die uitbreiding valt buiten deze opdracht.

## Corpus en brongebruik

Gebruik uitsluitend `/Users/R0GUE/Downloads/texas-criminal-reports/`: 135 uitspraken met JSON in `json/`, bijbehorende HTML in `html/` en bronmetadata in `metadata/`. Ze behoren tot volume **31 Texas Criminal Reports**, Texas Court of Criminal Appeals, met uitspraakdatums in 1892–1893. [CAP Texas](https://case.law/caselaw/#texas) is de collectie-ingang; de benchmarkgrens wordt bepaald door deze lokale bestanden, niet door alle online Texas-zaken. CAP levert geen relevantielabels voor deze opdracht. De [officiële errata](https://github.com/harvard-lil/capstone#errata) waarschuwen voor OCR- en metadatafouten; corrigeer twijfelgevallen niet ongemerkt.

Gebruik `decision_date` per zaak. `VolumeMetadata.json` vermeldt foutief 1992–1993 in `start_year`, `end_year` en de overeenkomstige `spine`-velden; `publication_year` is 1893. Behoud de bronmetadata en registreer deze afwijking.

Gebruik, wanneer een document wordt aangeboden, uitsluitend de canonieke tekst van `casebody.opinions[].text` met `type: majority`. Leg normalisatie, `text_version` en SHA-256 van de exacte invoertekst vast. Bewaar `head_matter` afzonderlijk als redactionele context en zoekindex voor methode A; voeg deze niet aan de documentinvoer toe. Benoem concurrence en dissent volgens hun eigen type; schrijf hun redenering niet aan de meerderheid toe. Controleer bewijs tegen de oorspronkelijke tekst. Aanwezige tekstvelden bewijzen geen foutloze OCR of inhoudelijke volledigheid. Verzin geen zaken, citaties of citaten.

## Scenarioselectie en relevantie

Laat de scenarioschrijver eerst de bronzaak lezen, zonder kandidaatmatches, zoekresultaten of rankings te zien. Schrijf voor `query` en `combined` een concrete Engelse rechtsvraag op basis van deze werkelijke broninhoud; verzin geen aanvullende feiten. Vermijd overgenomen passages, zaaknamen, zaak-ID’s en citaties in de vraag. Bij `query` blijft de bronzaak uitsluitend verborgen herkomst voor beoordeling, nooit aanvullende modelinvoer. Bij `document` wordt geen vraag meegestuurd. Selecteer gevarieerde rechtsvragen, feiten, documentlengtes en procedurele situaties.

Leg per scenario de rechtsvraag, beslissing op die vraag en dragende feitelijke voorwaarden vast. De volgende dekking is verplicht; overlap tussen categorieën mag:

| Moeilijke categorie | Wat moet de test onderscheiden? | Verwachting | Minimum |
|---|---|---|---|
| Vergelijkbare feiten, andere rechtsvraag | Een kandidaat lijkt door de feiten bruikbaar, maar behandelt een andere juridische vraag. | Herken de oppervlakkige match als niet of zijdelings relevant, met bronbewijs; hetzelfde delict volstaat niet. | 4 basisscenario’s |
| Andere feiten, dezelfde rechtsvraag | Een kandidaat behandelt de juridische kern ondanks een ander feitencomplex of weinig gedeelde woorden. | Vind de juridisch bruikbare kandidaat en onderbouw welke rechtsregel of redenering aansluit. | 4 basisscenario’s |
| Dezelfde rechtsvraag, tegengestelde beslissing | De beslissing op dezelfde rechtsvraag verschilt; de kandidaat biedt relevante onderscheidende redenering. | Sluit de kandidaat niet uit vanwege de uitkomst; verklaar de juridisch relevante verschillen. | 4 basisscenario’s |

Alleen een andere einduitspraak, bijvoorbeeld vernietiging wegens een andere fout, voldoet niet aan de derde categorie. Kan het corpus een minimum niet dragen, meld het tekort als acceptatiepunt; verzin geen passende paren.

Voeg bij vraagbevattende scenario’s minstens **vijf parafrases** toe die dezelfde juridische betekenis behouden, met onafhankelijk gecontroleerde gelijkblijvende labels. Voeg bij minstens **drie combined-scenario’s met meerdere rechtsvragen** een tweede echte vraag toe bij hetzelfde document, met nieuwe kandidaatbeoordelingen. Deze issuewissels testen of de vraag het resultaat werkelijk stuurt. Koppel varianten aan hun basisscenario; tel ze niet als onafhankelijke basisscenario’s. Rapporteer hun scores en gepaarde veranderingen afzonderlijk.

Beoordeel ieder kandidaatpaar **gegeven uitsluitend de zichtbare invoer van zijn modus**. Bij `document` gaat het om de centrale juridische onderwerpen en materiële feiten van het document, zonder verborgen focusvraag; bij `query` om de expliciete vraag, zonder verborgen feiten uit de herkomstzaak; bij `combined` om het document in het licht van de vraag. Beoordeel labels per modus zelfstandig: querygerichte labels gelden niet automatisch voor document-only. Onderbouw rechtsvraag, redenering en materiële feiten; gedeelde woorden, delict of uitkomst volstaan niet. Leg schaal en positieve drempel **grade ≥ 2** vooraf vast.

| Grade | Betekenis |
|---|---|
| 0 | De kandidaat helpt niet bij de zichtbare juridische informatiebehoefte; eventuele feitelijke of woordelijke overeenkomst is oppervlakkig. |
| 1 | Er is een zijdelings verband, maar onvoldoende toepasselijke juridische behandeling om wezenlijk te helpen. |
| 2 | De kandidaat behandelt een relevante rechtsvraag of redenering en biedt bruikbare ondersteuning, met beschreven beperkingen of verschillen. |
| 3 | De kandidaat sluit rechtstreeks aan op de centrale juridische informatiebehoefte en biedt sterke vergelijkbare of onderscheidende redenering; een tegengestelde uitkomst sluit dit niet uit. |

Een lokaal gecontroleerd ontwikkelvoorbeeld is **Nixon v. State**, `156133`, `json/0205-01.json`, tegenover **Kelley v. State**, `156056`, `json/0211-01.json`. Nixon zegt over ander feitenbewijs: “This testimony did not tend to identify any fact or circumstance which could aid in developing the res gestae”; Kelley: “This evidence was properly admitted.” Dit biedt een mogelijke vraag naar de vereiste samenhang tussen ander delictbewijs en het vervolgde feit. Verschillende toepassingsfeiten verklaren de verschillende beslissingen; dit bewijst geen doctrinaire tegenspraak. Kelley citeert Nixon: controleer dus ook zoeken via citaties. Dit zichtbare voorbeeld is geen verborgen test of definitief gelabeld paar; het team moet vraag en volledig bewijs nog vastleggen.

## Dataset en bewijs

Lever `eval_dataset.json` als array met één record per uniek `(scenario_id, candidate_case_id)`. Gebruik de gevraagde veldnamen en voeg identificatie en beoordelingsstatus toe:

```text
scenario_id: string
input_mode: "document" | "query" | "combined"
query_case_id: string | null
document_ref: {case_id, text_version, sha256} | null
query: string | null
candidate_case_id: string
relevance_grade: integer 0..3
reasoning: string
evidence: array van bewijsobjecten
judgment_status: "verified"
```

`document_ref` verwijst naar de exacte aangeboden majoritytekst. `document` vereist een niet-leeg document en `query: null`; `query` vereist niet-lege vraagtekst en `document_ref: null`; `combined` vereist beide. Minstens één invoer is bruikbaar. `query_case_id` registreert een bron- of vraaganker en is zelf geen modelinvoer. Leg herkomst zonder uniek anker vast in het manifest. Herhaalde records met hetzelfde `scenario_id` hebben identieke modus, input en herkomst. `reasoning` verklaart het paar, ook bij grade 0; geen keywordmatch is geen bewijs van irrelevantie.

Bewijs bevat exacte passages uit de kandidaat en de bronzaak of gedocumenteerde herkomst van de vraag. Bij query-only dient herkomstbewijs voor controle; voeg hiermee geen onzichtbare voorwaarden aan de relevantiebeoordeling toe. Ieder bewijsobject vermeldt `case_id`, sectie of opiniontype, `text`, `start_utf16`, `end_utf16` en `text_version`. Gebruik nulgebaseerde UTF-16-posities met exclusief einde volgens de [projectafspraak](FRONTEND_BACKEND.md). De uitsnede moet exact gelijk zijn aan `text`. Benoem de canonieke sectietekst; majority en head matter hebben eigen versies. Bewaar SHA-256 van die exacte UTF-8-tekst en hashes van bronbestanden.

Registreer auteurs, beoordelaars, datum, beoordelingsmethode, eventuele modelversie en herkomst van voorstellen in een gekoppeld manifest of beoordelingslog. Houd identiteiten van maker, onafhankelijke beoordelaar en eventuele beslisser uit elkaar.

## Beoordeling en dekking

Bewaar automatisch voorgestelde labels afzonderlijk, bijvoorbeeld in `proposed_labels.json`. Laat een andere beoordelaar zelfstandig oordelen zonder rankings, scores of het oorspronkelijke voorgestelde oordeel te zien. Vergelijk daarna de beoordelingen, leg verschillen vast en laat een afzonderlijke beslisser geschillen beslechten. Alleen geaccepteerde, onafhankelijk gecontroleerde labels komen in de vaste benchmarkversie. Een onafhankelijke AI-controle is geen juridisch deskundigenoordeel; voor een betrouwbare juridische goldstandard is controle door een juridisch deskundige vereist. Vermeld welke controle werkelijk heeft plaatsgevonden.

**Voorkeur: beoordeel alle toegestane kandidaten per scenario.** Bij uitsluiting van één bron- of ankerzaak blijven 134 zaken over: voor 25 basisscenario’s 3.350 kandidaatparen, exclusief issuewissels. Een vraag zonder uniek anker heeft niet automatisch 134 kandidaten; leg de werkelijke telling vast. Volledige beoordeling bepaalt de Recallnoemer en ideale rangorde.

Als volledige beoordeling niet haalbaar is, stel vooraf een pool samen met meerdere verschillende zoekstrategieën en handmatige ontdekking. Rapporteer per scenario hoeveel kandidaten beoordeeld zijn en welke mogelijk relevante kandidaten nog openstaan, met ID en reden voor nader onderzoek. `unjudged` betekent niet grade 0. Bewaar openstaande paren buiten de geverifieerde dataset.

Noem scores met onvolledige beoordelingen **pooled en voorlopig**. Claim geen ongekwalificeerde corpus-Recall of automatische ondergrens: delen door alleen bekende positieve labels kan zowel misleiden als vergelijkingen bevoordelen. Vindt een nieuwe strategie een onbeoordeelde kandidaat in haar top3, rapporteer die run als onvolledig beoordeeld en niet definitief vergelijkbaar. Werk labels gecontroleerd bij in een nieuwe benchmarkversie en beoordeel alle vergeleken runs opnieuw.

## Voorkomen van datalekken

Sluit volgens vooraf vastgelegde benchmarkpolicy het aangeboden brondocument en de concrete zaak waaraan een vraag is ontleend uit, ook bij query-only. Sluit bij een ongebonden vraag geen willekeurige ankerzaak uit. Pas uitsluitingen toe vóór top3selectie met dezelfde productscorer en sortering. Verwijder geen selfmatch uit een al afgeknotte API-top3: dan ontbreekt een geldige vervanger. Onderzoek exacte en bijna-dubbele teksten, herpublicaties en overgenomen passages. Leg per modus/scenario de bronafgeleide duplicaten, uitsluitingen en toegestane kandidaten vast.

Splits ontwikkel- en testscenario’s op bronfamilie en rechtsvraagfamilie, inclusief duplicaatgroepen; alle varianten blijven bij hun familie. Reserveer minstens vijf onafhankelijke bronfamilies als verborgen test. Houd hun vragen en labels afgeschermd voor mensen en agents die zoekmethoden afstellen. Het kandidaatcorpus blijft vast: verwijder geen zaken uitsluitend vanwege hun ontwikkel- of testrol. Alleen vooraf vastgelegde uitsluitingen gelden per scenario.

De zoekmethode mag het corpus en uitsluitend de scenario-invoer gebruiken, geen verborgen vraaganker, relevantielabels, beoordelingsredenen of bewijsselecties. Controleer of directe zaakverwijzingen of gekopieerde tekst het bedoelde juridische zoekprobleem omzeilen en leg beleid vooraf vast. Bevries corpus- en teksthashes, scenario’s, splits, labels, passageverdeling, model en rankinginstellingen. Gebruik testprestaties niet om achteraf gunstige scenario’s of labels te kiezen.

## Diagnostiek voor moeilijke gevallen

Vergelijk binnen iedere modus de beschikbare zoekmethoden met BM25, dense zoeken en een eenvoudige controle op metadata, citaties of termoverlap. Geef geen methode invoer die in dat scenario ontbreekt. Vergelijk bij `combined` aanvullend document-only en query-only als diagnostiek, met zelfstandig beoordeelde labels voor de gewijzigde invoer. Leg configuraties vooraf vast; eis geen vooraf gekozen winnaar.

Maak voor minstens vijf geschikte scenario’s een deterministische variant met gemaskeerde verwijzingen of namen in de daadwerkelijk aanwezige invoer en index; voeg geen ontbrekend document toe. Bewaar originelen als bewijs, hash afgeleide versies en controleer betekenisbehoud. Verander geen procesrollen of materiële feiten. Selecteer deze gevallen vóór prestatiemeting.

Beoordeel bij gevonden top3-zaken ook afzonderlijk of de aangeboden passage de bij de zichtbare invoer passende rechtsregel of toepassing ondersteunt, uit de juiste opinion komt en geen verworpen standpunt als beslissing presenteert. Accepteer een andere juiste passage dan het vooraf geselecteerde citaat. Rapporteer verkeerde zaken, juiste zaken met verkeerde passages, hard negatives en falende issuewissels apart.

## Evaluatiescript en meetafspraken

De technische eerste versie leest scenario’s en optionele labels en legt een runbestand vast; de onderstaande afspraken blijven ook gelden voor verdere benchmarkuitbreidingen. Het runbestand is een array van `{scenario_id, input_mode, ranked_case_ids}`, met per scenario **nul tot drie** geordende, unieke zaak-ID’s. De runner biedt exact de vastgelegde invoervelden aan en controleert de gerapporteerde modus. Succes levert drie zaken na uitsluitingen; kortere lijsten blijven zichtbaar als tekortkoming. Weiger modusconflicten, langere lijsten, onbekende ID’s, duplicaten, uitgesloten zaken en ontbrekende of dubbele scenario’s. Sorteer ties op `case_id` lexicografisch oplopend, na score aflopend.

Bewaar daarnaast de volledige zoekuitvoer, gekoppeld aan run en scenario: per zaak de aangeboden passage, tekstversie en offsets, plus corpus-, model- en rankingconfiguratie. Deze uitvoer maakt passagebeoordeling en herhaling mogelijk; alleen zaak-ID’s volstaan daarvoor niet.

Bereken per scenario, met rangposities vanaf 1:

- **Recall@3:** aantal resultaten met grade ≥ 2 in de eerste drie, gedeeld door alle kandidaten met grade ≥ 2 binnen de voor dat scenario toegestane kandidaten. Bepaal telling en uitsluitingen volgens de vastgelegde modus- en herkomstpolicy.
- **nDCG@3:** `DCG@3 = Σ (2^grade_i − 1) / log2(i + 1)`, voor maximaal drie resultaten. Deel door `IDCG@3`: dezelfde formule voor de drie hoogste grades uit alle toegestane, beoordeelde kandidaten.
- **RR@3:** `1 / rang` van de eerste kandidaat met grade ≥ 2 binnen rang 1–3, anders 0. **MRR@3** is het gemiddelde van deze waarden.

Bij volledige beoordelingen is `R` het aantal positieve kandidaten en het Recall@3-plafond `min(3, R) / R` voor `R > 0`. Bij meer dan drie is Recall 1 onmogelijk; bij minder dan drie zijn geen drie relevante resultaten beschikbaar. Meld deze schaarste en verhoog geen grades. Bij pooling kennen we uitsluitend beoordeelde positieven: rapporteer `R_known` en hoogstens het ideaal binnen de pool, niet het werkelijke corpusplafond of bewezen schaarste. Drie outputzaken betekent niet drie goldpositives. Verander de metrieknoemer niet om het plafond te compenseren.

Rapporteer macro-gemiddelden, dus ieder scenario weegt gelijk, plus scores per invoermodus en moeilijke categorie. Een lege ranking scoort 0 wanneer positieve kandidaten bestaan. Flag scenario’s zonder positieve kandidaat: Recall is ongedefinieerd; nDCG is ongedefinieerd bij `IDCG = 0`, maar kan bij uitsluitend grade 1 nog berekenbaar zijn. Rapporteer dit afzonderlijk, met RR = 0. Vereis voor de hoofdvergelijking scenario’s met minstens één positieve kandidaat en publiceer iedere uitsluiting en noemer; pas scenarioselectie niet aan op zoekprestaties.

Toon verschillen tussen methoden en parafrases per scenario, plus onzekerheid berekend met bronfamilies als eenheid; varianten zijn geen extra onafhankelijke waarnemingen. Rapporteer labelovereenstemming, verschillen over de grens tussen grade 1 en 2, en beslissingen bij geschillen. De kleine set rechtvaardigt geen algemene claim over alle juridische vragen of agentgedrag.

De gain- en rangformules volgen [Microsoft Research over NDCG en MRR](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tr-2008-179.pdf); [de retrievaldocumentatie](https://learn.microsoft.com/en-us/azure/databricks/ai-search/retrieval-quality-eval) beschrijft ook Recall als aandeel gevonden relevante documenten. De hier vastgelegde cutoff en juridische beoordelingsschaal zijn benchmarkafspraken.

## Oplevering en acceptatie

Lever dataset, labelvoorstellen, schema, manifest, beoordelingslog, dekkingsoverzicht en script met gebruiksinstructies. Test document-only, query-only en combined met hun eigen invoer en labels; beide invoeren leeg is een aparte negatieve contracttest, geen retrievalscenario. Voeg abstracte metriekvoorbeelden toe met verwachte scores, inclusief lege rankings, ongeldige IDs, selfmatches, ontbrekende scenario’s, nul positieve labels en onvolledige beoordelingen.

Acceptatie vereist 20–30 basisscenario’s met minstens vijf per invoermodus, de minima per moeilijke categorie en stressvariant, exacte invoer en modusgebonden labels, controleerbaar bewijs, onafhankelijke labelcontrole, verborgen testfamilies en reproduceerbare diagnostiek. Voor een juridische goldstandard controleert een juridisch deskundige ook moeilijke paren en betekenisbehoud van varianten; AI-only labels blijven voorlopig. Meld ontbrekende corpusdekking expliciet.

Leg kwaliteitsdoelen voor het zoeksysteem vast op een afzonderlijke ontwikkelset, vóór de verborgen test. Levering van een correcte benchmark is een andere acceptatiebeslissing dan voldoende zoekkwaliteit. Publiceer uitsluitend werkelijk gemeten scores en onderbouw of het systeem de vooraf vastgelegde doelen haalt.
