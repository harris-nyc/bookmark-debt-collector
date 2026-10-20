"""Weekly resurfacing: pick 3 open bookmarks and ask do it / snooze / archive.

Ranking is a tiny recsys:
  score = w(category) * debt(age) * quality(save-rate) * alive
  debt(age)  = min(1, log1p(age_days) / log1p(365))  (older unpaid debt ranks higher)
  quality    = percentile of bookmark_count / impression_count among your bookmarks
               ("how often other people who saw this also saved it")
Then a greedy MMR re-rank (lambda=0.5) so the 3 picks don't share a theme or author.
Decisions live in state.json; snoozed items come back after N days, done/archived never do.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAT_WEIGHT = {"Install/Try": 1.0, "Follow up": 1.0, "Learn": 0.9, "Read": 0.8, "Archive": 0.0}


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"decisions": {}, "known_ids": [], "last_resurfaced": [], "reads": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1))


def _open(pid: str, state: dict, now: datetime) -> bool:
    d = state["decisions"].get(pid)
    if not d:
        return True
    if d["action"] == "snooze":
        return datetime.fromisoformat(d["until"]) <= now
    return False


def pick(records, tri, fresh, themes_by_id, state, n=3, lam=0.5, now=None, exclude_private=None):
    now = now or datetime.now(timezone.utc)
    fr = {f["id"]: f for f in fresh}
    rates = {}
    for r in records:
        m = r.get("metrics") or {}
        if m.get("impression_count"):
            rates[r["id"]] = (m.get("bookmark_count") or 0) / m["impression_count"]
    ordered = sorted(rates.values())
    pct = {pid: (ordered.index(v) + 1) / len(ordered) for pid, v in rates.items()} if ordered else {}

    cands = []
    for r in records:
        pid = r["id"]
        cat = tri[pid]["category"]
        if CAT_WEIGHT.get(cat, 0) == 0 or not _open(pid, state, now):
            continue
        if exclude_private and exclude_private(r):
            continue
        age = fr[pid]["age_days"]
        debt = min(1.0, math.log1p(age) / math.log1p(365))
        quality = 0.5 + 0.5 * pct.get(pid, 0.5)
        alive = 0.3 if fr[pid]["status"] == "broken" else 1.0
        s = CAT_WEIGHT[cat] * (0.25 + debt) * quality * alive
        cands.append((s, r))
    cands.sort(key=lambda x: -x[0])

    chosen = []
    while cands and len(chosen) < n:
        def mmr(c):
            s, r = c
            sim = 0.0
            for _, q in chosen:
                same_theme = themes_by_id.get(r["id"]) == themes_by_id.get(q["id"])
                same_author = r["author_username"] == q["author_username"]
                same_cat = tri[r["id"]]["category"] == tri[q["id"]]["category"]
                sim = max(sim, 0.4 * same_theme + 0.2 * same_author + 0.4 * same_cat)
            return lam * s - (1 - lam) * sim
        best = max(cands, key=mmr)
        chosen.append(best)
        cands.remove(best)
    return [r for _, r in chosen]


def message(picks, tri, fresh, handle: str | None = None) -> str:
    from .normalize import clean_text
    fr = {f["id"]: f for f in fresh}
    lines = [f"## Bookmark debt: 3 from the graveyard this week{' for @' + handle if handle else ''}", ""]
    for i, r in enumerate(picks, 1):
        t = tri[r["id"]]
        f = fr[r["id"]]
        hook = clean_text(r["text"])
        q = next((clean_text(x["text"]) for x in r.get("quoted", []) if x.get("text")), "")
        if len(hook) < 60 and q:
            hook = f"{hook} ↳ {q}"
        hook = hook[:140] + "…" if len(hook) > 140 else hook
        lines += [
            f"**{i}. [{t['category']}] @{r['author_username']}** · saved post from {r['created_at'][:10]} · {int(f['age_days'])} days old · {f['status']}",
            f"> {hook}",
            f"Next action: {t['next_action']}",
            f"{r['url']}",
        ]
        if f["issues"] or f["notes"]:
            lines.append("Heads up: " + "; ".join(f["issues"] + f["notes"]))
        lines.append("")
    lines += ["Reply with e.g. `do 1`, `snooze 2` (2 weeks) or `archive 3`.", ""]
    return "\n".join(lines)


def decide(state: dict, ref: str, action: str, days: int = 14, now=None) -> str:
    now = now or datetime.now(timezone.utc)
    pid = ref
    if ref.isdigit() and len(ref) < 3:
        idx = int(ref) - 1
        if not 0 <= idx < len(state.get("last_resurfaced", [])):
            raise SystemExit(f"no item #{ref} in the last resurfacing")
        pid = state["last_resurfaced"][idx]
    action = {"do": "done", "done": "done", "snooze": "snooze", "archive": "archive"}[action]
    d = {"action": action, "at": now.isoformat()}
    if action == "snooze":
        d["until"] = (now + timedelta(days=days)).isoformat()
    state["decisions"][pid] = d
    return pid
