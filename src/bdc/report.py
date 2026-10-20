"""Markdown outputs: the triaged action list and the freshness report."""
from __future__ import annotations

from .normalize import clean_text
from .triage import CATEGORIES

BADGE = {"fresh": "🟢 fresh", "aging": "🟡 aging", "stale": "🟠 stale", "broken": "🔴 broken"}
ORDER = ["Install/Try", "Follow up", "Learn", "Read", "Archive"]


def _hook(r, n=150):
    t = clean_text(r["text"])
    q = next((clean_text(x["text"]) for x in r.get("quoted", []) if x.get("text")), "")
    if len(t) < 60 and q:
        t = f"{t} ↳ {q}"
    return t[: n - 1] + "…" if len(t) > n else t


def actions_md(records, tri, fresh, themes_by_id=None, theme_names=None, public=False, is_private=None, handle=None,
               hidden_themes=None):
    fr = {f["id"]: f for f in fresh}
    themes_by_id = themes_by_id or {}
    theme_names = theme_names or {}
    counts = {c: sum(1 for r in records if tri[r["id"]]["category"] == c) for c in CATEGORIES}
    out = [f"# Bookmark debt{' for @' + handle if handle else ''}", "",
           f"{len(records)} bookmarks → {sum(v for k, v in counts.items() if k != 'Archive')} open actions. "
           + " · ".join(f"{c}: {counts[c]}" for c in ORDER), ""]
    hidden = 0
    for cat in ORDER:
        items = [r for r in records if tri[r["id"]]["category"] == cat]
        if not items:
            continue
        out += [f"## {cat} ({len(items)})", ""]
        # oldest debt first within each bucket, except Archive (newest first is fine)
        items.sort(key=lambda r: r["created_at"], reverse=(cat == "Archive"))
        for r in items:
            t, f = tri[r["id"]], fr[r["id"]]
            if public and is_private and is_private(r):
                hidden += 1
                continue
            tid = str(themes_by_id.get(r["id"]))
            theme = "" if public and tid in (hidden_themes or {}) else theme_names.get(tid, "")
            meta = f"@{r['author_username']} · {r['created_at'][:10]} · {BADGE.get(f['status'], f['status'])}"
            if theme and not theme.startswith("_"):
                meta += f" · {theme}"
            out.append(f"- [ ] **{t['next_action']}**  ")
            out.append(f"  {meta} · [post]({r['url']})  ")
            out.append(f"  > {_hook(r)}")
            extra = f["issues"] + f["notes"]
            if extra:
                out.append(f"  ⚠️ {'; '.join(extra)}")
            out.append("")
    if hidden:
        out += [f"_{hidden} private-topic item(s) hidden from this public view._", ""]
    return "\n".join(out)


def freshness_md(records, fresh, summary, is_private=None):
    """Freshness report. Totals count everything; rows for private-topic bookmarks are withheld
    (freshness.json keeps the full detail for you)."""
    by = {r["id"]: r for r in records}
    shown = [f for f in fresh if not (is_private and is_private(by[f["id"]]))]
    n_hidden = len(fresh) - len(shown)
    out = ["# Freshness check", "",
           f"- Bookmarks: {summary['total']}",
           f"- Status: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["by_status"].items())),
           f"- Still fresh: {summary['fresh_pct']}% (alive and younger than its category's half-life)",
           f"- Checks run: {summary['checked']} (links, repos, papers, quoted posts) · dead: {summary['dead']} · archived repos: {summary['archived_repos']} · dormant repos: {summary['dormant_repos']} · unverifiable: {summary['unverifiable']}",
           f"- Bookmarks with updates since saved (new releases, new paper versions, moved repos): {summary['with_updates']}",
           "", "## Broken", ""]
    broken = [f for f in shown if f["status"] == "broken"]
    for f in broken or []:
        out.append(f"- @{by[f['id']]['author_username']} ({by[f['id']]['created_at'][:10]}) {f['url']}: " + "; ".join(f["issues"]))
    n_hidden_broken = summary["by_status"].get("broken", 0) - len(broken)
    if n_hidden_broken > 0:
        out.append(f"- {n_hidden_broken} {'more ' if broken else ''}on private-topic bookmarks (details in freshness.json)")
    elif not broken:
        out.append("- none")
    out += ["", "## Updated since you saved it", ""]
    upd = [f for f in shown if f["notes"]]
    for f in upd:
        out.append(f"- {f['url']}: " + "; ".join(f["notes"]))
    if not upd:
        out.append("- none")
    out += ["", "## All checks", "", "| post | type | target | state | detail |", "|---|---|---|---|---|"]
    for f in shown:
        for c in f["checks"]:
            target = c.get("url") or c.get("repo") or c.get("arxiv") or c.get("id")
            detail = c.get("note") or c.get("http") or c.get("x_status") or ""
            if c["type"] == "github":
                detail = f"★{c.get('stars')} · pushed {c.get('days_since_push')}d ago · latest {c.get('latest_release') or '-'}"
            if c["type"] == "arxiv":
                detail = f"{c.get('latest_version')} · updated {str(c.get('updated'))[:10]}"
            out.append(f"| [{f['id']}]({f['url']}) | {c['type']} | {target} | {c['state']} | {detail} |")
    if n_hidden:
        out += ["", f"_{n_hidden} private-topic bookmark(s) left out of this report; they still count in the totals above._"]
    return "\n".join(out) + "\n"
