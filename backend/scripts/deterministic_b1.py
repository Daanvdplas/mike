"""Fixed two-target check for the preregistered appeal-bond query; no AI judge."""
import hashlib
import json
import math
import sqlite3


def load_fixture(repo):
    raw = (repo / "docs/evals/deterministic_b1.json").read_bytes()
    fixture = json.loads(raw)
    ids = [row["case_id"] for row in fixture["expected_cases"]]
    if (fixture["schema_version"] != 1 or fixture["id"] != "B1"
            or fixture["input_mode"] != "query" or fixture["document"] is not None
            or fixture["excluded_case_ids"] != [] or len(ids) != 2 or len(set(ids)) != 2):
        raise ValueError("De vaste B1-fixture is ongeldig.")
    return fixture, hashlib.sha256(raw).hexdigest()


def verified_index(fixture, database_path, corpus):
    with sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True) as database:
        manifest = json.loads(database.execute("SELECT manifest FROM metadata WHERE id=1").fetchone()[0])
        cases = {case_id: json.loads(record) for case_id, record in database.execute("SELECT case_id, record FROM cases")}
    if manifest["corpus_version"] != fixture["context"]["corpus_version"] or len(cases) != 135:
        raise ValueError("De index wijkt af van de vooraf vastgelegde corpusversie.")
    for expected in fixture["expected_cases"]:
        raw = (corpus / expected["source_file"]).read_bytes()
        source = json.loads(raw)
        case = cases[expected["case_id"]]
        proof = expected["evidence"]
        units = case["text"].encode("utf-16-le")
        quote = units[proof["start_utf16"] * 2:proof["end_utf16"] * 2].decode("utf-16-le")
        if (hashlib.sha256(raw).hexdigest() != expected["raw_sha256"]
                or str(source["id"]) != expected["case_id"]
                or source["decision_date"] != expected["decision_date"]
                or json.loads(case["source_json"]) != source
                or case["metadata"]["text_version"] != expected["text_version"]
                or quote != proof["quote"]):
            raise ValueError("Vooraf vastgelegde referentiebron of bewijs wijkt af.")
    return manifest, cases


def score(fixture, response, cases):
    if (response.get("mode") != "query"
            or response.get("corpus_version") != fixture["context"]["corpus_version"]
            or response.get("ranking_version") != fixture["context"]["ranking_version"]):
        raise ValueError("De zoekresponse heeft een andere modus, corpus- of rankingversie.")
    rows = response.get("results")
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError("De zoekresponse moet precies drie geldige unieke zaken bevatten.")
    found = {}
    results = []
    expected_ids = {row["case_id"] for row in fixture["expected_cases"]}
    for rank, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError("De zoekresponse bevat een ongeldig resultaat.")
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or case_id not in cases or case_id in found:
            raise ValueError("De zoekresponse bevat een onbekende of dubbele zaak-ID.")
        metadata = cases[case_id]["metadata"]
        value = row.get("score")
        if (type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1
                or any(row.get(field) != metadata[field] for field in ("case_id", "title", "text_version"))):
            raise ValueError("De zoekresponse bevat ongeldige scores of bronmetadata.")
        found[case_id] = rank
        results.append({"case_id": case_id, "title": row["title"], "score": value,
                        "rank": rank, "assessment": "expected" if case_id in expected_ids else "unjudged"})
    expectations = [{"case_id": row["case_id"], "title": row["title"],
                     "found": row["case_id"] in found, "rank": found.get(row["case_id"])}
                    for row in fixture["expected_cases"]]
    hit_count = sum(row["found"] for row in expectations)
    return {"hit_count": hit_count, "expected_count": 2, "passed": hit_count == 2,
            "expectations": expectations, "results": results}
