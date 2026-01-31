import sys
from pathlib import Path
import json
import pytest

# Ensure repo root is on sys.path so `import app...` works in tests
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pretty_json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Attach request/response payloads into pytest-html report.

    In tests, store payloads like:
      request_log = {"method": "...", "url": "...", "json": {...}}
      response_log = {"status_code": 200, "json": {...}}
      item._api_logs = [{"title": "...", "request": ..., "response": ...}, ...]
    """
    outcome = yield
    rep = outcome.get_result()

    if rep.when != "call":
        return

    api_logs = getattr(item, "_api_logs", None)
    if not api_logs:
        return

    # Only attach if pytest-html is installed/enabled
    extras = getattr(rep, "extra", [])

    try:
        import pytest_html  # noqa: F401
        from pytest_html import extras as html_extras
    except Exception:
        rep.extra = extras
        return

    for entry in api_logs:
        title = entry.get("title", "API Call")
        req = entry.get("request", {})
        res = entry.get("response", {})

        html = f"""
        <div style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;">
          <h4 style="margin:8px 0;">{title}</h4>

          <details style="margin:6px 0;">
            <summary><b>Request</b></summary>
            <pre style="background:#0b1020;color:#cfe3ff;padding:10px;border-radius:8px;overflow:auto;">{pretty_json(req)}</pre>
          </details>

          <details style="margin:6px 0;">
            <summary><b>Response</b></summary>
            <pre style="background:#0b1020;color:#cfe3ff;padding:10px;border-radius:8px;overflow:auto;">{pretty_json(res)}</pre>
          </details>
        </div>
        """
        extras.append(html_extras.html(html))

    rep.extra = extras
