"""Read-only Gemini model metadata probe; never generate or print errors."""
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

key = os.environ.pop("LLM_API_KEY", "")
report = {"status": "BLOCKED_MISSING_KEY", "generation_calls": 0}
if key:
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash",
        headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            model = json.load(response)
        methods = model.get("supportedGenerationMethods", [])
        report = {"status": "PASS" if "generateContent" in methods else "BLOCKED_UNSUPPORTED_MODEL",
                  "model": model.get("name"), "methods": methods, "generation_calls": 0}
    except urllib.error.HTTPError as error:
        report = {"status": "BLOCKED_HTTP", "http_status": error.code, "generation_calls": 0}
    except Exception as error:
        report = {"status": "BLOCKED_TRANSPORT", "error_type": type(error).__name__,
                  "generation_calls": 0}
Path("model-metadata-probe.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
if report["status"] != "PASS":
    raise SystemExit(1)
