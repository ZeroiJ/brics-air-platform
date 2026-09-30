"""Focused test for the frontend's cold-start retry (_request).

Extracts the function from frontend/app.py via AST and exercises it against a
scripted backend, so nothing Streamlit-specific is imported.
"""
import ast
import types

import requests as real_requests

APP = "frontend/app.py"
src = open(APP, encoding="utf-8").read()
tree = ast.parse(src)

fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_request")
consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            name = getattr(t, "id", "")
            if name.startswith("_RETRY_") or name.startswith("_TRANSIENT_"):
                consts[name] = ast.literal_eval(node.value)

slept = []


class FakeResp:
    def __init__(self, code):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.HTTPError(f"{self.status_code}")

    def json(self):
        return {"ok": self.status_code == 200}


def build(script):
    """script: list of int status codes, or Exception instances to raise."""
    steps = list(script)

    def fake_request(method, url, **kw):
        step = steps.pop(0) if steps else 200
        if isinstance(step, Exception):
            raise step
        return FakeResp(step)

    ns = {
        "requests": types.SimpleNamespace(
            request=fake_request,
            ConnectionError=real_requests.ConnectionError,
            Timeout=real_requests.Timeout,
            RequestException=real_requests.RequestException,
        ),
        "time": types.SimpleNamespace(sleep=lambda s: slept.append(s)),
        "_RETRY_ATTEMPTS": consts.get("_RETRY_ATTEMPTS", 3),
        "_RETRY_BACKOFF": consts.get("_RETRY_BACKOFF", 4.0),
        "_TRANSIENT_ATTEMPTS": consts.get("_TRANSIENT_ATTEMPTS", 2),
        "_TRANSIENT_BACKOFF": consts.get("_TRANSIENT_BACKOFF", 1.0),
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), APP, "exec"), ns)
    return ns["_request"]


def run(name, script, expect, expect_sleeps, expect_calls=None):
    slept.clear()
    steps = list(script)
    f = build(script)
    calls = {"n": 0}
    inner = f

    # wrap to count attempts
    ns_req = None
    try:
        got = inner("GET", "http://x/y")
        got = ("ok", got.status_code)
    except Exception as e:  # noqa: BLE001
        got = ("raise", type(e).__name__)
    ok = got == expect and slept == expect_sleeps
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"          result={got}  expected={expect}")
    print(f"          slept={slept}  expected={expect_sleeps}")
    if not ok:
        print("          <<< MISMATCH")
    return ok


print("retry helper constants:", consts)
print()
results = []
# The real incident: sleeping Render answers 503, 503, then wakes up.
results.append(run("503, 503, then 200 -> succeeds",
                   [503, 503, 200], ("ok", 200), [4.0, 8.0]))
results.append(run("503 once, then 200 -> succeeds",
                   [503, 200], ("ok", 200), [4.0]))
# Connection dropped instead of 503.
# A refused connection is NOT a booting instance -- one quick retry only.
results.append(run("ConnectionError, then 200 -> quick retry",
                   [real_requests.ConnectionError("reset"), 200], ("ok", 200), [1.0]))
results.append(run("ReadTimeout, then 200 -> quick retry",
                   [real_requests.ReadTimeout("slow"), 200], ("ok", 200), [1.0]))
# Still asleep after every attempt -> fail loudly, but only after retrying.
results.append(run("503 x3 -> HTTPError after retrying",
                   [503, 503, 503], ("raise", "HTTPError"), [4.0, 8.0]))
# Backend genuinely down: must fail after ONE short sleep, not 12s per call.
results.append(run("ConnectionError x3 -> ConnectionError, single 1s wait",
                   [real_requests.ConnectionError("a"), real_requests.ConnectionError("b"),
                    real_requests.ConnectionError("c")],
                   ("raise", "ConnectionError"), [1.0]))
# A genuine 4xx/5xx must NOT be retried — otherwise a real bug turns into a
# slow, misleading error during the demo.
results.append(run("422 immediately -> no retry",
                   [422], ("raise", "HTTPError"), []))
results.append(run("500 immediately -> no retry",
                   [500], ("raise", "HTTPError"), []))
results.append(run("200 straight through, no sleep",
                   [200], ("ok", 200), []))

print()
print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
