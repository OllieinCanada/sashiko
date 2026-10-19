#!/usr/bin/env python3
"""Bound one authorized Sashiko review; never expose the provider credential."""
import datetime
from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

MODEL = os.environ.get("SASHIKO_REVIEW_MODEL", "gemini-3.8-flash")
if MODEL not in {"gemini-3.8-flash", "gemini-3.6-flash"}:
    raise RuntimeError("model is outside the approved equal-price allowlist")
ORIGIN = "https://generativelanguage.googleapis.com"
INPUT_PRICE = Decimal("0.75")
OUTPUT_PRICE = Decimal("3.75")
LIMIT = Decimal("2.25")  # First attempt; one separately activated follow-up <= $2.25.
MAX_INPUT = 150000
MAX_OUTPUT = 8192
MAX_CALLS = 30
TIME_LIMIT = 600
OUT = Path.cwd() / "adaptive-model-review-results"
OUT.mkdir(exist_ok=True)
REPORT = {
    "status": "NOT_STARTED", "model": MODEL, "maximum_usd_this_attempt": str(LIMIT),
    "maximum_seconds_this_attempt": TIME_LIMIT,
    "overall_authorization": "initial plus at most one follow-up; $4.50 and 20 minutes total",
    "pricing_source": "https://ai.google.dev/gemini-api/docs/pricing",
    "pricing_checked_utc": "2026-10-19", "input_usd_per_million": str(INPUT_PRICE),
    "output_usd_per_million_including_thinking": str(OUTPUT_PRICE),
    "reserved_usd": "0", "calls": [],
    "limitations": ["Model review is advisory; deterministic checks remain required.",
                   "A timeout, exhausted budget, partial result or missing patch result is not a clean review."],
}
KEY = os.environ.pop("LLM_API_KEY", "")
DEADLINE = None
RESERVED = Decimal(0)
HALTED = False


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect())


def remote(action, payload):
    remaining = DEADLINE - time.monotonic()
    if remaining < 1:
        raise RuntimeError("review deadline reached")
    req = urllib.request.Request(
        ORIGIN + "/v1beta/models/" + MODEL + ":" + action,
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": KEY},
    )
    try:
        with OPENER.open(req, timeout=min(60, remaining)) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise RuntimeError("provider response too large")
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        REPORT["provider_failure"] = {"action": action, "http_status": error.code}
        save()
        raise
    except Exception as error:
        REPORT["provider_failure"] = {"action": action, "error_type": type(error).__name__}
        save()
        raise


def validate_request(body):
    allowed = {"contents", "systemInstruction", "tools", "toolConfig",
               "generationConfig", "safetySettings"}
    if not isinstance(body, dict) or set(body) - allowed:
        raise RuntimeError("unsupported provider request fields")
    config = body.setdefault("generationConfig", {})
    if config.get("candidateCount", 1) != 1:
        raise RuntimeError("multiple candidates are not authorized")
    config["candidateCount"] = 1
    config["maxOutputTokens"] = min(config.get("maxOutputTokens", MAX_OUTPUT), MAX_OUTPUT)
    if not 1 <= config["maxOutputTokens"] <= MAX_OUTPUT:
        raise RuntimeError("invalid output cap")
    for tool in body.get("tools", []):
        if set(tool) - {"functionDeclarations"}:
            raise RuntimeError("paid or remote provider tools are not authorized")

    def walk(value):
        if isinstance(value, dict):
            if any(k in value for k in ("fileData", "inlineData", "executableCode",
                                       "codeExecutionResult", "cachedContent")):
                raise RuntimeError("only text and local function calls are authorized")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        global RESERVED, HALTED
        try:
            if HALTED:
                raise RuntimeError("provider proxy already stopped")
            if self.path != "/v1beta/models/" + MODEL + ":generateContent":
                raise RuntimeError("unsupported provider endpoint")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2 * 1024 * 1024:
                raise RuntimeError("invalid provider request size")
            body = json.loads(self.rfile.read(length))
            validate_request(body)
            if len(REPORT["calls"]) >= MAX_CALLS:
                raise RuntimeError("provider call limit reached")
            # Count the full request, including system instructions and tool schemas.
            count_request = dict(body, model="models/" + MODEL)
            count = remote("countTokens", {"generateContentRequest": count_request})
            tokens = count.get("totalTokens")
            if not isinstance(tokens, int) or not 0 < tokens <= MAX_INPUT:
                raise RuntimeError("provider input-token cap reached")
            # Add count/generation framing slack. Never refund reservations, including
            # failed/time-out calls, because a lost response may still be billed.
            reserved_input = tokens + max(2048, (tokens + 19) // 20)
            upper = (Decimal(reserved_input) * INPUT_PRICE
                     + Decimal(MAX_OUTPUT) * OUTPUT_PRICE) / Decimal(1000000)
            if RESERVED + upper > LIMIT:
                raise RuntimeError("provider dollar budget reached")
            RESERVED += upper
            record = {"number": len(REPORT["calls"]) + 1,
                      "counted_input_tokens": tokens,
                      "reserved_input_tokens": reserved_input,
                      "maximum_output_tokens": MAX_OUTPUT,
                      "reserved_usd": str(upper), "status": "DISPATCHED"}
            REPORT["calls"].append(record)
            REPORT["reserved_usd"] = str(RESERVED)
            save()
            response = remote("generateContent", body)
            usage = response.get("usageMetadata", {})
            record["usage"] = {k: usage.get(k) for k in (
                "promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount",
                "cachedContentTokenCount", "totalTokenCount")}
            actual_input = usage.get("promptTokenCount")
            output = (usage.get("candidatesTokenCount", 0)
                      + usage.get("thoughtsTokenCount", 0))
            if (not isinstance(actual_input, int) or actual_input > reserved_input
                    or not isinstance(output, int) or output > MAX_OUTPUT):
                record["status"] = "ACCOUNTING_MISMATCH"
                save()
                raise RuntimeError("provider usage exceeded reservation; review stopped")
            record["status"] = "RETURNED"
            save()
            data = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            HALTED = True
            # Never relay provider error bodies, URLs, request content or credentials.
            REPORT["last_error"] = "provider proxy refused or failed request"
            save()
            data = b'{"error":{"code":400,"message":"Review request stopped by bounded proxy"}}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass


def review(directory, base, head):
    global DEADLINE
    REPORT.update({"base": base, "head": head, "status": "PREPARING"})
    save()
    if not KEY:
        REPORT["status"] = "BLOCKED_MISSING_LLM_API_KEY"
        save()
        raise RuntimeError("LLM_API_KEY is not configured")
    if datetime.datetime.now(datetime.timezone.utc).date() > datetime.date(2026, 12, 31):
        raise RuntimeError("pricing authorization expired")
    env = os.environ.copy()
    for name in list(env):
        if any(word in name for word in ("TOKEN", "SECRET", "API_KEY")):
            env.pop(name)
    env["GEMINI_API_KEY"] = "bounded-loopback-placeholder"
    env["RUST_LOG"] = "warn"
    env["CARGO_TARGET_DIR"] = str(Path.cwd() / "target")
    env["RUSTUP_TOOLCHAIN"] = "stable"
    subprocess.run(["cargo", "build", "--locked", "--no-default-features",
                    "--bin", "sashiko"], cwd=directory, env=env, check=True,
                   timeout=600, stdout=subprocess.DEVNULL)
    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = OUT / "review-settings.toml"
    settings.write_text(
        'log_level = "warn"\n[ai]\nprovider = "gemini"\nmodel = "' + MODEL + '"\n'
        'max_input_tokens = 150000\nmax_interactions = 12\napi_timeout_secs = 65\n'
        'response_cache = false\nlog_turns = false\n'
        '[ai.gemini]\nexplicit_prompt_caching = false\nmax_tokens = 8192\n'
        'base_url = "http://127.0.0.1:' + str(server.server_port) + '"\n'
        '[database]\nurl = "' + str(OUT / "local-review.db") + '"\ntoken = ""\n'
        '[review]\nconcurrency = 1\ntimeout_seconds = 540\nmax_retries = 0\n'
        'max_total_tokens = 2500000\nmax_total_output_tokens = 150000\n')
    binary = Path(env["CARGO_TARGET_DIR"]) / "debug/sashiko"
    args = [str(binary), "--project", "sashiko", "review",
            "--settings", str(settings), "--agent", base + ".." + head]
    REPORT["command"] = args
    REPORT["status"] = "RUNNING"
    DEADLINE = time.monotonic() + TIME_LIMIT
    save()
    process = None
    try:
        with (OUT / "agent.json").open("w") as stdout, (OUT / "review.log").open("w") as stderr:
            process = subprocess.Popen(args, cwd=directory, env=env, stdout=stdout,
                                       stderr=stderr, start_new_session=True)
            try:
                code = process.wait(timeout=TIME_LIMIT)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                raise RuntimeError("review time limit reached")
        raw = (OUT / "agent.json").read_text()
        result = json.loads(raw)
        patches = result.get("patches", [])
        expected = subprocess.check_output(
            ["git", "rev-list", "--count", base + ".." + head],
            cwd=directory, text=True).strip()
        complete = (code == 0 and result.get("status") in ("clean", "issues_found")
                    and result.get("partial", False) is False and not result.get("error")
                    and REPORT["calls"] and not REPORT.get("last_error")
                    and len(patches) == int(expected)
                    and not any(p.get("error") or p.get("partial") for p in patches))
        REPORT["agent_status"] = result.get("status")
        REPORT["findings"] = result.get("findings", [])
        REPORT["concerns"] = result.get("concerns", [])
        REPORT["status"] = "COMPLETED" if complete else "INCOMPLETE"
        REPORT["agent_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
        save()
        if not complete:
            raise RuntimeError("model review did not complete all patches")
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        for path in (OUT / "agent.json", OUT / "review.log"):
            if path.exists() and KEY:
                path.write_text(path.read_text().replace(KEY, "[REDACTED]"))
        save()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: run.py CHECKED_DIRECTORY BASE HEAD")
    try:
        review(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    except Exception as error:
        if REPORT["status"] not in ("BLOCKED_MISSING_LLM_API_KEY", "INCOMPLETE"):
            REPORT["status"] = "FAILED"
        REPORT["error"] = str(error).replace(KEY, "[REDACTED]") if KEY else str(error)
        save()
        raise SystemExit(1)
