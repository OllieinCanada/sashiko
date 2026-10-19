#!/usr/bin/env python3
"""Offline negative controls for the review proxy; no credentials/provider calls."""
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location("bounded_review", Path(__file__).with_name("run.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
calls = []


def remote(action, payload):
    calls.append(action)
    if action == "countTokens":
        assert payload["generateContentRequest"]["model"] == "models/" + module.MODEL
        return {"totalTokens": 100}
    return {"usageMetadata": {"promptTokenCount": 110, "candidatesTokenCount": 20,
                              "thoughtsTokenCount": 10}, "candidates": []}


def reset():
    module.REPORT["calls"] = []
    module.REPORT.pop("last_error", None)
    module.RESERVED = Decimal(0)
    module.HALTED = False
    calls.clear()


with tempfile.TemporaryDirectory() as temporary:
    module.OUT = Path(temporary)
    module.DEADLINE = time.monotonic() + 30
    module.remote = remote
    server = module.HTTPServer(("127.0.0.1", 0), module.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(payload, path=None):
        endpoint = path or "/v1beta/models/" + module.MODEL + ":generateContent"
        req = urllib.request.Request("http://127.0.0.1:" + str(server.server_port) + endpoint,
                                     data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    body = {"contents": [{"role": "user", "parts": [{"text": "public diff"}]}],
            "generationConfig": {"maxOutputTokens": 8192}}
    try:
        assert request(body) == 200
        assert calls == ["countTokens", "generateContent"]
        assert module.RESERVED > 0
        assert module.REPORT["calls"][0]["status"] == "RETURNED"
        reset()
        module.RESERVED = module.LIMIT
        assert request(body) == 400
        assert calls == ["countTokens"], "budget exhaustion dispatched a paid request"
        assert request(body) == 400
        assert calls == ["countTokens"], "stopped proxy accepted another request"
        for invalid in [
            dict(body, tools=[{"googleSearch": {}}]),
            dict(body, tools=[{"codeExecution": {}}]),
            dict(body, cachedContent="remote-cache"),
            dict(body, contents=[{"parts": [{"fileData": {"fileUri": "remote"}}]}]),
            dict(body, generationConfig={"candidateCount": 2}),
        ]:
            reset()
            assert request(invalid) == 400
            assert not calls, "invalid request reached provider"
        reset()
        assert request(body, "/v1beta/models/other:generateContent") == 400
        assert not calls
        reset()
        module.REPORT["calls"] = [{} for _ in range(module.MAX_CALLS)]
        assert request(body) == 400
        assert not calls
        reset()
        module.remote = lambda action, payload: {"totalTokens": module.MAX_INPUT + 1}
        assert request(body) == 400
        assert not module.REPORT["calls"]
        reset()
        marker = "DET8_FAKE_PROVIDER_SECRET"
        def reflected_failure(action, payload):
            if action == "countTokens":
                return {"totalTokens": 100}
            raise RuntimeError(marker + " held-review-output")
        module.remote = reflected_failure
        assert request(body) == 400
        encoded = json.dumps(module.REPORT)
        assert marker not in encoded and "held-review-output" not in encoded
        assert module.RESERVED > 0 and module.REPORT["calls"][0]["status"] == "DISPATCHED"
        assert module.HALTED and module.REPORT["last_error"] == "provider proxy refused or failed request"
        assert marker not in (module.OUT / "manifest.json").read_text()
        print("PASS: budget and request controls; provider failure canaries absent from manifest")
    finally:
        server.shutdown()
        server.server_close()
