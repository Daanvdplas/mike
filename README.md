# Mike

Mike zoekt bij een juridische vraag, PDF/TXT-document of beide de drie hoogst scorende uitspraken uit het aangeleverde Texas-corpus.
Je kunt de volledige meerderheidstekst lezen, met de gevonden bronpassage gemarkeerd.

## Hoe werkt het?

De Rustbackend zoekt lokaal met BGE-embeddings in SQLite. Orq kan de gevonden passages met je invoer vergelijken en uitleg toevoegen.
Mike gebruikt oordeelpassages (B). In de evals kies je B, head matter (A) of beide.
B1 telt twee vaste referentiezaken; E06 kan de gevonden passages met AI beoordelen. Een overeenkomstscore of AI-oordeel bewijst geen juridische juistheid.

**Verificatie:** de laatste eindcontrole gebruikte een lokale testprovider met de echte zoekengine. Zonder geldige sleutel is Orq/cloud niet opnieuw gevalideerd.

## Starten

Vereist: macOS of Linux, Python 3, Rust 1.94.1 via rustup, Node.js 22.12+ met npm, het aangeleverde corpus en de bestaande index met bijbehorende modelcache.
Voor deze volledige start is een geldige Orq-sleutel nodig. Gebruik een ingestelde servercredential of voer de sleutel verborgen in wanneer daarom wordt gevraagd.

Voer vanuit deze map één commando uit:

```sh
./start
```

De launcher controleert de benodigdheden, bouwt ontbrekende onderdelen en opent:

- [Mike](http://127.0.0.1:5176/)
- [Evaluaties](http://127.0.0.1:8798/)

Houd de terminal open; Ctrl+C stopt de eigen services. Er wordt geen index stil geïmporteerd en geen ingevoerde sleutel blijvend opgeslagen.

Configuratie, handmatige setup, grenzen en controles staan in de [uitgebreide lokale setup](docs/LOCAL_SETUP.md). Evaluatiecode, data en afspraken staan in [evals/](evals/README.md).
