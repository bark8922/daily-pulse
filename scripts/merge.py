#!/usr/bin/env python3
"""Merge scan results into data/tasks.json. Stable-ID dedupe. Honor closed.json + overrides.json."""
import sys, re, json
from pathlib import Path
from datetime import date

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
TASKS_FILE = DATA / "tasks.json"
PROJ_FILE = DATA / "projects.json"
CLOSED_FILE = DATA / "closed.json"
OVERRIDES_FILE = DATA / "overrides.json"

cfg = json.load(open(PROJ_FILE))
PROJECTS = {p["id"]: p["name"] for p in cfg["projects"]}
PROJECTS["inbox"] = "Inbox (untagged)"
DISMISSED = cfg.get("dismissed_patterns", [])

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
    return re.sub(r'\W+', '', s.lower())[:n]

def stable_id(source_type, source, text):
    src = (source or "").strip()
    if source_type == 'slack':
        return src or "slack/inbox/" + norm_slug(text, 50)
    if source_type == 'gmail':
        return src or "gmail/inbox/" + norm_slug(text, 50)
    if source_type == 'fireflies':
        return (src + "/" + norm_slug(text, 40)) if src else "fireflies/inbox/" + norm_slug(text, 50)
    if source_type == 'cowork':
        return (src + "/" + norm_slug(text, 40)) if src else "cowork/inbox/" + norm_slug(text, 50)
    return "inbox/" + norm_slug(text, 50)

def is_dismissed(text):
    tl = text.lower()
    for pat in DISMISSED:
        if pat.lower() in tl:
            return True
    return False

today = str(date.today())

if TASKS_FILE.exists():
    existing = json.load(open(TASKS_FILE))
    by_id = {t["id"]: t for t in existing.get("tasks", []) if "id" in t}
else:
    by_id = {}

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

added, updated, skipped_closed = 0, 0, 0
for t in new_tasks:
    if is_dismissed(t.get("text", "")):
        continue
    sid = t.get("id") or stable_id(t["source_type"], t.get("source",""), t["text"])
    t["id"] = sid
    if sid in CLOSED_IDS:
        # User closed this on the dashboard; do not re-introduce
        skipped_closed += 1
        if sid in by_id:
            del by_id[sid]
        continue
    proj = t.get("project", "inbox")
    if sid in by_id:
        ex = by_id[sid]
        if len(t.get("text","")) > len(ex.get("text","")):
            ex["text"] = t["text"]
        ex["date"] = max(ex.get("date","") or "", t.get("date","") or "")
        ex["last_seen"] = today
        ex["project"] = proj
        ex["project_name"] = PROJECTS.get(proj, proj)
        if t.get("confidence") == "high":
            ex["confidence"] = "high"
        if "extras" in t:
            ex["extras"] = t["extras"]
        updated += 1
    else:
        t["project_name"] = PROJECTS.get(proj, proj)
        t["first_seen"] = t.get("date") or today
        t["last_seen"] = today
        t["status"] = "open"
        by_id[sid] = t
        added += 1

# Remove anything that is now in CLOSED_IDS (idempotent housekeeping)
for cid in list(CLOSED_IDS):
    if cid in by_id:
        del by_id[cid]

final = list(by_id.values())
# Apply project overrides at write time (server-side source of truth for re-tags)
for t in final:
    if t["id"] in OVERRIDES:
        new_proj = OVERRIDES[t["id"]]
        t["project"] = new_proj
        t["project_name"] = PROJECTS.get(new_proj, new_proj)

out = {
    "generated_at": today,
    "schema_version": 2,
    "total": len(final),
    "projects": [{"id": p["id"], "name": p["name"], "tier": p.get("tier","medium")} for p in cfg["projects"]],
    "tasks": final,
}
TASKS_FILE.write_text(json.dumps(out, indent=2))
print(f"Merge: {added} added, {updated} updated, {skipped_closed} skipped (closed), {len(final)} total")
