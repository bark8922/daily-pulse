#!/usr/bin/env python3
"""Merge scan results into data/tasks.json via stable IDs + semantic dedupe."""
import sys, re, json
from pathlib import Path
from datetime import date
from difflib import SequenceMatcher

REPO = Path(__file__).resolve().parent.parent
TASKS_FILE = REPO / "data" / "tasks.json"
PROJ_FILE = REPO / "data" / "projects.json"

cfg = json.load(open(PROJ_FILE))
PROJECTS = {p["id"]: p["name"] for p in cfg["projects"]}
PROJECTS["inbox"] = "Inbox (untagged)"
DISMISSED = cfg.get("dismissed_patterns", [])

def norm_slug(s, n=40):
    return re.sub(r'\W+', '', s.lower())[:n]

def norm_text(s):
    return re.sub(r'\s+', ' ', s.lower().strip())

def sim_score(a, b):
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()

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

def find_similar(t, by_id_dict, same_source_threshold=0.65, cross_source_threshold=0.85):
    new_text = t.get('text','')
    new_src = t.get('source','')
    for ex_id, ex in by_id_dict.items():
        if not ex.get('text'):
            continue
        thresh = same_source_threshold if ex.get('source') == new_src else cross_source_threshold
        if sim_score(new_text, ex['text']) >= thresh:
            return ex_id
    return None

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
    data = json.load(open(p))
    if isinstance(data, list):
        new_tasks.extend(data)
    elif isinstance(data, dict) and "tasks" in data:
        new_tasks.extend(data["tasks"])

added, updated = 0, 0
for t in new_tasks:
    if is_dismissed(t.get("text", "")):
        continue
    sid = t.get("id") or stable_id(t["source_type"], t.get("source",""), t["text"])
    t["id"] = sid
    proj = t.get("project", "inbox")
    # Semantic dedupe disabled — rely on stable IDs only.
    # Stable IDs catch true re-detection (same source artifact).
    # Different action phrasings = different stable IDs = treated as separate tasks (intentional).
    if sid in by_id:
        existing_t = by_id[sid]
        # Keep longer text (usually more informative)
        if len(t.get("text","")) > len(existing_t.get("text","")):
            existing_t["text"] = t["text"]
        existing_t["date"] = max(existing_t.get("date","") or "", t.get("date","") or "")
        existing_t["last_seen"] = today
        existing_t["project"] = proj
        existing_t["project_name"] = PROJECTS.get(proj, proj)
        if t.get("confidence") == "high":
            existing_t["confidence"] = "high"
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

final = list(by_id.values())
out = {
    "generated_at": today,
    "schema_version": 2,
    "total": len(final),
    "projects": [{"id": p["id"], "name": p["name"], "tier": p["tier"]} for p in cfg["projects"]],
    "tasks": final,
}
TASKS_FILE.write_text(json.dumps(out, indent=2))
print("Merge complete: " + str(added) + " added, " + str(updated) + " updated, " + str(len(final)) + " total")
