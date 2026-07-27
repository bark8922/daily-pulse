#!/usr/bin/env python3
"""One-time backlog cleanup for daily-pulse.
- drops recurring-noise tasks (dismissed_patterns)
- drops tasks already closed on the dashboard
- canonicalizes every project into the real taxonomy
- normalizes confidence
- collapses near-duplicate rows
- archives untouched tasks older than aging_days
Run once, review, commit."""
import json
from pathlib import Path
from datetime import date
import pulse_lib as L

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
cfg = json.load(open(DATA / "projects.json"))
data = json.load(open(DATA / "tasks.json"))
tasks = data["tasks"]

closed = set()
cf = DATA / "closed.json"
if cf.exists():
    try:
        closed = set(json.load(open(cf)).get("ids", []))
    except Exception:
        pass
overrides = {}
of = DATA / "overrides.json"
if of.exists():
    try:
        overrides = json.load(open(of)).get("overrides", {})
    except Exception:
        pass

AGING = cfg.get("aging_days", 21)
THRESH = cfg.get("dedup_threshold", 0.7)
today = date.today()

start = len(tasks)
report = {"start": start}

# 1. suppress recurring noise
tasks = [t for t in tasks if not L.is_dismissed(cfg, t.get("text", ""))]
report["dropped_noise"] = start - len(tasks)

# 2. drop already-closed
before = len(tasks)
tasks = [t for t in tasks if t.get("id") not in closed]
report["dropped_closed"] = before - len(tasks)

# 3. canonicalize project (respect overrides) + normalize confidence
retagged = 0
for t in tasks:
    tid = t.get("id")
    src = overrides[tid] if tid in overrides else t.get("project")
    canon = L.canon_project(cfg, src)
    if canon != t.get("project"):
        retagged += 1
    t["project"] = canon
    t["confidence"] = L.norm_confidence(t.get("confidence"))
    t.setdefault("status", "open")
report["retagged"] = retagged

# 4. collapse near-duplicate rows
tasks, removed = L.collapse_dups(tasks, overrides, THRESH)
report["dedup_removed"] = removed

# 5. age out untouched stale tasks
n_arch, n_react = L.age_tasks(tasks, overrides, AGING, today)
report["archived"] = n_arch

# fill project_name for rendering
pmap = {p["id"]: p["name"] for p in cfg["projects"]}
pmap["inbox"] = "Needs sorting"
for t in tasks:
    t["project_name"] = pmap.get(t["project"], t["project"])

out = L.build_output(cfg, tasks)
(DATA / "tasks.json").write_text(json.dumps(out, indent=2))

report["end_total"] = len(tasks)
report["active"] = out["active_count"]
report["archived_total"] = out["archived_count"]
print(json.dumps(report, indent=2))
