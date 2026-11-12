#!/usr/bin/env python3
"""Build the offline documentation view. This does not build or run evaluations."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import unicodedata


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "README.md"
WEB = HERE / "web"
DATA = HERE / "data"
OUTPUT = WEB / "index.html"


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


def scenario_catalog():
    catalog = json.loads((DATA / "scenarios.json").read_text())
    if catalog.get("schema_version") != 1 or catalog.get("status") != "ontwerp":
        raise ValueError("De scenariocatalogus moet schema 1 en status ontwerp gebruiken.")
    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("De scenariocatalogus bevat geen ontwerpbeschrijvingen.")
    ids = set()
    for position, scenario in enumerate(scenarios, 1):
        if scenario.get("id") != f"E{position:02d}" or scenario["id"] in ids:
            raise ValueError("Scenario’s moeten unieke, opeenvolgende E01-identificaties hebben.")
        ids.add(scenario["id"])
        for field in ("title", "expected_behavior", "why"):
            if not isinstance(scenario.get(field), str) or not scenario[field].strip():
                raise ValueError(f"Ontbrekende scenario-inhoud: {field}")
        mode = scenario.get("input_mode")
        document, query = scenario.get("document"), scenario.get("query")
        if mode not in {"document", "query", "combined"}:
            raise ValueError("Onbekende scenario-invoermodus.")
        if (document is not None) != (mode in {"document", "combined"}) or (query is not None) != (mode in {"query", "combined"}):
            raise ValueError("Scenario-invoer komt niet overeen met de invoermodus.")
        if scenario.get("status") != "ontwerp" or scenario.get("judgment_status") != "nog niet beoordeeld":
            raise ValueError("Deze viewer toont ontwerpen, geen beoordeelde benchmarklabels.")
        source = scenario.get("source_case", {})
        for field in ("id", "name", "file", "decision_date"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                raise ValueError(f"Ontbrekende bronmetadata: {field}")
        if document is not None and any(not isinstance(document.get(field), str) or not document[field].strip() for field in ("excerpt", "field", "sha256")):
            raise ValueError("Documentinvoer mist exact fragment of herkomst.")
        if query is not None and any(not isinstance(query.get(language), str) or not query[language].strip() for language in ("nl", "en")):
            raise ValueError("Vraaginvoer mist Nederlandse uitleg of Engelse uitvoervraag.")
        evidence = scenario.get("source_evidence")
        if not isinstance(evidence, list) or not evidence or any(not entry.get("text") for entry in evidence):
            raise ValueError("Een scenario mist bronbewijs.")
    return catalog


def render_scenario(scenario):
    escape = html.escape
    source = scenario["source_case"]
    mode = scenario["input_mode"]
    mode_label = {"document": "Document", "query": "Vraag", "combined": "Document + vraag"}[mode]
    identity = f'{escape(source["name"])} <span>· {escape(source["decision_date"])}</span>'
    inputs = []
    if scenario["document"] is not None:
        document = scenario["document"]
        inputs.append(f'''<div class="input-document"><h4>Document</h4><p class="case-name">{identity}</p><blockquote>{escape(document["excerpt"])}</blockquote><p class="input-note">De invoer is de volledige majority opinion. Hier staat een kort leesfragment.</p></div>''')
    if scenario["query"] is not None:
        query = scenario["query"]
        inputs.append(f'''<div class="input-query"><h4>Exacte zoekvraag · Engels</h4><p class="question-text" lang="en">{escape(query["en"])}</p><details class="english-query"><summary>Nederlandse leesvertaling</summary><p lang="nl">{escape(query["nl"])}</p></details></div>''')
    provenance_label = "Bron en tekstverwijzing" if scenario["document"] is not None else "Herkomst van de vraag · niet meegestuurd als document"
    quotes = "".join(f'<blockquote>{escape(entry["text"])}</blockquote>' for entry in scenario["source_evidence"])
    provenance = f'<p class="case-name">{identity}</p><p class="source-path"><code>{escape(source["file"])}</code> · zaak-ID <code>{escape(source["id"])}</code></p>{quotes}'
    if scenario["document"] is not None:
        provenance += f'<p class="source-path">Volledige invoertekst: <code>{escape(scenario["document"]["field"])}</code><br>SHA-256: <code>{escape(scenario["document"]["sha256"])}</code></p>'
    run_link = f'<p><a href="#run-{escape(scenario["id"])}" data-run-eval="{escape(scenario["id"])}">{escape(scenario["id"])} uitvoeren ↑</a></p>'
    return f'''<details class="eval-item" id="{escape(scenario["id"])}"><summary><span class="eval-id">{escape(scenario["id"])}</span><span class="eval-title">{escape(scenario["title"])}</span><span class="eval-mode">{mode_label}</span><span class="chevron" aria-hidden="true"></span></summary><div class="eval-detail">{run_link}<section class="scenario-input"><h3>Input</h3>{"".join(inputs)}</section><section class="scenario-expectation"><h3>Verwacht gedrag</h3><p>{escape(scenario["expected_behavior"])}</p></section><section class="scenario-purpose"><h3>Waarom deze test?</h3><p>{escape(scenario["why"])}</p></section><details class="provenance"><summary>{provenance_label}</summary>{provenance}</details><p class="scenario-status">Ontwerpbeschrijving · kandidaatmatches en relevantielabels nog niet beoordeeld.</p></div></details>'''


def render(source):
    content = sections(source)
    status = content["Status en leeswijzer"]
    if "**Status: technische uitvoering beschikbaar; juridische benchmark nog ontwerp.**" not in status:
        raise ValueError("De viewer combineert technische runs met ontwerpscenario’s; pas bronstatus en presentatie bewust samen aan.")
    modes = table_rows(status)[1:]
    if len(modes) != 3 or any(len(row) != 4 for row in modes):
        raise ValueError("De bron moet drie invoervormen met vier kolommen bevatten.")
    goal_match = re.search(r"\*\*(\d+) basisscenario", content["Doel en afbakening"])
    if not goal_match:
        raise ValueError("Het streefgetal voor basisscenario’s ontbreekt in de bron.")
    catalog = scenario_catalog()
    scenarios = catalog["scenarios"]
    count_match = re.search(r"\*\*(\d+) concrete ontwerpscenario", status)
    if count_match and len(scenarios) != int(count_match.group(1)):
        raise ValueError("Het scenarioaantal wijkt af van de canonieke statusbeschrijving.")
    source_navigation = "".join(f'<li><a href="#bron-{slug(title)}">{html.escape(title)}</a></li>' for title in content)
    replacements = {
        "STYLE": (WEB / "viewer.css").read_text(),
        "SCRIPT": (WEB / "viewer.js").read_text(),
        "SCENARIO_COUNT": str(len(scenarios)),
        "SCENARIO_ITEMS": "\n".join(render_scenario(scenario) for scenario in scenarios),
        "SOURCE_NAVIGATION": source_navigation,
        "SPECIFICATION": markdown(source),
        "HASH": hashlib.sha256(source.encode()).hexdigest(),
        "CATALOG_HASH": hashlib.sha256((DATA / "scenarios.json").read_bytes()).hexdigest(),
    }
    result = (WEB / "template.html").read_text()
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
                print("Evalviewer is verouderd. Voer python3 -m evals.build uit.", file=sys.stderr)
                return 1
            print("Evalviewer komt overeen met de canonieke bron en presentatiefiles.")
        else:
            OUTPUT.write_text(result)
            print("Gegenereerd: evals/web/index.html (documentatie; geen evaluaties uitgevoerd).")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Documentatiegeneratie mislukt: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
