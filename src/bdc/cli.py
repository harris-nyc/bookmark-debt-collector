"""bdc: Bookmark Debt Collector command line.

  bdc run      --input bookmarks.json --out out/ [--me handle]   full pipeline
  bdc ingest   page-1.txt [page-2.txt ...]                       merge saved X plugin pages (Grok Bot path)
  bdc pull     --user-id ID --archive archive.json               pull via X API (X_USER_TOKEN), only what's new
  bdc resurface --out out/ --state state.json                    pick this week's 3
  bdc decide   --state state.json 2 snooze                       record do/snooze/archive
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import cluster, freshness, normalize, privacy, report, resurface, triage, wrapped


def log(msg):
    print(msg, flush=True)


def _load_json(p):
    return json.loads(Path(p).read_text()) if p and Path(p).exists() else {}


def cmd_run(a):
    t0 = time.time()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now else datetime.now(timezone.utc)
    extra_private = [k.strip() for k in (a.private_keywords or "").split(",") if k.strip()]

    log(f"▸ loading {a.input}")
    if not Path(a.input).exists():
        sys.exit(f"{a.input} not found. pull bookmarks first (bdc ingest <saved page>), see BOT.md")
    recs = normalize.load(a.input, a.me)
    if not recs:
        sys.exit("no bookmarks in the input, nothing to triage. (X returned an empty list: bookmark a few posts first)")
    (out / "bookmarks.normalized.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False))
    n_links = sum(len(r["links"]) for r in recs)
    n_quotes = sum(len(r["quoted"]) for r in recs)
    log(f"  {len(recs)} bookmarks · {len({r['author_username'] for r in recs})} authors · {n_links} outbound links · {n_quotes} quoted/replied posts")

    log("▸ triage (rules → reviewed overrides)")
    tri = triage.triage(recs, a.me)
    tri = triage.apply_overrides(tri, a.overrides)
    reviewed = sum(1 for v in tri.values() if v.get("source") == "reviewed")
    cats = {c: sum(1 for v in tri.values() if v["category"] == c) for c in triage.CATEGORIES}
    log("  " + " · ".join(f"{c} {n}" for c, n in cats.items()) + (f"  ({reviewed} reviewed)" if reviewed else ""))
    (out / "triage.json").write_text(json.dumps(tri, indent=1, ensure_ascii=False))

    log("▸ clustering themes")
    cl = cluster.discover(recs, seed=a.seed, backend=a.cluster_backend, k=a.k)
    name_cfg = _load_json(a.theme_names)
    names = cluster.resolve_names(cl["themes"], name_cfg)
    themes_by_id = {}
    for t in cl["themes"]:
        for pid in t["members"]:
            themes_by_id[pid] = t["id"]
    hide = list(name_cfg.get("_hide", [])) + [h.strip() for h in (a.hide_themes or "").split(",") if h.strip()]
    is_private = privacy.PrivacyFilter(recs, extra_private, cl["themes"], names, hide_themes=hide,
                                       theme_share=a.sensitive_theme_share)
    hidden = is_private.hidden_themes
    log(f"  {cl['method']}")
    for t in cl["themes"]:
        nm = names.get(str(t["id"]))
        if str(t["id"]) in hidden:   # never print a hidden theme's name: terminal output gets screenshotted
            nm = "_hidden"
        log(f"   [{t['size']:>2}] {' · '.join(t['terms'][:5])}" + (f"  → “{nm}”" if nm and not nm.startswith(' · '.join(t['terms'][:3])) else ""))
    if hidden:
        log(f"  {len(hidden)} theme(s) kept off the card and public outputs (sensitive)")
    for t in cl["themes"]:
        t["name"] = names[str(t["id"])]
        t["hidden"] = str(t["id"]) in hidden
    (out / "themes.json").write_text(json.dumps({k: v for k, v in cl.items() if k != "vectors"}, indent=1))

    log("▸ freshness check" + (" (offline)" if a.offline else ""))
    fr = freshness.run(recs, {k: v["category"] for k, v in tri.items()}, Path(a.cache) if a.cache else out / ".cache.json",
                       offline=a.offline, ref_time=now)
    fs = freshness.summarize(fr)
    n_adj = triage.adjust_for_freshness(tri, fr)
    if n_adj:
        log(f"  re-triaged {n_adj} bookmark(s) that point at dead or archived things")
        for f in fr:
            f["category"] = tri[f["id"]]["category"]
        (out / "triage.json").write_text(json.dumps(tri, indent=1, ensure_ascii=False))
    (out / "freshness.json").write_text(json.dumps({"summary": fs, "results": fr}, indent=1))
    (out / "freshness.md").write_text(report.freshness_md(recs, fr, fs, is_private=is_private))
    log(f"  {fs['checked']} checks · {fs['dead']} dead · {fs['unverifiable']} unverifiable · "
        + " · ".join(f"{k} {v}" for k, v in sorted(fs['by_status'].items())) + f" → {fs['fresh_pct']}% fresh")

    log("▸ writing action list")
    (out / "actions.md").write_text(report.actions_md(recs, tri, fr, themes_by_id, names, handle=a.me))
    (out / "actions.public.md").write_text(report.actions_md(recs, tri, fr, themes_by_id, names, public=True, is_private=is_private,
                                                             handle=a.me, hidden_themes=hidden))
    (out / "privacy.json").write_text(json.dumps(is_private.to_json(), indent=1, ensure_ascii=False))
    log(f"  {len(is_private.reasons)} private-topic bookmark(s) kept off public outputs (reasons in privacy.json)")

    log("▸ Bookmark Wrapped")
    state_path = Path(a.state) if a.state else out / "state.json"
    st = resurface.load_state(state_path)
    stats = wrapped.compute(recs, tri, fr, fs, cl, names, handle=a.me, is_private=is_private, now=now,
                            decided=st["decisions"].keys(), hidden_themes=hidden)
    (out / "wrapped.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False))
    html = wrapped.render_html(stats)
    (out / "card.html").write_text(html)
    png_failed = None
    if not a.no_png:
        try:
            wrapped.render_png(html, out / "card@1x.png", scale=1)
            wrapped.render_png(html, out / "card.png", scale=2)
            log(f"  wrote {out/'card@1x.png'} (1200x675) and card.png (2400x1350)")
        except RuntimeError as e:
            png_failed = str(e)
            log("  ✗ " + png_failed)

    log("▸ weekly resurface preview")
    picks = resurface.pick(recs, tri, fr, themes_by_id, st, now=now, exclude_private=is_private)
    msg = resurface.message(picks, tri, fr, a.me)
    (out / "resurface.md").write_text(msg)
    st["last_resurfaced"] = [r["id"] for r in picks]
    st["known_ids"] = sorted({*st.get("known_ids", []), *[r["id"] for r in recs]})
    resurface.save_state(state_path, st)
    for i, r in enumerate(picks, 1):
        log(f"  {i}. [{tri[r['id']]['category']}] @{r['author_username']}: {tri[r['id']]['next_action'][:80]}")
    if png_failed:
        log(f"✗ finished in {time.time()-t0:.1f}s but card.png is missing (see above) → {out}/")
        return 3
    log(f"✓ done in {time.time()-t0:.1f}s → {out}/")
    return 0


def cmd_ingest(a):
    """Merge raw get_users_bookmarks results (one file per page, any wrapper) into the
    archive, then say exactly what to do next: fetch the next page, or stop."""
    fetch = normalize_fetch()
    arch = Path(a.archive)
    files = list(a.files or []) + ([a.input] if a.input else [])
    if not files:
        sys.exit("give one or more saved get_users_bookmarks results: bdc ingest private/pulls/page-1.txt")
    old = json.loads(arch.read_text()) if arch.exists() else []
    old = old if isinstance(old, list) else [old]
    known_before = {p["id"] for pg in old for p in pg.get("data", [])}
    pages = []
    for f in files:
        got = fetch.extract_pages(Path(f).read_text(encoding="utf-8", errors="replace"))
        if not got:
            sys.exit(f"{f}: no bookmarks page found (expected the JSON that get_users_bookmarks returns, "
                     f'with "data" and usually "includes" and "meta")')
        pages.extend(got)
    _, n_new = fetch.merge_archive(arch, pages)
    returned = sum(len(pg.get("data", [])) for pg in pages)
    hit_known = any(p["id"] in known_before for pg in pages for p in pg.get("data", []))
    total = len(known_before) + n_new
    next_token = (pages[-1].get("meta") or {}).get("next_token")
    log(f"ingested {len(pages)} page(s): {returned} returned, {n_new} new, {returned - n_new} already known")
    log(f"archive: {total} bookmarks in {arch}")
    if hit_known:
        log("NEXT: stop paging, you've reached bookmarks you already have")
    elif next_token:
        log(f"NEXT: call get_users_bookmarks again with pagination_token={next_token}")
    else:
        log("NEXT: done, that was the last page")
    return 0


def normalize_fetch():
    from . import fetch
    return fetch


def cmd_pull(a):
    fetch = normalize_fetch()
    token = os.environ.get("X_USER_TOKEN")
    if not token:
        sys.exit("set X_USER_TOKEN to an OAuth 2.0 user token with bookmark.read + tweet.read + users.read")
    arch = Path(a.archive)
    old = json.loads(arch.read_text()) if arch.exists() else []
    known = {p["id"] for pg in (old if isinstance(old, list) else [old]) for p in pg.get("data", [])}
    pages, stats = fetch.pull(a.user_id, token, known, probe=a.probe)
    _, n_new = fetch.merge_archive(arch, pages)
    log(f"pulled {stats['returned']} posts ({n_new} new)")
    return 0


def cmd_resurface(a):
    out = Path(a.out)
    recs = json.loads((out / "bookmarks.normalized.json").read_text())
    tri = json.loads((out / "triage.json").read_text())
    fr = json.loads((out / "freshness.json").read_text())["results"]
    th = json.loads((out / "themes.json").read_text())
    themes_by_id = {pid: t["id"] for t in th["themes"] for pid in t["members"]}
    st = resurface.load_state(Path(a.state))
    picks = resurface.pick(recs, tri, fr, themes_by_id, st, n=a.n, exclude_private=privacy.load_for_run(out, recs))
    st["last_resurfaced"] = [r["id"] for r in picks]
    resurface.save_state(Path(a.state), st)
    print(resurface.message(picks, tri, fr, a.me))
    return 0


def cmd_decide(a):
    st = resurface.load_state(Path(a.state))
    pid = resurface.decide(st, a.ref, a.action, a.days)
    resurface.save_state(Path(a.state), st)
    log(f"{pid}: {st['decisions'][pid]}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="bdc", description="Bookmark Debt Collector")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="full pipeline")
    r.add_argument("--input", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--me", help="your X handle (marks self-bookmarks and mentions)")
    r.add_argument("--overrides", help="triage_overrides.json from the bot's review pass")
    r.add_argument("--theme-names", help="theme_names.json mapping cluster id -> name")
    r.add_argument("--private-keywords", help="comma-separated extra keywords to keep off public outputs")
    r.add_argument("--hide-themes", help="comma-separated theme names, ids or term:<word> to keep off the card "
                                        "(same as \"_hide\" in theme_names.json)")
    r.add_argument("--sensitive-theme-share", type=float, default=privacy.DEFAULT_THEME_SHARE,
                   help="hide a theme when this share of its posts are private-topic (0 = off; default %(default)s)")
    r.add_argument("--state", help="state.json (decisions, known ids)")
    r.add_argument("--cache", help="freshness cache path")
    r.add_argument("--offline", action="store_true", help="skip network; use X unfurl hints + cache")
    r.add_argument("--no-png", action="store_true")
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--cluster-backend", choices=["auto", "embed", "tfidf"], default="auto")
    r.add_argument("--k", type=int, help="force number of themes (default: pick by silhouette)")
    r.add_argument("--now", help="ISO timestamp to compute ages against (reproducible runs)")
    r.set_defaults(fn=cmd_run)
    i = sub.add_parser("ingest", help="merge saved get_users_bookmarks results into the archive (Grok Bot path)")
    i.add_argument("files", nargs="*", help="saved tool results, one per page, in order")
    i.add_argument("--input", help="(older spelling) a single saved page")
    i.add_argument("--archive", default="private/archive.json", help="default: %(default)s")
    i.set_defaults(fn=cmd_ingest)
    pl = sub.add_parser("pull", help="pull bookmarks with your own X API token")
    pl.add_argument("--user-id", required=True)
    pl.add_argument("--archive", required=True)
    pl.add_argument("--probe", type=int, default=10)
    pl.set_defaults(fn=cmd_pull)
    rs = sub.add_parser("resurface", help="pick this week's items")
    rs.add_argument("--out", required=True)
    rs.add_argument("--state", required=True)
    rs.add_argument("--me")
    rs.add_argument("-n", type=int, default=3)
    rs.set_defaults(fn=cmd_resurface)
    d = sub.add_parser("decide", help="record a decision")
    d.add_argument("--state", required=True)
    d.add_argument("ref", help="item number from the last resurfacing (1-3) or a post id")
    d.add_argument("action", choices=["do", "done", "snooze", "archive"])
    d.add_argument("--days", type=int, default=14)
    d.set_defaults(fn=cmd_decide)
    a = p.parse_args(argv)
    return a.fn(a)
