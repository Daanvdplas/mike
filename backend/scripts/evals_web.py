#!/usr/bin/env python3
"""Local page for the explicit E06 run; model credentials stay here."""
import argparse
import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid

import retrieval_relevance as relevance

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "openai/gpt-4.1-mini-2025-04-14"


class RunError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def e06_record(repo):
    raw = (repo / "docs/evals/scenarios.json").read_bytes()
    catalog = json.loads(raw)
    records = [row for row in catalog["scenarios"] if row["id"] == "E06"]
    if len(records) != 1:
        raise RunError("E06 ontbreekt of staat dubbel in de catalogus.")
    row = records[0]
    if (catalog["schema_version"] != 1 or row["input_mode"] != "query"
            or row["document"] is not None or row["query_case_id"] != "156133"
            or row["source_case"]["id"] != "156133"):
        raise RunError("E06 heeft niet meer de afgesproken query-only bronbinding.")
    return row, sha256(raw)


def catalog(config):
    row, _ = e06_record(config["repo"])
    return {"evals": [
        {"id": "E06", "title": row["title"], "input_mode": "query",
         "query": row["query"]["en"], "query_nl": row["query"]["nl"],
         "document_label": None, "source_case": row["source_case"],
         "expected_behavior": row["expected_behavior"], "why": row["why"], "runnable": True},
    ]}


def indexed_source(config, row):
    source_file = config["corpus"] / row["source_case"]["file"]
    raw = source_file.read_bytes()
    source = json.loads(raw)
    if str(source["id"]) != row["query_case_id"] or source["decision_date"] != row["source_case"]["decision_date"]:
        raise RunError("De E06-bronidentiteit of uitspraakdatum wijkt af.")
    majority = [opinion["text"] for opinion in source["casebody"]["opinions"] if opinion["type"] == "majority"]
    if len(majority) != 1:
        raise RunError("E06 moet precies één majority opinion hebben.")
    text = majority[0].replace("\r\n", "\n").replace("\r", "\n").strip()
    with sqlite3.connect(f"{config['database'].as_uri()}?mode=ro", uri=True) as database:
        manifest = json.loads(database.execute("SELECT manifest FROM metadata WHERE id=1").fetchone()[0])
        record = json.loads(database.execute("SELECT record FROM cases WHERE case_id=?", (row["query_case_id"],)).fetchone()[0])
    text_version = "sha256:" + sha256(text.encode())
    if (record["text"] != text or record["metadata"]["text_version"] != text_version
            or json.loads(record["source_json"]) != source):
        raise RunError("De E06-bron komt niet overeen met de geïndexeerde corpusversie.")
    return manifest, {"case_id": row["query_case_id"], "file": row["source_case"]["file"],
                      "raw_sha256": sha256(raw), "text_version": text_version}


def excluded_search(config, row, run_dir):
    manifest, source = indexed_source(config, row)
    if not config["binary"].is_file():
        raise RunError("De Rustbinary voor bronuitsluiting is niet beschikbaar.")
    command = [sys.executable, str(config["repo"] / "backend/scripts/resource_guard.py"),
               "--label", "web-e06", "--timeout-seconds", "600",
               "--report", str(run_dir / "guard.json"), "--log", str(run_dir / "search.log"),
               "--", str(config["binary"]), "search", "--exclude-case-id", row["query_case_id"], row["query"]["en"]]
    env = os.environ.copy()
    env.pop("ORQ_API_KEY", None)
    env["ADAMI_DB_PATH"] = str(config["database"])
    env["ADAMI_CACHE_DIR"] = str(config["model_cache"])
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        child.communicate(timeout=620)
    except subprocess.TimeoutExpired:
        child.terminate()
        child.communicate(timeout=15)
        raise RunError("De E06-zoekactie is gestopt wegens de tijdslimiet.") from None
    report_path = run_dir / "guard.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    if child.returncode != 0 or report.get("status") != "passed":
        raise RunError("De E06-zoekactie is gestopt of mislukt onder de resourcebewaking. Bekijk het lokale guardverslag.")
    for line in reversed((run_dir / "search.log").read_text().splitlines()):
        if line.startswith('{'):
            value = json.loads(line)
            if isinstance(value, dict) and "response" in value:
                if value.get("excluded_case_ids") != [row["query_case_id"]] or value.get("eligible_case_count") != 134:
                    raise RunError("De Rustzoekactie bevestigt de bronuitsluiting niet.")
                response = value["response"]
                break
    else:
        raise RunError("De Rustzoekactie leverde geen geldige zoekresponse.")
    if response["corpus_version"] != manifest["corpus_version"]:
        raise RunError("De corpusversie veranderde tijdens de E06-run.")
    return response, manifest, source


def run_eval(config, eval_id):
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    run_dir = config["outputs"] / run_id
    run_dir.mkdir(parents=True)
    started = time.monotonic()
    rubric = None
    source = None
    manifest = None
    scenario_hash = None
    if eval_id == "E06":
        row, scenario_hash = e06_record(config["repo"])
        query, document, mode = row["query"]["en"], None, "query"
        response, manifest, source = excluded_search(config, row, run_dir)
        rubric = {"expected_behavior": row["expected_behavior"], "why": row["why"]}
    else:
        raise RunError("Alleen E06 kan worden uitgevoerd.")
    passages = relevance.passages_from_response(response, mode)
    if eval_id == "E06" and source["case_id"] in passages:
        raise RunError("De bronzaak is niet uitgesloten; deze run is ongeldig.")
    (run_dir / "search.json").write_text(json.dumps(response, ensure_ascii=False, indent=2))
    try:
        judgments, model, usage = relevance.judge(query, document, passages, config["model"], config["key"], config["orq_base"], rubric=rubric)
    except relevance.EvaluationError as failure:
        if failure.diagnostic is not None:
            (run_dir / "judge.failed.json").write_text(json.dumps(failure.diagnostic, ensure_ascii=False, indent=2))
        raise
    by_id = {hit["case_id"]: hit for hit in response["results"]}
    for judgment in judgments:
        hit = by_id[judgment["case_id"]]
        judgment.update(title=hit["title"], score=hit["score"],
                        case_url=config["backend"] + hit["case_url"])
    result = {
        "run_id": run_id, "eval_id": eval_id, "status": "completed",
        "input": {"mode": mode, "query": query,
                  "document_label": None,
                  "document_sha256": sha256(document.encode()) if document else None},
        "structural_checks": {"three_unique_results": True,
                              "source_excluded": True if eval_id == "E06" else None},
        "model": model, "requested_model": config["model"], "usage": usage,
        "corpus_version": response["corpus_version"], "ranking_version": response["ranking_version"],
        "retrieval_manifest": manifest, "source": source, "scenarios_sha256": scenario_hash,
        "excluded_case_ids": [source["case_id"]] if source else [],
        "eligible_case_count": 134 if source else None,
        "judgments": judgments, "search_response": response,
        "duration_seconds": round(time.monotonic() - started, 3),
        "limitations": ["AI-beoordeling, geen menselijke juridische referentie of Recall/nDCG-meting.",
                        "Uitgevoerd betekent dat de run technisch is voltooid; grades kunnen zwakke relevantie aangeven.",
                        "Bronfragmenten zijn letterlijk gecontroleerd; dat bewijst niet dat de AI-score juist is."],
        "artifact_name": run_id + "/result.json",
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def handler_class(config, runner=run_eval):
    lock = threading.Lock()
    static = config["repo"] / "docs/evals"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_json(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/evals":
                try:
                    self.send_json(200, catalog(config))
                except (OSError, ValueError, KeyError, RunError):
                    self.send_json(503, {"error": {"code": "catalog_unavailable", "message": "De evalcatalogus kon niet worden geladen."}})
                return
            name = "index.html" if path == "/" else path.lstrip('/')
            if name not in {"index.html", "viewer.js", "viewer.css", "scenarios.json"}:
                self.send_error(404)
                return
            try:
                data = (static / name).read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            expected_origin = f"http://{self.headers.get('Host', '')}"
            allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in allowed_hosts or self.headers.get("Origin") != expected_origin:
                self.send_json(403, {"error": {"code": "origin_rejected", "message": "Start de eval vanaf deze lokale pagina."}})
                return
            path = urlsplit(self.path).path
            ids = {"/api/evals/E06/run": "E06"}
            if path not in ids:
                self.send_json(404, {"error": {"code": "unknown_eval", "message": "Deze eval is niet uitvoerbaar."}})
                return
            if self.headers.get("Content-Type", "").split(';')[0] != "application/json" or self.headers.get("Content-Length") != "2" or self.rfile.read(2) != b"{}":
                self.send_json(400, {"error": {"code": "invalid_input", "message": "Deze knop voert alleen de vastgelegde eval-invoer uit."}})
                return
            if not lock.acquire(blocking=False):
                self.send_json(409, {"error": {"code": "busy", "message": "Er loopt al een eval. Wacht tot die klaar is."}})
                return
            try:
                if not config.get("key"):
                    self.send_json(503, {"error": {"code": "model_unavailable", "message": "De evalserver heeft geen modelcredential."}})
                    return
                self.send_json(200, runner(config, ids[path]))
            except (RunError, relevance.EvaluationError) as failure:
                self.send_json(502, {"error": {"code": "run_failed", "message": str(failure)}})
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError):
                self.send_json(503, {"error": {"code": "run_unavailable", "message": "De run is niet voltooid. Controleer de lokale bron, Rustbinary en indexconfiguratie."}})
            finally:
                lock.release()

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=os.environ.get("ORQ_MODEL", DEFAULT_MODEL))
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("ADAMI_DB_PATH", "data/cases.sqlite3")))
    parser.add_argument("--model-cache", type=Path, default=Path(os.environ.get("ADAMI_CACHE_DIR", ".fastembed_cache")))
    parser.add_argument("--corpus", type=Path, default=Path.home() / "Downloads/texas-criminal-reports")
    parser.add_argument("--outputs", type=Path, default=Path.home() / "Library/Caches/adami-case/web-evals")
    args = parser.parse_args()
    key = os.environ.get("ORQ_API_KEY") or getpass.getpass("Orq API key (not echoed): ")
    if not key.strip():
        raise SystemExit("Missing Orq API key.")
    config = {"repo": REPO, "backend": args.backend.rstrip('/'), "model": args.model, "key": key,
              "orq_base": os.environ.get("ORQ_BASE_URL", relevance.ORQ_BASE_URL),
              "binary": args.binary.resolve(), "database": args.database.resolve(),
              "model_cache": args.model_cache.resolve(), "corpus": args.corpus.resolve(),
              "outputs": args.outputs.resolve()}
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_class(config))
    print(f"Eval page: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
