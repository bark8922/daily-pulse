#!/usr/bin/env python3
"""
Merge scan results into data/tasks.json using stable IDs.

Usage:
  python3 scripts/merge.py /path/to/scan_fireflies.json /path/to/scan_gmail.json /path/to/scan_slack.json /path/to/scan_cowork.json

Each scan file is a JSON array of task dicts with at minimum:
  text, project, project_name, source, source_type, date, confidence, extras

Reads data/tasks.json (existing) and data/projects.json (config).
Writes data/tasks.json (merged, dedupe by stable ID).
"""
import sys, re, json
from pathlib import Path
from datetime import date

REPO = Path(__file__).resolve().parent.parent
TASKS_FILE = REPO / "data" / "tasks.json"
PROJ_FILE = REPO / "data" / "projects.json"

cfg = json.load(open(PROJ_FILE))
PROJECTS = {p["id"]: p["name"] for p in cfg["projects"]}
PROJECTS["inbox"] = "Inbox (untagged)"
DISMISSED = cfg.get("dismissed_patterns", [])

def norm_slug(s, n=40):
    return re.sub(r'\W+', '', s.lower())[:n]

def stable_id(source_type, source, text):
    src = (source or "").strip()
    if source_type == 'slack':
        return src or f"slack/inbox/{norm_slug(text, 50)}"
    if source_type == 'gmail':
        return src or f"gmail/inbox/{norm_slug(text, 50)}"
    if source_type == 'fireflies':
        return f"{src}/{norm_slug(text, 40)}" if src else f"fireflies/inbox/{norm_slug(text, 50)}"
    if source_type == 'cowork':
        return f"{src}/{norm_slug(text, 40)}" if src else f"cowork/inbox/{norm_slug(text, 50)}"
    return f"inbox/{norm_slug(text, 50)}"

def is_dismissed(text):
    tl = text.lower()
    for pat in DISMISSED:
        if pat.lower() in tl:
            return True
    return False

today = str(date.today())

# Load existing
if TASKS_FILE.exists():
    existing = json.load(open(TASKS_FILE))
    by_id = {t["id"]: t for t in existing.get("tasks", []) if "id" in t}
else:
    by_id = {}

# Load new scans
new_tasks = []
for arg in sys.argv[1:]:
    p = Path(arg)
    if not p.exists():
        print(f"WARN: scan file missing: {p}", file=sys.stderr)
        continue
    data = json.load(open(p))
    if isinstance(data, list):
        new_tasks.extend(data)
    elif isinstance(data, dict) and "tasks" in data:
        new_tasks.extend(data["tasks"])

# Merge
added, updated = 0, 0
for t in new_tasks:
    if is_dismissed(t.get("text", "")):
        continue
    sid = t.get("id") or stable_id(t["source_type"], t.get("source",""), t["text"])
    t["id"] = sid
    proj = t.get("project", "inbox")
    if existing_t := by_id.get(sid):
        # Update: keep first_seen, bump last_seen, take latest text/date/confidence
        existing_t["text"] = t.get("text", existing_t["text"])
        existing_t["date"] = max(existing_t.get("date","") or "", t.get("date","") or "")
        existing_t["last_seen"] = today
        # Don't overwrite project if user might have it set — but project comes from scan, not user
        # User project edits live in browser localStorage anyway
        existing_t["project"] = proj
        existing_t["project_name"] = PROJECTS.get(proj, proj)
        existing_t["confidence"] = t.get("confidence", existing_t.get("confidence","medium"))
        if "extras" in t:
            existing_t["extras"] = t["extras"]
        updated += 1
    else:
        t["project_name"] = PROJECTS.get(proj, proj)
        t["first_seen"] = t.get("date") or today
        t["last_seen"] = today
        t["status"] = "open"
        by_id[sid] = t
        added += 1

# Optional: drop tasks not seen in N days (sliding window)
# Skip for now — keep cumulative until we add server-side close tracking

final = list(by_id.values())
out = {
    "generated_at": today,
    "schema_version": 2,
    "total": len(final),
    "projects": [{"id": p["id"], "name": p["name"], "tier": p["tier"]} for p in cfg["projects"]],
    "tasks": final,
}
TASKS_FILE.write_text(json.dumps(out, indent=2))
print(f"Merge complete: {added} added, {updated} updated, {len(final)} total")
