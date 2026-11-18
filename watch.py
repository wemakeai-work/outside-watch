#!/usr/bin/env python3
"""Outside watch: poll public health endpoints from OUTSIDE the platform they run on.

Runs on a GitHub Actions schedule. The platform's own watchers run on the same platform, so a platform
outage silences them together with what they watch; this one does not share that fate.

    python watch.py                 # check every target, open/close outage issues, mail on a change
    python watch.py --drill         # also check a target that is meant to fail (proves the alarm path)

State lives in GitHub issues (label `outside-watch`, one open issue per target that is down), so the
alarm goes out once per outage and once on recovery, never every 15 minutes.
A target is down only when it fails twice, RETRY_S apart. Stdlib only.

Exit code: 1 when this run opened an outage issue or could not send its mail - GitHub then mails the
account about the failed run, a second channel that does not depend on the mail provider.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

TARGETS = [
    # name, url, kind: "json" = HTTP 200 and {"ok": true} or {"status": "ok"}; "text" = HTTP 200 and a body starting "ok"
    ("totolix", "https://totolix.com/api/health", "json"),
    ("enjoyhere", "https://api.enjoyhere.eu/health", "json"),   # also false when its heartbeat is stale
    ("dotoday", "https://dotoday.eu/health", "json"),
    ("edooview", "https://edooview.com/api/health", "json"),
    ("businessdash", "https://businessdash.eu/healthz", "json"),
    ("accountingdash", "https://accountingdash.eu/healthz", "json"),
    ("helpdash", "https://helpdash.eu/healthz", "json"),
    ("maildash", "https://maildash.eu/health", "json"),
    ("wmaw.dev", "https://wmaw.dev/health", "json"),
    ("wemakeai.work", "https://wemakeai.work/health", "text"),
]
DRILL = ("drill", "https://wemakeai.work/__outside-watch-drill", "text")   # a 404 on purpose
LABEL = "outside-watch"
TITLE = "DOWN: "
TIMEOUT = 20
RETRY_S = 90


def verdict(status: int, body: str, kind: str) -> tuple[bool, str]:
    """Pure: is this answer healthy?"""
    if status != 200:
        return False, f"HTTP {status}"
    if kind == "text":
        return (True, "ok") if body.strip().startswith("ok") else (False, "body does not start with 'ok'")
    try:
        j = json.loads(body)
    except ValueError:
        return False, "not JSON"
    if not isinstance(j, dict):
        return False, "JSON is not an object"
    if j.get("ok") is True or j.get("status") == "ok":
        return True, "ok"
    return False, "ok is not true" + (f" (heartbeat {j['heartbeat_age_minutes']} min old)" if "heartbeat_age_minutes" in j else "")


def plan(down: dict[str, str], open_issues: dict[str, int]) -> tuple[list[str], list[str]]:
    """Pure: (targets to open an issue for, targets whose issue to close). A watched-no-more issue closes too."""
    to_open = sorted(n for n in down if n not in open_issues)
    to_close = sorted(n for n in open_issues if n not in down)
    return to_open, to_close


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "outside-watch"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001 - a dead endpoint is a result, not a crash
        return 0, f"{type(e).__name__}: {e}"


def check(targets, get=fetch, wait=time.sleep, retry_s: float = RETRY_S) -> dict[str, str]:
    """{name: reason} for every target that failed twice, retry_s apart."""
    first = {}
    for name, url, kind in targets:
        status, body = get(url)
        ok, why = verdict(status, body, kind)
        print(f"  {'ok  ' if ok else 'FAIL'} {name:15} {why if status else body[:120]}")
        if not ok:
            first[name] = (url, kind)
    if not first:
        return {}
    wait(retry_s)
    down = {}
    for name, (url, kind) in first.items():
        status, body = get(url)
        ok, why = verdict(status, body, kind)
        print(f"  retry {name:15} {'ok' if ok else why if status else body[:120]}")
        if not ok:
            down[name] = f"{url}: {why if status else body[:200]}"
    return down


# ---- GitHub issues (state) --------------------------------------------------------------------------------

def gh(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json", "User-Agent": "outside-watch"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def open_issues() -> dict[str, int]:
    out = {}
    for i in gh("GET", f"/issues?state=open&labels={LABEL}&per_page=100"):
        if i["title"].startswith(TITLE):
            out[i["title"][len(TITLE):]] = i["number"]
    return out


# ---- mail -------------------------------------------------------------------------------------------------

def mail(subject: str, text: str) -> bool:
    key, to, sender, project = (os.environ.get(k, "") for k in ("SCW_TEM_KEY", "ALARM_TO", "ALARM_FROM", "SCW_PROJECT_ID"))
    if not (key and to and sender and project):
        print("  mail: not configured (SCW_TEM_KEY / ALARM_TO / ALARM_FROM / SCW_PROJECT_ID) - the failed run is the alarm")
        return False
    payload = {"from": {"email": sender, "name": "outside-watch"}, "to": [{"email": to}],
               "subject": subject, "text": text, "project_id": project}
    req = urllib.request.Request("https://api.scaleway.com/transactional-email/v1alpha1/regions/fr-par/emails",
                                 method="POST", data=json.dumps(payload).encode(),
                                 headers={"X-Auth-Token": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  mail sent: {subject} -> {r.status}")
            return True
    except Exception as e:  # noqa: BLE001 - the mail provider may be down with everything else
        print(f"  mail FAILED: {type(e).__name__}: {e}")
        return False


def main() -> int:
    targets = TARGETS + ([DRILL] if "--drill" in sys.argv else [])
    print(f"outside-watch: {len(targets)} targets")
    down = check(targets)
    issues = open_issues()
    to_open, to_close = plan(down, issues)
    run = f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    failed = False
    for n in to_open:
        i = gh("POST", "/issues", {"title": TITLE + n, "labels": [LABEL], "body": f"{down[n]}\n\nRun: {run}"})
        print(f"  opened #{i['number']} {TITLE}{n}")
        failed = True
    for n in to_close:
        gh("POST", f"/issues/{issues[n]}/comments", {"body": f"Up again (or no longer watched). Run: {run}"})
        gh("PATCH", f"/issues/{issues[n]}", {"state": "closed"})
        print(f"  closed #{issues[n]} {TITLE}{n}")
    if to_open or to_close:
        lines = [f"DOWN  {n}: {down[n]}" for n in to_open] + [f"UP    {n}" for n in to_close]
        still = sorted(set(down) - set(to_open))
        subj = (f"DOWN {', '.join(to_open)}" if to_open else f"UP {', '.join(to_close)}") + " (outside-watch)"
        body = "\n".join(lines) + (f"\n\nStill down: {', '.join(still)}" if still else "") + f"\n\nRun: {run}\n"
        if not mail(subj, body):
            failed = True
    print(f"down: {sorted(down) or 'none'}; opened {to_open or 'none'}; closed {to_close or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
