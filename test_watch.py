"""Tests for watch.py - stdlib only: python test_watch.py"""
import sys

import watch as w

bad = 0


def check(name, cond, detail=""):
    global bad
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    bad += 0 if cond else 1


# verdict
check("json ok:true is healthy", w.verdict(200, '{"ok":true}', "json")[0])
check("json status:ok is healthy (devboard shape)", w.verdict(200, '{"status":"ok","version":"x"}', "json")[0])
ok, d = w.verdict(200, '{"ok":false,"heartbeat_age_minutes":51}', "json")
check("json ok:false is down and names the heartbeat age", not ok and "51 min" in d, d)
check("json ok missing is down", not w.verdict(200, '{"version":"x"}', "json")[0])
check("json ok as the string 'true' is down (only a real true counts)", not w.verdict(200, '{"ok":"true"}', "json")[0])
check("HTTP 503 is down whatever the body", not w.verdict(503, '{"ok":true}', "json")[0])
check("an HTML error page is down", not w.verdict(200, "<html>oops</html>", "json")[0])
check("text 'ok <sha>' is healthy", w.verdict(200, "ok ff5bc47", "text")[0])
check("text 404 is down", not w.verdict(404, "", "text")[0])

# plan
o, c = w.plan({"a": "x"}, {})
check("a new outage opens one issue", o == ["a"] and c == [], (o, c))
o, c = w.plan({"a": "x"}, {"a": 7})
check("an outage with an open issue opens nothing (no repeat mail)", o == [] and c == [], (o, c))
o, c = w.plan({}, {"a": 7})
check("recovery closes the issue", o == [] and c == ["a"], (o, c))
o, c = w.plan({"b": "x"}, {"a": 7})
check("one recovers while another fails", o == ["b"] and c == ["a"], (o, c))

# check: two strikes
answers = {"u1": [(503, ""), (200, '{"ok":true}')], "u2": [(503, ""), (503, "")]}
def fake(url):
    return answers[url].pop(0)
waited = []
down = w.check([("one", "u1", "json"), ("two", "u2", "json")], get=fake, wait=waited.append, retry_s=0)
check("a single failure that recovers on the retry is NOT down", "one" not in down, down)
check("two failures in a row are down", "two" in down, down)
check("it waits once before the retry", waited == [0], waited)
waited.clear()
down = w.check([("ok", "u3", "json")], get=lambda u: (200, '{"ok":true}'), wait=waited.append)
check("all healthy: no retry wait at all", down == {} and waited == [], (down, waited))

# the targets themselves
names = [t[0] for t in w.TARGETS]
check("no duplicate target names", len(names) == len(set(names)))
check("every target is https and public (no platform-internal host)",
      all(u.startswith("https://") and "scw.cloud" not in u for _, u, _ in w.TARGETS))
check("the drill target is not watched by default", w.DRILL not in w.TARGETS)

TOTAL = 20
print(f"{TOTAL - bad}/{TOTAL} passed")
sys.exit(1 if bad else 0)
