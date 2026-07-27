#!/usr/bin/env python3
"""Shared helpers for daily-pulse: project canonicalization, semantic dedup,
noise suppression, confidence normalization, and aging/archive.
Both merge.py (ongoing scans) and cleanup.py (one-time backlog fix) use this."""
import re
from datetime import date

STOP = set((
    "the a an to and or of for with on in at by from into as is are be been being "
    "do does send check make making plan planning hold get set up update updating "
    "review reviewing new so that this these those his her their your our we you i "
    "will need needs should can via re about it its per each all any"
).split())


def toks(s):
    return {w for w in re.sub(r"\W+", " ", (s or "").lower()).split()
            if len(w) > 2 and w not in STOP}


def jacc(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def valid_projects(cfg):
    v = {p["id"] for p in cfg["projects"]}
    v.add("inbox")
    return v


def canon_project(cfg, pid):
    v = valid_projects(cfg)
    aliases = cfg.get("project_aliases", {})
    pid = (pid or "inbox").strip()
    if pid in v:
        return pid
    if pid in aliases and aliases[pid] in v:
        return aliases[pid]
    return "inbox"


def norm_confidence(c):
    if isinstance(c, bool):
        return "medium"
    if isinstance(c, (int, float)):
        if c >= 0.8:
            return "high"
        if c < 0.5:
            return "low"
        return "medium"
    if c in ("high", "medium", "low"):
        return c
    return "medium"


def is_dismissed(cfg, text):
    tl = (text or "").lower()
    for pat in cfg.get("dismissed_patterns", []):
        if pat.lower() in tl:
            return True
    return False


def _days_between(iso, today):
    try:
        d = date.fromisoformat((iso or "")[:10])
        return (today - d).days
    except Exception:
        return None


def age_tasks(tasks, overrides, aging_days, today=None):
    if today is None:
        today = date.today()
    n_arch = n_react = 0
    for t in tasks:
        tid = t.get("id")
        touched = tid in overrides
        t.setdefault("status", "open")
        age = _days_between(t.get("first_seen") or t.get("date"), today)
        if touched:
            if t["status"] == "archived":
                t["status"] = "open"
                t.pop("archived_on", None)
                n_react += 1
            continue
        if t["status"] != "archived" and age is not None and age > aging_days:
            t["status"] = "archived"
            t["archived_on"] = str(today)
            n_arch += 1
    return n_arch, n_react


def collapse_dups(tasks, overrides, threshold=0.7):
    n = len(tasks)
    tk = [toks(t.get("text", "")) for t in tasks]
    inv = {}
    for i, ts in enumerate(tk):
        for w in ts:
            inv.setdefault(w, []).append(i)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    checked = set()
    for w, idxs in inv.items():
        if len(idxs) > 80:
            continue
        for a in range(len(idxs)):
            ia = idxs[a]
            for b in range(a + 1, len(idxs)):
                ib = idxs[b]
                key = (ia, ib)
                if key in checked:
                    continue
                checked.add(key)
                if jacc(tk[ia], tk[ib]) >= threshold:
                    union(ia, ib)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    kept = []
    removed = 0
    for members in groups.values():
        if len(members) == 1:
            kept.append(tasks[members[0]])
            continue

        def sort_key(i):
            t = tasks[i]
            in_ov = 0 if t.get("id") in overrides else 1
            fs = t.get("first_seen") or t.get("date") or "9999-99-99"
            return (in_ov, fs)
        members.sort(key=sort_key)
        surv = tasks[members[0]]
        all_dates = [tasks[i].get("date", "") for i in members if tasks[i].get("date")]
        first_seens = [x for x in (tasks[i].get("first_seen") or tasks[i].get("date") or "" for i in members) if x]
        last_seens = [x for x in (tasks[i].get("last_seen") or tasks[i].get("date") or "" for i in members) if x]
        longest = max((tasks[i] for i in members), key=lambda t: len(t.get("text", "")))
        surv["text"] = longest.get("text", surv.get("text", ""))
        if all_dates:
            surv["date"] = max(all_dates)
        if first_seens:
            surv["first_seen"] = min(first_seens)
        if last_seens:
            surv["last_seen"] = max(last_seens)
        if any(norm_confidence(tasks[i].get("confidence")) == "high" for i in members):
            surv["confidence"] = "high"
        for i in members[1:]:
            oid = tasks[i].get("id")
            if oid in overrides and surv.get("id") not in overrides:
                surv["project"] = overrides[oid]
        surv.setdefault("extras", {})["merged_count"] = len(members)
        kept.append(surv)
        removed += len(members) - 1
    return kept, removed


def build_output(cfg, tasks):
    active = [t for t in tasks if t.get("status", "open") != "archived"]
    archived = [t for t in tasks if t.get("status") == "archived"]
    return {
        "generated_at": str(date.today()),
        "schema_version": 3,
        "total": len(active),
        "active_count": len(active),
        "archived_count": len(archived),
        "projects": [{"id": p["id"], "name": p["name"], "tier": p.get("tier", "medium")}
                     for p in cfg["projects"]],
        "tasks": tasks,
    }
