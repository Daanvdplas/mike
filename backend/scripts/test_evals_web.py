"""One lightweight web-route check; no native model or external API calls."""
import json
import threading
import unittest
from urllib import error, request

import evals_web


class EvalsWebTest(unittest.TestCase):
    def test_catalog_and_one_run_share_the_local_page_without_exposing_files(self):
        calls = []
        config = {"repo": evals_web.REPO, "key": "synthetic"}
        def run(_config, eval_id):
            calls.append(eval_id)
            return {"eval_id": eval_id, "status": "completed"}
        server = evals_web.ThreadingHTTPServer(('127.0.0.1', 0), evals_web.handler_class(config, run))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with request.urlopen(base + "/api/evals") as response:
                data = json.load(response)
            self.assertEqual([row["id"] for row in data["evals"]], ["B1", "E06"])
            self.assertEqual(data["evals"][1]["input_mode"], "query")
            self.assertIsNone(data["evals"][1]["document_label"])
            req = request.Request(base + "/api/evals/E06/run", data=b"{}",
                                  headers={"Origin": base, "Content-Type": "application/json"})
            with request.urlopen(req) as response:
                self.assertEqual(json.load(response)["status"], "completed")
            self.assertEqual(calls, ["E06"])
            removed = request.Request(base + "/api/evals/relevance/run", data=b"{}",
                                      headers={"Origin": base, "Content-Type": "application/json"})
            with self.assertRaises(error.HTTPError) as rejected:
                request.urlopen(removed)
            self.assertEqual(rejected.exception.code, 404)
            rejected.exception.close()
            self.assertEqual(calls, ["E06"])
            config["key"] = None
            without_key = request.Request(base + "/api/evals/B1/run", data=b"{}",
                                          headers={"Origin": base, "Content-Type": "application/json"})
            with request.urlopen(without_key) as response:
                self.assertEqual(json.load(response)["eval_id"], "B1")
            with self.assertRaises(error.HTTPError) as rejected:
                request.urlopen(req)
            self.assertEqual(rejected.exception.code, 503)
            rejected.exception.close()
            with self.assertRaises(error.HTTPError) as rejected:
                request.urlopen(base + "/.git/config")
            self.assertEqual(rejected.exception.code, 404)
            rejected.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
