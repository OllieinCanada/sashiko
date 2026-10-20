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
    module.remote = remote
    module.REPORT["calls"] = []
    module.REPORT.pop("last_error", None)
    module.REPORT.pop("provider_failure", None)
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
        module.REPORT["calls"] = [{"counted_input_tokens": module.MAX_TOTAL_INPUT}]
        assert request(body) == 400
        assert calls == ["countTokens"], "aggregate cap dispatched a paid request"
        assert module.RESERVED == 0
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

# Exercise the real remote helper with a fake opener. No network or sleeps.
class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, maximum):
        return b'{"totalTokens":100}'

class FakeOpener:
    def __init__(self):
        self.timeouts = []
        self.fail = False
    def open(self, request, timeout):
        self.timeouts.append(timeout)
        if self.fail:
            raise TimeoutError("DET8_FAKE_PROVIDER_SECRET held-review-output")
        return FakeResponse()

with tempfile.TemporaryDirectory() as temporary:
    module.OUT = Path(temporary)
    # Compile the function from the exact checked module, not a mirrored helper.
    fresh_spec = importlib.util.spec_from_file_location("transport_controls", Path(__file__).with_name("run.py"))
    transport = importlib.util.module_from_spec(fresh_spec)
    fresh_spec.loader.exec_module(transport)
    transport.OUT = Path(temporary)
    fake = FakeOpener()
    transport.OPENER = fake
    transport.DEADLINE = time.monotonic() + 600
    transport.remote("countTokens", {})
    transport.remote("generateContent", {})
    assert fake.timeouts == [20, 120], fake.timeouts
    assert transport.CLIENT_TIMEOUT > transport.GENERATION_TIMEOUT
    transport.DEADLINE = time.monotonic() + 10
    transport.remote("generateContent", {})
    assert 1 <= fake.timeouts[-1] <= 10
    fake.fail = True
    try:
        transport.remote("generateContent", {})
        raise AssertionError("timeout was accepted")
    except TimeoutError:
        pass
    failure = transport.REPORT["provider_failure"]
    assert failure["action"] == "generateContent"
    assert failure["error_type"] == "TimeoutError"
    assert failure["elapsed_seconds"] >= 0
    assert 1 <= failure["timeout_seconds"] <= 10
    assert "DET8_FAKE_PROVIDER_SECRET" not in (transport.OUT / "manifest.json").read_text()
    assert "held-review-output" not in (transport.OUT / "manifest.json").read_text()
    transport.DEADLINE = time.monotonic() - 1
    count_before = len(fake.timeouts)
    try:
        transport.remote("generateContent", {})
        raise AssertionError("expired deadline was accepted")
    except RuntimeError:
        pass
    assert len(fake.timeouts) == count_before
    print("PASS: exact transport timeout selection, remaining deadline and failure redaction")

# Native commit-range reviews report existing patches as present/current-tree.
# These independently specified fixtures guard against both false failures and
# misleading passes after a stopped or partially reviewed range.
import copy
with tempfile.TemporaryDirectory() as temporary:
    module.OUT = Path(temporary)
    reset()
    module.REPORT["calls"] = [{"status": "RETURNED", "counted_input_tokens": 10}]
    current = {"status": "clean", "patches": [
        {"index": i, "status": "present", "method": "current-tree"}
        for i in range(1, 9)]}
    assert module.review_is_complete(0, current, 8)
    applied = copy.deepcopy(current)
    for patch in applied["patches"]:
        patch.update(status="applied", method="git-am")
    assert module.review_is_complete(0, applied, 8)
    findings = copy.deepcopy(current)
    findings.update(status="issues_found", findings=[{"problem": "inspect this"}])
    assert module.review_is_complete(0, findings, 8)
    invalid = []
    for field, value in [("status", "error"), ("partial", True), ("error", "stopped")]:
        fixture = copy.deepcopy(current)
        fixture[field] = value
        invalid.append(fixture)
    fixture = copy.deepcopy(current)
    fixture["patches"].pop()
    invalid.append(fixture)
    for field, value in [
        ("index", 7), ("index", True), ("status", "error"),
        ("status", "unknown"), ("method", "unknown"),
        ("review_status", "incomplete"), ("review_error", "stopped"),
        ("partial", True), ("error", "apply failed")]:
        fixture = copy.deepcopy(current)
        fixture["patches"][-1][field] = value
        invalid.append(fixture)
    for fixture in invalid:
        assert not module.review_is_complete(0, fixture, 8), fixture
    assert not module.review_is_complete(1, current, 8)
    module.REPORT["last_error"] = "provider stopped"
    assert not module.review_is_complete(0, current, 8)
    module.REPORT.pop("last_error")
    module.REPORT["calls"] = []
    assert not module.review_is_complete(0, current, 8)
    print("PASS: native current-tree completion, findings preserved and incomplete/duplicate/error fixtures rejected")
