"""Read only metadata for the one selected review model."""
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

out = Path("pr455-model-review-results")
out.mkdir(exist_ok=True)
key = os.environ.get("LLM_API_KEY", "")
report = {"status": "BLOCKED_MISSING_KEY", "generation_calls": 0}
if key:
    model = os.environ["SASHIKO_REVIEW_MODEL"]
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/" + model,
        headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
        methods = data.get("supportedGenerationMethods", [])
        report = {"status": "PASS" if "generateContent" in methods else "BLOCKED_UNSUPPORTED_MODEL",
                  "model": data.get("name"), "generation_calls": 0}
    except urllib.error.HTTPError as error:
        report = {"status": "BLOCKED_HTTP", "http_status": error.code, "generation_calls": 0}
    except Exception as error:
        report = {"status": "BLOCKED_TRANSPORT", "error_type": type(error).__name__, "generation_calls": 0}
(out / "metadata-probe.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
if report["status"] != "PASS":
    raise SystemExit(1)
