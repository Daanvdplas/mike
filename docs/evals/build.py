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
    for required in ["Status en leeswijzer", "Doel en afbakening", "Scenarioselectie en relevantie", "Diagnostiek voor moeilijke gevallen"]:
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

    mode_controls = []
    panels = []
    for i, (label, mode_code, offered, expectation) in enumerate(modes):
        mode = mode_code.strip("`")
        if mode not in {"document", "query", "combined"}:
            raise ValueError("Onbekende invoermodus in de bron.")
        checked = " checked" if i == 2 else ""
        mode_controls.append(f'<label><input type="radio" name="input-mode" value="{mode}"{checked}><span>{inline(label)}</span></label>')
        document = '<dt>Document</dt><dd>Nog te kiezen<br><small>Volledige majority opinion</small></dd>' if mode != "query" else '<dt>Document</dt><dd>Wordt niet meegestuurd</dd>'
        query = '<dt>Juridische vraag</dt><dd>Nog op te stellen<br><small>Concrete Engelse zoekvraag</small></dd>' if mode != "document" else '<dt>Juridische vraag</dt><dd>Wordt niet meegestuurd</dd>'
        panels.append(f'''<section class="mode-panel" data-mode="{mode}" aria-label="{html.escape(label)}">
          <h3 class="mode-heading">{inline(label)}</h3>
          <div class="anatomy">
            <article><span class="step">01 · Invoer</span><h4>Wat geef je mee?</h4><p>{inline(offered)}</p><dl>{document}{query}</dl></article>
            <article><span class="step">02 · Verwachting</span><h4>Wat zou relevant zijn?</h4><p>{inline(expectation)}</p><p class="empty-label">Nog niet beoordeeld</p><p class="small">Hier komen de kandidaatmatches, hun label van 0–3 en exacte bronpassages. Dit is geen vaste lijst van drie zaken.</p></article>
            <article><span class="step">03 · Werkelijk resultaat</span><h4>Wat vindt de zoekfunctie?</h4><p class="empty-label">Nog niet uitgevoerd</p><p class="small">Na een run komen hier de drie gevonden zaken en hun passages, vergeleken met de beoordeelde verwachtingen.</p><button type="button" class="button unavailable" aria-disabled="true" aria-describedby="run-unavailable">Run test <span aria-hidden="true">↗</span></button><p class="button-help"><a href="#run-unavailable">Waarom nog niet?</a></p></article>
          </div>
        </section>''')

    challenge_html = []
    for title, question, expected, minimum in challenges:
        challenge_html.append(f'''<details class="challenge"><summary><span>{inline(title)}</span><span class="minimum">{inline(minimum)}</span></summary><div class="detail-body"><h4>Wat wordt er moeilijk gemaakt?</h4><p>{inline(question)}</p><h4>Verwachte beoordeling</h4><p>{inline(expected)}</p><p class="small">Een testgeval en bijbehorende passages zijn nog niet samengesteld. De relevantielabels liggen nog niet vast.</p><a class="text-link" href="#testopbouw">Bekijk de opbouw van een test <span aria-hidden="true">↑</span></a></div></details>''')
    source_navigation = "".join(f'<li><a href="#bron-{slug(title)}">{html.escape(title)}</a></li>' for title in content)
    status_intro = status.split("\n\n")[0]
    replacements = {
        "STYLE": (HERE / "viewer.css").read_text(),
        "SCRIPT": (HERE / "viewer.js").read_text(),
        "TARGET": target,
        "STATUS": inline(status_intro),
        "MODE_CONTROLS": "\n".join(mode_controls),
        "MODE_PANELS": "\n".join(panels),
        "CHALLENGES": "\n".join(challenge_html),
        "VARIANTS": inline(variants),
        "MASKING": inline(masking),
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
