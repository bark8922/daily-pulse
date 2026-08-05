#!/usr/bin/env python3
"""Generate one markdown body per project into /tmp/pages/<project_id>.md

Run after merge.py. The scheduled task then pushes each file into the matching
Notion page with update-page / replace_content, so opening a project card shows
where it stands plus every open task under it.
"""
import json, datetime, re
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = Path("/tmp/pages"); OUT.mkdir(exist_ok=True)
TODAY = datetime.date.today()

PERSONAL = re.compile(
    r"job.search|kosik|alza|rental|bezrealitky|salespad|poseidon|govai|"
    r"usercentrics|floor fan|interview mp4|COO-titled", re.I)
SRC = {"fireflies": "meeting", "slack": "Slack", "gmail": "email", "cowork": "Claude"}
DASH = "https://bark8922.github.io/daily-pulse/"


def main():
    led = json.load(open(DATA / "ledger.json"))
    tasks = json.load(open(DATA / "tasks.json"))
    aliases = json.load(open(DATA / "projects.json"))["project_aliases"]
    have_personal = any(p["id"] == "personal" for p in led["projects"])

    grouped = defaultdict(list)
    for t in tasks["tasks"]:
        if t.get("status") != "open":
            continue
        pid = t["project"]
        if pid == "inbox" and have_personal and PERSONAL.search(t["text"]):
            pid = "personal"
        grouped[aliases.get(pid, pid)].append(t)

    written = []
    for pr in led["projects"]:
        if pr.get("status") == "Retired":
            continue
        pid = pr["id"]
        rows = sorted(grouped.get(pid, []), key=lambda x: x["date"], reverse=True)

        def days(t):
            return (TODAY - datetime.date.fromisoformat(t["date"])).days

        recent = [t for t in rows if days(t) <= 7]
        older = [t for t in rows if days(t) > 7]

        L = ["## Where it stands", pr.get("current_state") or "_No state recorded yet._", "",
             "## Waiting on", (pr.get("waiting_on") or "").strip() or "_Nothing recorded._", "",
             "## Next", pr.get("next_action") or "_Nothing recorded._", "",
             "---", "",
             f"## Open tasks ({len(rows)})",
             f"Mirror of Daily Pulse, rewritten twice a day. Tick things off at {DASH} , not here.", ""]

        for title, block in (("Last 7 days", recent), ("Older", older)):
            if not block:
                continue
            L += [f"**{title}** ({len(block)})", ""]
            for t in block:
                when = datetime.date.fromisoformat(t["date"]).strftime("%d %b").lstrip("0")
                src = SRC.get(t["source_type"], t["source_type"])
                L.append(f"- {t['text'].replace(chr(10), ' ').strip()} `{when} · {src}`")
            L.append("")
        if not rows:
            L.append("_No open tasks._")

        (OUT / f"{pid}.md").write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")
        written.append((pid, pr.get("notion_page_id", ""), len(rows)))

    for pid, page, n in sorted(written, key=lambda r: -r[2]):
        print(f"{pid}\t{page}\t{n}")
    print(f"# {len(written)} pages -> /tmp/pages/", flush=True)


if __name__ == "__main__":
    main()
