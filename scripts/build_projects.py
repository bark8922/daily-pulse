#!/usr/bin/env python3
"""Generate data/projects.json from data/ledger.json + data/scan_config.json.

The Notion database "Blake - Project Ledger" is the source of truth for the
project taxonomy. The scheduled scan mirrors it into data/ledger.json, then runs
this script. DO NOT hand-edit data/projects.json: it is overwritten every run.

To add, rename, merge or retire a project, edit the Notion database.
  - Add a row            -> new project appears on the next run
  - Set Status=Retired   -> project is dropped from the taxonomy
  - Put an old id in the "Aliases" field of the surviving project
                         -> that id's tasks re-route instead of orphaning
"""
import json, sys, datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

def main():
    ledger = json.load(open(DATA / "ledger.json"))
    scan = json.load(open(DATA / "scan_config.json"))

    live = [p for p in ledger["projects"] if p.get("status") != "Retired"]
    tiermap = {"Core": "big", "Supporting": "medium", "Personal": "medium"}

    projects, aliases, seen = [], {}, set()
    for p in live:
        pid = p["id"]
        if pid in seen:
            sys.exit(f"ERROR: duplicate project id in ledger: {pid}")
        seen.add(pid)
        projects.append({
            "id": pid,
            "name": p["name"],
            "tier": tiermap.get(p.get("tier"), "medium"),
            "notes": p.get("current_state", "")[:280],
        })
        for a in p.get("aliases", []):
            a = a.strip().lower()
            if not a or a == pid:
                continue
            if a in seen:
                sys.exit(f"ERROR: alias '{a}' on {pid} collides with a live project id")
            if a in aliases and aliases[a] != pid:
                sys.exit(f"ERROR: alias '{a}' claimed by both {aliases[a]} and {pid}")
            aliases[a] = pid

    # retired ids must resolve somewhere or the scan will orphan their tasks
    for r in ledger.get("retired", []):
        if r["id"] not in aliases and r["id"] not in seen:
            print(f"WARNING: retired project '{r['id']}' has no alias route. "
                  f"Its tasks will fall to inbox.", file=sys.stderr)

    out = dict(scan)
    out["updated"] = datetime.date.today().isoformat()
    out["generated_from"] = "data/ledger.json (Notion). Do not hand-edit."
    out["projects"] = projects
    out["project_aliases"] = dict(sorted(aliases.items()))

    json.dump(out, open(DATA / "projects.json", "w"), indent=2, ensure_ascii=False)
    print(f"projects.json: {len(projects)} projects, {len(aliases)} aliases")

if __name__ == "__main__":
    main()
