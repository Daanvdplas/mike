#!/usr/bin/env python3
"""Local A/B retrieval runs for the canonical development scenarios."""
import argparse
from contextlib import closing
import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import threading
import tempfile
import time
from urllib.parse import urlsplit
import uuid

from . import retrieval_relevance as relevance
from . import deterministic_b1 as b1
from backend.scripts.orq_models import ModelCatalog, UnsupportedModel
from backend.scripts.orq_credentials import load_api_key

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "openai/gpt-4.1-mini-2025-04-14"


class RunError(Exception):
    def __init__(self, message, code="run_failed", retryable=True):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def private_json(path, value):
    """Publish a complete provider response atomically, mode0600, without overwriting."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n"); output.flush(); os.fsync(output.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def scenario_catalog(repo):
    raw = (repo / "evals/data/scenarios.json").read_bytes()
    value = json.loads(raw)
    rows = value.get("scenarios")
    if value.get("schema_version") != 1 or value.get("status") != "ontwerp" or not isinstance(rows, list) or not rows:
        raise RunError("De ontwerpcatalogus heeft geen geldig schema of scenario’s.")
    seen = set()
    for row in rows:
        mode, query, document = row["input_mode"], row["query"], row["document"]
        if (not isinstance(row["id"], str) or not row["id"] or row["id"] in seen
                or mode not in {"query", "document", "combined"}
                or (document is not None) != (mode in {"document", "combined"})
                or (query is not None) != (mode in {"query", "combined"})
                or (query is not None and (not isinstance(query.get("en"), str) or not query["en"].strip()))
                or row["query_case_id"] != row["source_case"]["id"]):
            raise RunError("Scenario-ID, invoermodus of bronbinding is ongeldig.")
        if document is not None and (document["field"] != "casebody.opinions[0].text" or document["opinion_type"] != "majority"):
            raise RunError("Scenario-documentinvoer moet de vastgelegde majority opinion zijn.")
        seen.add(row["id"])
    return rows, sha256(raw)


def catalog(config):
    rows, _ = scenario_catalog(config["repo"])
    fixture, _ = b1.load_fixture(config["repo"])
    records = [{"id": row["id"], "title": row["title"], "input_mode": row["input_mode"],
                "query": row["query"]["en"] if row["query"] else None,
                "query_nl": row["query"].get("nl") if row["query"] else None,
                "document_label": "Volledige meerderheidstekst" if row["document"] else None,
                "source_case": row["source_case"], "source_excluded": True,
                "expected_behavior": row["expected_behavior"], "why": row["why"], "runnable": True} for row in rows]
    fixed = [{"id": "B1", "title": fixture["title"], "input_mode": "query", "query": fixture["query"],
              "document_label": None, "expected_cases": [{"case_id": item["case_id"], "title": item["title"]} for item in fixture["expected_cases"]],
              "fixture_version": fixture["fixture_version"], "runnable": True},
             next(row for row in records if row["id"] == "E06")]
    return {"retrieval_methods": ["opinion_chunks", "head_matter"], "judge_available": bool(config.get("key")), "evals": fixed, "diagnostic_evals": records}


def indexed_source(config, row):
    relative = Path(row["source_case"]["file"])
    if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
        raise RunError("Een scenariobron moet binnen het afgesproken corpus staan.")
    source_file = config["corpus"] / relative
    raw = source_file.read_bytes()
    source = json.loads(raw)
    if str(source["id"]) != row["query_case_id"] or source["decision_date"] != row["source_case"]["decision_date"]:
        raise RunError("De bronidentiteit of uitspraakdatum wijkt af.")
    opinions = source["casebody"]["opinions"]
    majority = [opinion["text"] for opinion in opinions if opinion["type"] == "majority"]
    if len(majority) != 1:
        raise RunError("Een scenariobron moet precies één majority opinion hebben.")
    text = majority[0].replace("\r\n", "\n").replace("\r", "\n").strip()
    canonical_hash = sha256(text.encode())
    if row["document"] is not None and (row["document"]["sha256"] != canonical_hash
            or opinions[0]["type"] != "majority" or opinions[0]["text"] != text):
        raise RunError("De documenthash of het vastgelegde majority-veld wijkt af.")
    with closing(sqlite3.connect(f"{config['database'].as_uri()}?mode=ro", uri=True)) as database:
        manifest = json.loads(database.execute("SELECT manifest FROM metadata WHERE id=1").fetchone()[0])
        stored = database.execute("SELECT record FROM cases WHERE case_id=?", (row["query_case_id"],)).fetchone()
    if stored is None:
        raise RunError("De scenariobron ontbreekt in de zoekindex.")
    record = json.loads(stored[0])
    text_version = "sha256:" + canonical_hash
    if (record["text"] != text or record["metadata"]["text_version"] != text_version
            or record["source_json"] != raw.decode("utf-8")):
        raise RunError("De scenariobron komt niet overeen met de geïndexeerde corpusversie.")
    return manifest, {"case_id": row["query_case_id"], "file": row["source_case"]["file"],
                      "raw_sha256": sha256(raw), "canonical_sha256": canonical_hash, "text_version": text_version}, text


def local_search(config, query, document, mode, method, excluded_case_ids):
    envelope = relevance.search(config["backend"], query, document, method, excluded_case_ids)
    response = envelope.get("response", {})
    manifest = envelope.get("index_manifest")
    if (response.get("retrieval_method") != method
            or envelope.get("excluded_case_ids") != excluded_case_ids
            or envelope.get("eligible_case_count") != 135 - len(excluded_case_ids)
            or not isinstance(manifest, dict)
            or response.get("corpus_version") != manifest.get("corpus_version")):
        raise RunError("De zoekmethode, indexversie of bronuitsluiting is niet bevestigd; de run is ongeldig.")
    passages = relevance.passages_from_response(response, mode)
    section = "head_matter" if method == "head_matter" else "majority"
    if any(hit["passage"].get("source_section", "majority") != section for hit in response["results"]):
        raise RunError("De gevonden passages horen niet bij de gekozen zoekmethode.")
    if any(case_id in passages for case_id in excluded_case_ids):
        raise RunError("De bronzaak is niet uitgesloten; deze run is ongeldig.")
    return response, manifest, passages


def run_b1(config, run_id, run_dir, started):
    if config.get("judge_enabled"):
        raise RunError("B1 gebruikt geen AI-beoordelaar.", retryable=False)
    fixture, fixture_hash = b1.load_fixture(config["repo"])
    try:
        manifest, cases = b1.verified_index(fixture, config["database"], config["corpus"])
    except b1.IndexContextError as failure:
        raise RunError(str(failure), "index_context_mismatch", False) from None
    inputs = {"mode": "query", "query": fixture["query"], "document_label": None, "document_sha256": None}
    input_hash = sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode())
    provenance = {"fixture_version": fixture["fixture_version"], "fixture_sha256": fixture_hash,
                  "reference_status": fixture["reference_status"], "evaluation_kind": "migrated_target_check",
                  "index_snapshot": fixture["context"]["snapshot"],
                  "index_manifest_sha256": b1.digest(b1.canonical(manifest)),
                  "index_pipeline_sha256": sha256(manifest["pipeline"].encode())}
    runs = []
    for method in config.get("retrieval_methods", ["opinion_chunks"]):
        method_started = time.monotonic()
        response, returned_manifest, _ = local_search(config, fixture["query"], None, "query", method, [])
        if returned_manifest != manifest:
            raise RunError("De zoekengine gebruikt een andere index dan de B1-v2-snapshot.", "index_context_mismatch", False)
        try:
            scored = b1.score(fixture, response, cases, method)
        except ValueError as failure:
            raise RunError(str(failure), "invalid_search_result", False) from None
        (run_dir / f"search-{method}.json").write_text(json.dumps(response, ensure_ascii=False, indent=2))
        runs.append({"run_id": f"{run_id}-{method}", "eval_id": "B1", "status": "completed", **provenance, **scored,
                     "retrieval_method": method, "input": inputs, "input_sha256": input_hash,
                     "corpus_version": response["corpus_version"], "ranking_version": response["ranking_version"],
                     "retrieval_manifest": manifest, "search_response": response, "excluded_case_ids": [], "eligible_case_count": len(cases),
                     "structural_checks": {"three_unique_results": True, "valid_corpus_ids": True, "source_excluded": False},
                     "judge_status": "not_requested", "judgments": [], "model": None, "requested_model": None,
                     "duration_seconds": round(time.monotonic() - method_started, 3), "artifact_name": f"{run_id}/result.json",
                     "limitations": ["Twee overgenomen, agentvoorgestelde referentiezaken; geen menselijke juridische goldset.",
                                     "De nieuwe indexbinding is geen nieuwe preregistratie. Andere matches blijven onbeoordeeld.",
                                     "0–2 telt verwachte zaken; de cosinusscore is geen juridische kwaliteitsscore."]})
    shared = sorted(set.intersection(*(set(row["case_id"] for row in run["search_response"]["results"]) for run in runs)))
    result = {"run_id": run_id, "eval_id": "B1", "status": "completed", **provenance, "input": inputs, "input_sha256": input_hash,
              "runs": runs, "comparison": {"shared_case_ids": shared, "overlap_count": len(shared)} if len(runs) > 1 else None,
              "duration_seconds": round(time.monotonic() - started, 3), "artifact_name": f"{run_id}/result.json"}
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result



def run_eval(config, eval_id):
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    run_dir = config["outputs"] / run_id
    run_dir.mkdir(parents=True)
    started = time.monotonic()
    if eval_id == "B1":
        return run_b1(config, run_id, run_dir, started)
    methods = config.get("retrieval_methods", ["opinion_chunks"])
    judge_enabled = config.get("judge_enabled", False)
    rubric = source = source_manifest = scenario_hash = None
    rows, scenario_hash = scenario_catalog(config["repo"])
    row = next((item for item in rows if item["id"] == eval_id), None)
    if row is None:
        raise RunError("Dit scenario staat niet in de canonieke catalogus.")
    source_manifest, source, source_text = indexed_source(config, row)
    mode = row["input_mode"]
    query = row["query"]["en"] if row["query"] else None
    document = source_text if row["document"] else None
    rubric = {"expected_behavior": row["expected_behavior"], "why": row["why"]}
    if judge_enabled and not config.get("key"):
        raise RunError("AI-beoordeling is niet beschikbaar zonder modelcredential.")
    inputs = {"mode": mode, "query": query,
              "document_label": source["file"] if document else None,
              "document_sha256": sha256(document.encode()) if document else None}
    input_hash = sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode())
    excluded = [source["case_id"]] if source else []
    runs = []
    for method in methods:
        method_started = time.monotonic()
        response, manifest, passages = local_search(config, query, document, mode, method, excluded)
        if source_manifest is not None and source_manifest != manifest:
            raise RunError("De bronindex wijkt af van de zoekindex; de run is ongeldig.")
        if runs and (response["corpus_version"] != runs[0]["corpus_version"]
                     or response["ranking_version"] != runs[0]["ranking_version"]
                     or manifest != runs[0]["retrieval_manifest"]):
            raise RunError("De index, het model of de ranking veranderde tussen methodes; vergelijking gestopt.")
        (run_dir / f"search-{method}.json").write_text(json.dumps(response, ensure_ascii=False, indent=2))
        judgments, returned_model, usage = [], None, None
        judge_response_artifact = judge_response_sha256 = None
        if judge_enabled:
            try:
                judgments, returned_model, usage = relevance.judge(
                    query, document, passages, config["model"], config["key"], config["orq_base"], rubric=rubric,
                    source_sections={hit["case_id"]: hit["passage"].get("source_section", "majority") for hit in response["results"]},
                    response_sink=lambda provider_response: private_json(run_dir / f"judge-response-{method}.json", provider_response))
                judge_response_artifact = f"{run_id}/judge-response-{method}.json"
                judge_response_sha256 = sha256((run_dir / f"judge-response-{method}.json").read_bytes())
            except relevance.EvaluationError as failure:
                if failure.diagnostic is not None:
                    (run_dir / f"judge-failed-{method}.json").write_text(json.dumps(failure.diagnostic, ensure_ascii=False, indent=2))
                raise
        limitations = ["De zoekscore meet tekstovereenkomst, geen juridische relevantie.",
                      "Gelijke invoer en index maken methodes vergelijkbaar; overlap is geen kwaliteitsmeting."]
        if judge_enabled:
            limitations.append("AI-beoordeling, geen menselijke juridische referentie of Recall/nDCG-meting.")
        runs.append({"run_id": f"{run_id}-{method}", "eval_id": eval_id, "status": "completed",
                     "retrieval_method": method, "input": inputs, "input_sha256": input_hash,
                     "structural_checks": {"three_unique_results": True, "source_excluded": bool(source)},
                     "judge_status": "completed" if judge_enabled else "not_requested",
                     "model": returned_model, "requested_model": config["model"] if judge_enabled else None,
                     "usage": usage, "judgments": judgments,
                     "judge_response_artifact": judge_response_artifact, "judge_response_sha256": judge_response_sha256,
                     "corpus_version": response["corpus_version"], "ranking_version": response["ranking_version"],
                     "retrieval_manifest": manifest, "source": source, "scenarios_sha256": scenario_hash,
                     "excluded_case_ids": excluded, "eligible_case_count": 135 - len(excluded),
                     "search_response": response, "duration_seconds": round(time.monotonic() - method_started, 3),
                     "limitations": limitations, "artifact_name": f"{run_id}/result.json"})
    shared = sorted(set.intersection(*(set(hit["case_id"] for hit in run["search_response"]["results"]) for run in runs)))
    result = {"run_id": run_id, "eval_id": eval_id, "status": "completed",
              "execution_status": "completed", "input": inputs,
              "input_sha256": input_hash, "runs": runs,
              "comparison": {"shared_case_ids": shared, "overlap_count": len(shared)} if len(runs) > 1 else None,
              "duration_seconds": round(time.monotonic() - started, 3), "artifact_name": f"{run_id}/result.json"}
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def handler_class(config, runner=run_eval):
    models = config.get("models") or ModelCatalog(config.get("model", DEFAULT_MODEL))
    lock = threading.Lock()
    static = config["repo"] / "evals/web"

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
            if path == "/api/models":
                if not config.get("key"):
                    self.send_json(503, {"error": {"code": "model_unavailable", "message": "De evalserver heeft geen Orq-credential."}})
                else:
                    self.send_json(200, models.payload())
                return
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
                data = ((config["repo"] / "evals/data/scenarios.json") if name == "scenarios.json" else (static / name)).read_bytes()
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
            try:
                rows, _ = scenario_catalog(config["repo"])
                ids = {f"/api/evals/{eval_id}/run": eval_id for eval_id in ["B1", *(row["id"] for row in rows)]}
            except (OSError, ValueError, KeyError, TypeError, RunError):
                self.send_json(503, {"error": {"code": "catalog_unavailable", "message": "De evalcatalogus kon niet worden geladen."}})
                return
            if path not in ids:
                self.send_json(404, {"error": {"code": "unknown_eval", "message": "Deze eval is niet uitvoerbaar."}})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Content-Type", "").split(';')[0] != "application/json" or not 0 < length <= 1024:
                    raise ValueError()
                options = json.loads(self.rfile.read(length))
                if not isinstance(options, dict) or set(options) - {"retrieval_methods", "judge", "model"}:
                    raise ValueError()
                if ids[path] == "B1" and set(options) - {"retrieval_methods"}:
                    raise ValueError()
                methods = options.get("retrieval_methods", ["opinion_chunks"])
                judge_enabled = options.get("judge", "model" in options)
                if (not isinstance(methods, list) or not 1 <= len(methods) <= 2
                        or any(method not in {"opinion_chunks", "head_matter"} for method in methods)
                        or len(set(methods)) != len(methods) or type(judge_enabled) is not bool):
                    raise ValueError()
                if "model" in options and not isinstance(options["model"], str):
                    raise UnsupportedModel("Kies een model-ID uit de serverlijst.")
                selected_model = models.select(options.get("model")) if judge_enabled or "model" in options else None
            except UnsupportedModel as failure:
                self.send_json(400, {"error": {"code": "unsupported_model", "message": str(failure)}})
                return
            except (ValueError, TypeError):
                self.send_json(400, {"error": {"code": "invalid_input", "message": "Deze knop voert alleen de vastgelegde eval-invoer uit."}})
                return
            if not lock.acquire(blocking=False):
                self.send_json(409, {"error": {"code": "busy", "message": "Er loopt al een eval. Wacht tot die klaar is."}})
                return
            try:
                if judge_enabled and not config.get("key"):
                    self.send_json(503, {"error": {"code": "model_unavailable", "message": "De evalserver heeft geen modelcredential."}})
                    return
                run_config = {**config, "retrieval_methods": methods, "judge_enabled": judge_enabled}
                if selected_model is not None:
                    run_config["model"] = selected_model
                self.send_json(200, runner(run_config, ids[path]))
            except (RunError, relevance.EvaluationError) as failure:
                self.send_json(502, {"error": {"code": getattr(failure, "code", "run_failed"), "message": str(failure), "retryable": getattr(failure, "retryable", True)}})
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                self.send_json(503, {"error": {"code": "run_unavailable", "message": "De run is niet voltooid. Controleer de lokale bron, Rustbinary en indexconfiguratie."}})
            finally:
                lock.release()

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=os.environ.get("ORQ_MODEL", DEFAULT_MODEL))
    parser.add_argument("--binary", type=Path, help="Legacy option; web runs use the existing Rust server.")
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("ADAMI_DB_PATH", "data/cases.sqlite3")))
    parser.add_argument("--model-cache", type=Path, default=Path(os.environ.get("ADAMI_CACHE_DIR", ".fastembed_cache")))
    parser.add_argument("--corpus", type=Path, default=Path.home() / "Downloads/texas-criminal-reports")
    parser.add_argument("--outputs", type=Path, default=Path.home() / "Library/Caches/adami-case/web-evals")
    parser.add_argument("--ask-key", action="store_true", help="Ask for an optional key to enable an explicitly selected AI judgment")
    args = parser.parse_args()
    try:
        key = load_api_key()
    except ValueError as failure:
        parser.error(str(failure))
    if args.ask_key and not key:
        key = getpass.getpass("Orq API key (not echoed): ") or ""
    config = {"repo": REPO, "backend": args.backend.rstrip('/'), "model": args.model, "key": key,
              "orq_base": os.environ.get("ORQ_BASE_URL", relevance.ORQ_BASE_URL),
              "database": args.database.resolve(),
              "model_cache": args.model_cache.resolve(), "corpus": args.corpus.resolve(),
              "outputs": args.outputs.resolve(), "models": ModelCatalog(args.model, os.environ.get("ORQ_MODELS"))}
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
