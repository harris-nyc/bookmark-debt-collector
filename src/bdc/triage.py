"""Action triage: every bookmark gets one bucket and one concrete next action.

Buckets: Install/Try, Read, Learn, Follow up, Archive.

This module is the deterministic, offline baseline. Inside Grok Bot the
bookmark-triage skill has the model review these suggestions and write
overrides (better next actions, corrected buckets) to triage_overrides.json,
which `apply_overrides` merges back in. Overrides win.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .normalize import arxiv_ids, clean_text, github_repos

CATEGORIES = ["Install/Try", "Read", "Learn", "Follow up", "Archive"]

TRY_RE = re.compile(r"\b(pip install|npm i|brew install|open[- ]sourced?|github|repo|plugin|template|try it|"
                    r"demo|released?|launch(?:ed)?|install|cli|sdk|api is live|now available|beta|waitlist)\b", re.I)
LEARN_RE = re.compile(r"\b(how to|guide|tutorial|course|lessons?|playbook|framework|ways to|tips|techniques?|"
                      r"routine|protocol|cheat ?sheet|step[- ]by[- ]step|explained|learn|masterclass|handbook)\b", re.I)
READ_RE = re.compile(r"\b(deep dive|article|paper|essay|thread|blog|report|analysis|write-?up|long read|"
                     r"worth reading|must read|read this)\b", re.I)
FOLLOW_RE = re.compile(r"\b(dm me|dms|group chat|meetup|hiring|we're hiring|reach out|ping me|coffee|"
                       r"accounts to follow|follow @|who to follow|intro|collab)\b", re.I)
NUMBERED_RE = re.compile(r"(?m)^\s*(?:\d+[.)]|[-•→])\s+\S")


def _first_line(text: str, n: int = 80) -> str:
    t = clean_text(text)
    t = re.split(r"(?<=[A-Za-z)\"'][.!?])\s", t, maxsplit=1)[0]
    return (t[: n - 1] + "…") if len(t) > n else t


def read_minutes(rec: dict) -> int:
    words = len(clean_text(rec["text"]).split()) + sum(len((q.get("text") or "").split()) for q in rec["quoted"])
    return max(1, round(words / 230))


def _short_url(url: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    return u if len(u) <= 48 else u[:47] + "…"


def triage_one(rec: dict, me: str | None = None) -> dict:
    text = rec["text"]
    t = clean_text(text)
    who = "@" + rec["author_username"]
    repos, papers = github_repos(rec), arxiv_ids(rec)
    kinds = {l["kind"] for l in rec["links"]}
    web = [l for l in rec["links"] if l["kind"] in ("web", "x_article", "video")]
    long_form = len(t) > 700 or "x_article" in kinds
    mentions_me = bool(me) and me.lower().lstrip("@") in [m.lower() for m in rec.get("mentions", [])]
    hook = _first_line(text)
    strong_learn = re.search(r"\b(how to|guide|tutorial|course|step[- ]by[- ]step|playbook|\d+ tips|\d+ ways)\b", t, re.I)

    if rec.get("is_self"):
        return {"category": "Archive", "reason": "your own post",
                "next_action": "Your own post. Unbookmark it, or recycle the idea into a longer thread."}
    if mentions_me:
        return {"category": "Follow up", "reason": "mentions you",
                "next_action": f"Reply to {who}: they mentioned you and asked for something."}
    if FOLLOW_RE.search(t):
        return {"category": "Follow up", "reason": "people / community signal",
                "next_action": f"Act on the people part: follow, join or DM {who} (5 min)."}
    if strong_learn and not repos and not papers:
        target = f" ({_short_url(web[0]['url'])})" if web else ""
        return {"category": "Learn", "reason": "how-to / guide",
                "next_action": f"Do one thing from this guide{target} this week: “{_first_line(text, 60)}”"}
    if repos or "grok_bot" in kinds or "huggingface" in kinds or (TRY_RE.search(t) and rec["links"]):
        if repos:
            target = repos[0]
        else:
            l = rec["links"][0]
            target = l.get("title") or _short_url(l["url"])
        verb = "Clone and run" if repos else "Try"
        return {"category": "Install/Try", "reason": "links to something runnable",
                "next_action": f"{verb} {target} for 15 min; keep it or archive it."}
    if papers:
        return {"category": "Read", "reason": "paper",
                "next_action": f"Read the abstract + figures of arXiv {papers[0]} (20 min), then go deeper or archive."}
    if LEARN_RE.search(t) and (NUMBERED_RE.search(text) or len(t) > 140 or rec["links"]):
        return {"category": "Learn", "reason": "how-to / guide",
                "next_action": f"Pick one tip from {who} and do it this week: “{_first_line(text, 60)}”"}
    if web and (READ_RE.search(t) or long_form or len(t) > 80):
        return {"category": "Read", "reason": "linked article",
                "next_action": f"Read the linked piece ({_short_url(web[0]['url'])}), then write a one-line takeaway or archive."}
    if long_form or READ_RE.search(t):
        return {"category": "Read", "reason": "long-form",
                "next_action": f"Read it ({read_minutes(rec)} min{' incl. quoted post' if any(q.get('text') for q in rec['quoted']) else ''}), then write a one-line takeaway or archive."}
    return {"category": "Archive", "reason": "short take / news",
            "next_action": f"Skim once (“{hook}”) and unbookmark. Nothing to do."}


def triage(records: list[dict], me: str | None = None) -> dict[str, dict]:
    out = {r["id"]: triage_one(r, me) for r in records}
    # Cross-bookmark signals: if one of *your* bookmarked posts quotes/replies to another
    # bookmark, you already acted on it. If a bookmark quotes *you*, it's a follow-up.
    acted = {}
    for r in records:
        if r.get("is_self"):
            for q in r["quoted"]:
                acted.setdefault(q["id"], r["created_at"][:10])
    for r in records:
        if r["is_self"]:
            continue
        if r["id"] in acted:
            out[r["id"]] = {"category": "Archive", "reason": "already acted on",
                            "next_action": f"Done already: you quoted/replied to this on {acted[r['id']]}. Unbookmark it."}
        elif me and any((q.get("author") or "").lower() == me.lower().lstrip("@") for q in r["quoted"]) \
                and out[r["id"]]["category"] == "Archive":
            out[r["id"]] = {"category": "Follow up", "reason": "quotes you",
                            "next_action": f"@{r['author_username']} quoted your post. Reply with one concrete addition."}
    return out


def apply_overrides(tri: dict[str, dict], path: str | Path | None) -> dict[str, dict]:
    if not path or not Path(path).exists():
        return tri
    ov = json.loads(Path(path).read_text())
    for pid, o in ov.items():
        if pid in tri:
            if o.get("category") and o["category"] not in CATEGORIES:
                raise ValueError(f"override for {pid}: unknown category {o['category']!r}")
            tri[pid] = {**tri[pid], **o, "source": "reviewed"}
    return tri


def adjust_for_freshness(tri: dict[str, dict], fresh: list[dict]) -> int:
    """Rewrite rule-based actions that point at something dead. Reviewed items keep
    their (human/model) action but get the warning appended. Returns #changed."""
    changed = 0
    for f in fresh:
        t = tri[f["id"]]
        if not f["issues"] or t["category"] == "Archive":
            continue
        msg = "; ".join(f["issues"])
        if t.get("source") == "reviewed":
            if msg not in t["next_action"]:
                t["next_action"] += f" (Heads up: {msg}.)"
            continue
        repo_archived = any(i.startswith("repo archived") for i in f["issues"])
        if repo_archived and len(f["issues"]) == 1:
            t["next_action"] = f"The repo was archived ({msg.split(': ', 1)[1]}). Read the code for reference only, or archive."
        else:
            t.update(category="Archive", reason="dead", next_action=f"It's gone ({msg}). Unbookmark it.")
        changed += 1
    return changed
