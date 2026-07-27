#!/usr/bin/env python3
"""Merge scan results into data/tasks.json.
Enforces: noise suppression, project canonicalization, exact + semantic dedup,
closed/override honoring, and aging/archive. Idempotent."""
import sys, re, json
from pathlib import Path
from datetime import date
import pulse_lib as L

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
TASKS_FILE = DATA / "tasks.json"
PROJ_FILE = DATA / "projects.json"
CLOSED_FILE = DATA / "closed.json"
OVERRIDES_FILE = DATA / "overrides.json"

cfg = json.load(open(PROJ_FILE))
PMAP = {p["id"]: p["name"] for p in cfg["projects"]}
PMAP["inbox"] = "Needs sorting"
AGING = cfg.get("aging_days", 21)
THRESH = cfg.get("dedup_threshold", 0.7)

CLOSED_IDS = set()
if CLOSED_FILE.exists():
    try:
        CLOSED_IDS = set(json.load(open(CLOSED_FILE)).get("ids", []))
    except Exception:
        CLOSED_IDS = set()

OVERRIDES = {}
if OVERRIDES_FILE.exists():
    try:
        OVERRIDES = json.load(open(OVERRIDES_FILE)).get("overrides", {})
    except Exception:
        OVERRIDES = {}


def norm_slug(s, n=40):
    return re.sub(r"\W+", "", (s or "").lower())[:n]


def stable_id(source_type, source, text):
    src = (source or "").strip()
    if source_type == "slack":
        return src or "slack/inbox/" + norm_slug(text, 50)
    if source_type == "gmail":
        return src or "gmail/inbox/" + norm_slug(text, 50)
    if source_type in ("fireflies", "cowork"):
        return (src + "/" + norm_slug(text, 40)) if src else source_type + "/inbox/" + norm_slug(text, 50)
    return "inbox/" + norm_slug(text, 50)


today = str(date.today())

if TASKS_FILE.exists():
    existing = json.load(open(TASKS_FILE))
    by_id = {t["id"]: t for t in existing.get("tasks", []) if "id" in t}
else:
    by_id = {}

# Semantic-dedup index over currently-OPEN tasks.
open_index = [(tid, L.toks(t.get("text", "")))
              for tid, t in by_id.items() if t.get("status", "open") != "archived"]

new_tasks = []
for arg in sys.argv[1:]:
    p = Path(arg)
    if not p.exists():
        print("WARN: scan file missing: " + str(p), file=sys.stderr)
        continue
    d = json.load(open(p))
    if isinstance(d, list):
        new_tasks.extend(d)
    elif isinstance(d, dict) and "tasks" in d:
        new_tasks.extend(d["tasks"])

added = updated = skipped_closed = skipped_noise = skipped_semantic = 0
for t in new_tasks:
    text = t.get("text", "")
    if L.is_dismissed(cfg, text):
        skipped_noise += 1
        continue
    t["project"] = L.canon_project(cfg, t.get("project", "inbox"))
    t["confidence"] = L.norm_confidence(t.get("confidence"))
    sid = t.get("id") or stable_id(t["source_type"], t.get("source", ""), text)
    t["id"] = sid

    if sid in CLOSED_IDS:
        skipped_closed += 1
        if sid in by_id:
            del by_id[sid]
        continue

    if sid in by_id:
        ex = by_id[sid]
        if len(text) > len(ex.get("text", "")):
            ex["text"] = text
        ex["date"] = max(ex.get("date", "") or "", t.get("date", "") or "")
        ex["last_seen"] = today
        ex["project"] = t["project"]
        ex["project_name"] = PMAP.get(t["project"], t["project"])
        if t.get("confidence") == "high":
            ex["confidence"] = "high"
        if "extras" in t:
            ex["extras"] = t["extras"]
        updated += 1
        continue

    # Semantic dedup: does this match an existing open task closely?
    nt = L.toks(text)
    match = None
    for eid, etoks in open_index:
        if eid in by_id and L.jacc(nt, etoks) >= THRESH:
            match = eid
            break
    if match:
        ex = by_id[match]
        ex["last_seen"] = today
        ex["date"] = max(ex.get("date", "") or "", t.get("date", "") or "")
        if t.get("confidence") == "high":
            ex["confidence"] = "high"
        skipped_semantic += 1
        continue

    # genuinely new
    t["project_name"] = PMAP.get(t["project"], t["project"])
    t["first_seen"] = t.get("date") or today
    t["last_seen"] = today
    t["status"] = "open"
    by_id[sid] = t
    open_index.append((sid, nt))
    added += 1

# housekeeping: honor closed
for cid in list(CLOSED_IDS):
    if cid in by_id:
        del by_id[cid]

final = list(by_id.values())

# apply overrides (canonicalized) at write time
for t in final:
    if t["id"] in OVERRIDES:
        np = L.canon_project(cfg, OVERRIDES[t["id"]])
        t["project"] = np
        t["project_name"] = PMAP.get(np, np)

# aging/archive
n_arch, n_react = L.age_tasks(final, OVERRIDES, AGING, date.today())

out = L.build_output(cfg, final)
TASKS_FILE.write_text(json.dumps(out, indent=2))
print("Merge: %d added, %d updated, %d skipped-closed, %d skipped-noise, "
      "%d skipped-semantic-dup | archived %d, reactivated %d | %d active / %d archived"
      % (added, updated, skipped_closed, skipped_noise, skipped_semantic,
         n_arch, n_react, out["active_count"], out["archived_count"]))
