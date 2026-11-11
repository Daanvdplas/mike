#!/usr/bin/env python3
"""Build the offline documentation view. This does not build or run evaluations."""

import argparse
import hashlib
import html
from pathlib import Path
import re
import sys
import unicodedata


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "EVALUATIEOPDRACHT.md"
OUTPUT = HERE / "index.html"


def inline(text):
    """Render the small Markdown subset used by the canonical assignment; escape HTML."""
    parts = re.split(r"(`[^`]+`|\*\*.+?\*\*|\[[^\]]+\]\([^)]+\))", text)
    rendered = []
    for part in parts:
        if part.startswith("`") and part.endswith("`"):
            rendered.append("<code>" + html.escape(part[1:-1]) + "</code>")
        elif part.startswith("**") and part.endswith("**"):
            rendered.append("<strong>" + inline(part[2:-2]) + "</strong>")
        elif re.fullmatch(r"\[[^\]]+\]\([^)]+\)", part):
            label, href = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part).groups()
            if re.match(r"https?://", href):
                safe_href = href
            elif ":" in href or href.startswith("//"):
                rendered.append(html.escape(part))
                continue
            else:
                safe_href = "../" + href
            rendered.append(f'<a href="{html.escape(safe_href, quote=True)}">{inline(label)}</a>')
        else:
            rendered.append(html.escape(part))
    return "".join(rendered)


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def sections(source):
    result = {}
    for item in re.split(r"(?m)^## ", source)[1:]:
        title, _, body = item.partition("\n")
        result[title] = body.strip()
    for required in ["Status en leeswijzer", "Doel en afbakening", "Scenarioselectie en relevantie", "Diagnostiek voor moeilijke gevallen", "Voorkomen van datalekken"]:
        if required not in result:
            raise ValueError(f"Vereiste bronsectie ontbreekt: {required}")
    return result


def table_rows(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                rows.append(cells)
        elif rows:
            break
    return rows


def markdown(source):
    """No dependencies, raw HTML, images, or arbitrary embedded content."""
    lines = source.splitlines()
    output = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.startswith("# "):
            i += 1
        elif line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            i += 1
        elif line.startswith("## "):
            title = line[3:]
            output.append(f'<h3 id="bron-{slug(title)}">{inline(title)}</h3>')
            i += 1
        elif line.startswith("|"):
            rows = table_rows("\n".join(lines[i:]))
            output.append('<div class="table-scroll" tabindex="0" role="region" aria-label="Tabel uit de opdracht"><table><thead><tr>')
            output.extend("<th>" + inline(cell) + "</th>" for cell in rows[0])
            output.append("</tr></thead><tbody>")
            for row in rows[1:]:
                output.append("<tr>" + "".join("<td>" + inline(cell) + "</td>" for cell in row) + "</tr>")
            output.append("</tbody></table></div>")
            while i < len(lines) and lines[i].startswith("|"):
                i += 1
        elif re.match(r"[-*] ", line):
            output.append("<ul>")
            while i < len(lines) and re.match(r"[-*] ", lines[i]):
                output.append("<li>" + inline(lines[i][2:]) + "</li>")
                i += 1
            output.append("</ul>")
        else:
            paragraph = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"(?:## |```|\||[-*] )", lines[i]):
                paragraph.append(lines[i])
                i += 1
            output.append("<p>" + inline(" ".join(paragraph)) + "</p>")
    return "\n".join(output)


def render(source):
    content = sections(source)
    status = content["Status en leeswijzer"]
    if "**Status: gepland.**" not in status:
        raise ValueError("De viewer ondersteunt nu uitsluitend een geplande evaluatieset; pas de presentatie bewust aan bij nieuwe status.")
    modes = table_rows(status)[1:]
    if len(modes) != 3 or any(len(row) != 4 for row in modes):
        raise ValueError("De bron moet drie invoervormen met vier kolommen bevatten.")
    challenges = table_rows(content["Scenarioselectie en relevantie"])[1:]
    if len(challenges) != 3 or any(len(row) != 4 for row in challenges):
        raise ValueError("De bron moet drie moeilijke categorieën met vier kolommen bevatten.")
    goal_match = re.search(r"\*\*(\d+) basisscenario", content["Doel en afbakening"])
    if not goal_match:
        raise ValueError("Het streefgetal voor basisscenario’s ontbreekt in de bron.")
    target = goal_match.group(1)
    paragraphs = content["Scenarioselectie en relevantie"].split("\n\n")
    variants = next((p for p in paragraphs if p.startswith("Voeg bij vraagbevattende")), None)
    masking = next((p for p in content["Diagnostiek voor moeilijke gevallen"].split("\n\n") if p.startswith("Maak voor minstens")), None)
    if not variants or not masking:
        raise ValueError("Bronafspraken voor parafrases, issuewissels of naam-/citatiemaskering ontbreken.")

    def count(pattern, text):
        match = re.search(pattern, text)
        if not match:
            raise ValueError("Een minimumaantal ontbreekt in de canonieke bron.")
        value = match.group(1)
        numbers = {"een": "1", "twee": "2", "drie": "3", "vier": "4", "vijf": "5", "zes": "6", "zeven": "7", "acht": "8", "negen": "9", "tien": "10"}
        return numbers.get(value, value)

    def item(identifier, title, minimum, body, source_section):
        return f'''<details class="eval-item" id="{identifier}"><summary><span class="eval-title">{inline(title)}</span><span class="eval-minimum">{inline(minimum)}</span><span class="chevron" aria-hidden="true"></span></summary><div class="eval-detail">{body}<div class="detail-footer"><span>Testgeval en verwachte matches nog te maken.</span><a href="#bron-{slug(source_section)}">Bijbehorende afspraken <span aria-hidden="true">↗</span></a></div></div></details>'''

    def description(label, text):
        return f'<div><dt>{label}</dt><dd>{inline(text)}</dd></div>'

    mode_minimum = count(r"Neem minstens (\w+) basisscenario", content["Doel en afbakening"])
    mode_items = []
    for label, mode_code, offered, expectation in modes:
        mode = mode_code.strip("`")
        if mode not in {"document", "query", "combined"}:
            raise ValueError("Onbekende invoermodus in de bron.")
        body = '<dl class="test-fields">' + description("Input", offered) + description("Verwachte matches", expectation) + description("Resultaat", "Nog niet uitgevoerd. Later zie je hier de drie gevonden zaken en hun bronpassages.") + '</dl>'
        mode_items.append(item(f"eval-{mode}", label, f"Min. {mode_minimum}", body, "Status en leeswijzer"))

    challenge_items = []
    for title, question, expected, minimum in challenges:
        body = '<dl class="test-fields">' + description("Testopzet", question) + description("Verwachte beoordeling", expected) + description("Input", "Een passend document, een vraag of beide; de concrete bron en vraag zijn nog niet gekozen.") + '</dl>'
        challenge_items.append(item(f"eval-{slug(title)}", title, minimum.replace(" basisscenario’s", ""), body, "Scenarioselectie en relevantie"))

    para_minimum = count(r"minstens \*\*(\w+) parafrases", variants)
    switch_minimum = count(r"minstens \*\*(\w+) combined", variants)
    mask_minimum = count(r"minstens (\w+) geschikte", masking)
    leakage = content["Voorkomen van datalekken"]
    hidden = next((p for p in leakage.split("\n\n") if p.startswith("Splits ontwikkel-")), None)
    if not hidden:
        raise ValueError("De afspraak voor verborgen testfamilies ontbreekt.")
    hidden_minimum = count(r"minstens (\w+) onafhankelijke", hidden)
    paraphrase, _, switches = variants.partition(" Voeg bij minstens")
    variant_items = [
        item("eval-parafrase", "Dezelfde vraag, anders verwoord", f"Min. {para_minimum} varianten", '<dl class="test-fields">' + description("Input", "Een andere formulering van dezelfde juridische vraag, met hetzelfde document als dat bij de oorspronkelijke test hoort.") + description("Verwachting", "Dezelfde juridische betekenis en onafhankelijk gecontroleerde gelijkblijvende relevantielabels.") + '</dl><p class="source-note">' + inline(paraphrase) + '</p>', "Scenarioselectie en relevantie"),
        item("eval-issuewissel", "Andere vraag bij hetzelfde document", f"Min. {switch_minimum} varianten", '<dl class="test-fields">' + description("Input", "Hetzelfde document met een tweede echte rechtsvraag.") + description("Verwachting", "De resultaten sluiten aan op de gewijzigde vraag. De kandidaatmatches worden hiervoor opnieuw beoordeeld.") + '</dl><p class="source-note">' + inline("Voeg bij minstens" + switches) + '</p>', "Scenarioselectie en relevantie"),
        item("eval-maskering", "Zonder zaaknamen en citaties", f"Min. {mask_minimum} varianten", '<dl class="test-fields">' + description("Input", "De aanwezige invoer en index met gemaskeerde namen en verwijzingen; geen document toevoegen bij een vraag zonder document.") + description("Verwachting", "De zoekfunctie blijft juridisch bruikbare zaken vinden zonder makkelijke herkenningspunten.") + '</dl><p class="source-note">' + inline(masking) + '</p>', "Diagnostiek voor moeilijke gevallen"),
        item("eval-verborgen", "Vooraf apart gehouden tests", f"Min. {hidden_minimum} bronfamilies", '<dl class="test-fields">' + description("Input", "Onafhankelijke testfamilies die niet beschikbaar zijn tijdens het afstellen van de zoekmethode.") + description("Verwachting", "De kwaliteit wordt gemeten op vooraf afgeschermde vragen en labels; die worden niet in deze viewer meegeleverd.") + '</dl><p class="source-note">' + inline(hidden) + '</p>', "Voorkomen van datalekken"),
    ]
    source_navigation = "".join(f'<li><a href="#bron-{slug(title)}">{html.escape(title)}</a></li>' for title in content)
    replacements = {
        "STYLE": (HERE / "viewer.css").read_text(),
        "SCRIPT": (HERE / "viewer.js").read_text(),
        "TARGET": target,
        "MODE_ITEMS": "\n".join(mode_items),
        "CHALLENGE_ITEMS": "\n".join(challenge_items),
        "VARIANT_ITEMS": "\n".join(variant_items),
        "SOURCE_NAVIGATION": source_navigation,
        "SPECIFICATION": markdown(source),
        "HASH": hashlib.sha256(source.encode()).hexdigest(),
    }
    result = (HERE / "template.html").read_text()
    for name, value in replacements.items():
        result = result.replace("{{" + name + "}}", value)
    if re.search(r"\{\{[A-Z_]+\}\}", result):
        raise ValueError("Onbekende placeholder in het HTML-template.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated HTML is stale; do not write")
    args = parser.parse_args()
    try:
        result = render(SOURCE.read_text())
        if args.check:
            if not OUTPUT.exists() or OUTPUT.read_text() != result:
                print("Evalviewer is verouderd. Voer python3 docs/evals/build.py uit.", file=sys.stderr)
                return 1
            print("Evalviewer komt overeen met de canonieke bron en presentatiefiles.")
        else:
            OUTPUT.write_text(result)
            print("Gegenereerd: docs/evals/index.html (documentatie; geen evaluaties uitgevoerd).")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Documentatiegeneratie mislukt: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
