"""Bookmark Wrapped: real stats -> HTML card -> PNG (headless Chrome/Chromium, via Playwright or directly)."""
from __future__ import annotations

import html
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .normalize import clean_text
from .triage import CATEGORIES

CAT_COLORS = {"Install/Try": "#34d399", "Read": "#60a5fa", "Learn": "#c084fc", "Follow up": "#fbbf24", "Archive": "#64748b"}


def skill_label(text: str, max_len: int = 26) -> str:
    """Short chip label for a Learn bookmark when no reviewed `skill` exists."""
    import re
    t = clean_text(text)
    m = re.match(r"\s*([^:.!?]{4,60}?)\s*[:.!?]", t)
    lab = m.group(1) if m else " ".join(t.split()[:5])
    lab = re.sub(r"^(here are|here's|the)\s+", "", lab, flags=re.I)
    words, out = lab.split(), ""
    for w in words:
        if len(out) + len(w) + 1 > max_len:
            break
        out = f"{out} {w}".strip()
    return (out or lab[:max_len]).rstrip(",;-–")


def _d(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def compute(records, tri, fresh_results, fresh_summary, clusters, theme_names=None, skills=None,
            handle=None, is_private=lambda r: False, now=None, decided=None, hidden_themes=None) -> dict:
    now = now or datetime.now(timezone.utc)
    theme_names = theme_names or {}
    dates = sorted(_d(r["created_at"]) for r in records if r.get("created_at"))
    cats = Counter(tri[r["id"]]["category"] for r in records)
    self_count = sum(1 for r in records if r["is_self"])
    open_actions = sum(v for k, v in cats.items() if k != "Archive")

    themes = []
    hidden_themes = hidden_themes or {}
    n_hidden_themes = 0
    for t in clusters["themes"]:
        name = theme_names.get(str(t["id"])) or " · ".join(t["terms"][:3]) or "misc"
        # sensitive themes (privacy.sensitive_themes: "_" names, "_hide", sensitive words, mostly private posts)
        if name.startswith("_") or str(t["id"]) in hidden_themes:
            n_hidden_themes += 1
            continue
        themes.append({"name": name, "size": t["size"], "terms": t["terms"]})

    public = [r for r in records if not is_private(r)]
    # highlights (authors, oldest, skills) come from public items only; totals count everything
    authors = Counter(r["author_username"] for r in public if not r["is_self"])
    decided = set(decided or [])
    oldest = min((r for r in public if not r["is_self"] and r["id"] not in decided), key=lambda r: r["created_at"], default=None)

    fr = {f["id"]: f for f in fresh_results}
    learn = [r for r in public if tri[r["id"]]["category"] == "Learn"]
    skill_list = []
    for r in sorted(learn, key=lambda r: r["created_at"]):
        label = tri[r["id"]].get("skill") or (skills or {}).get(r["id"])
        if not label:
            label = skill_label(r["text"])
        if label not in skill_list:
            skill_list.append(label)

    return {
        "handle": handle,
        "generated_at": now.isoformat(),
        "total": len(records),
        "first": dates[0].isoformat() if dates else None,
        "last": dates[-1].isoformat() if dates else None,
        "span_days": (dates[-1] - dates[0]).days if dates else 0,
        "self_bookmarks": self_count,
        "unique_authors": len(set(r["author_username"] for r in records)),
        "top_authors": authors.most_common(3),
        "categories": {c: cats.get(c, 0) for c in CATEGORIES},
        "open_actions": open_actions,
        "fresh_pct": fresh_summary["fresh_pct"],
        "by_status": fresh_summary["by_status"],
        "links_checked": fresh_summary["checked"],
        "dead": fresh_summary["dead"],
        "unverifiable": fresh_summary["unverifiable"],
        "themes": themes,
        "hidden_themes": n_hidden_themes,
        "oldest": None if not oldest else {
            "author": oldest["author_username"], "date": oldest["created_at"],
            "age_days": int(fr[oldest["id"]]["age_days"]), "text": clean_text(oldest["text"]), "url": oldest["url"],
        },
        "skills": skill_list,
        "learn_count": cats.get("Learn", 0),
        "cluster_method": clusters.get("method"),
    }


def _fmt_month(iso):
    return _d(iso).strftime("%b %Y")


def render_html(s: dict) -> str:
    e = html.escape
    total = s["total"]
    bar = "".join(
        f'<div class="seg" style="flex:{v};background:{CAT_COLORS[c]}"></div>' for c, v in s["categories"].items() if v)
    legend = "".join(
        f'<span class="lg"><i style="background:{CAT_COLORS[c]}"></i>{e(c)} <b>{v}</b></span>' for c, v in s["categories"].items() if v)
    maxt = max([t["size"] for t in s["themes"]] or [1])
    themes = "".join(
        f'<div class="trow"><div class="tname">{e(t["name"])}</div><div class="tbar"><div style="width:{100*t["size"]/maxt:.0f}%"></div></div><div class="tn">{t["size"]}</div></div>'
        for t in s["themes"][:4])
    short = lambda h: h if len(h) <= 15 else h[:14] + "…"
    authors = "".join(f'<span class="chip">@{e(short(a))} <b>{n}</b></span>' for a, n in s["top_authors"])
    skills = "".join(f'<span class="chip skill">{e(x)}</span>' for x in s["skills"][:3])
    old = s["oldest"]
    oldtxt = ""
    if old:
        t = old["text"]
        t = t[:92].rsplit(" ", 1)[0] + "…" if len(t) > 92 else t
        oldtxt = (f'<div class="old"><div class="olbl">OLDEST UNTOUCHED · {old["age_days"]} DAYS</div>'
                  f'<div class="oq">“{e(t)}”</div><div class="oa">@{e(old["author"])} · {_d(old["date"]).strftime("%b %-d, %Y")}</div></div>')
    handle = f"@{e(s['handle'])}" if s.get("handle") else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:1200px;height:675px;overflow:hidden;font-family:Inter,'Noto Sans',system-ui,sans-serif;color:#e8ecf4;
background:radial-gradient(700px 420px at 8% 0%,rgba(244,63,94,.28),transparent 60%),radial-gradient(800px 500px at 100% 100%,rgba(99,102,241,.30),transparent 60%),#07080d}}
.wrap{{position:absolute;inset:0;padding:40px 46px 34px;display:grid;grid-template-columns:430px 1fr;gap:40px}}
.kicker{{font-size:17px;letter-spacing:.22em;font-weight:800;color:#fb7185}}
.handle{{font-size:20px;color:#94a3b8;margin-top:6px;font-weight:600}}
.big{{font-size:150px;font-weight:900;line-height:.9;letter-spacing:-.05em;margin-top:16px;
background:linear-gradient(90deg,#fff,#fda4af);-webkit-background-clip:text;color:transparent}}
.bigl{{font-size:30px;font-weight:800;margin-top:6px}}
.range{{font-size:20px;color:#94a3b8;margin-top:6px}}
.tiles{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:22px}}
.tile{{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);border-radius:16px;padding:10px 16px}}
.tv{{font-size:42px;font-weight:900;letter-spacing:-.03em;line-height:1.1}}
.tl{{font-size:17px;color:#a5b0c4;font-weight:600;margin-top:2px}}
.green{{color:#34d399}} .amber{{color:#fbbf24}} .red{{color:#fb7185}} .blue{{color:#93c5fd}}
.right{{display:flex;flex-direction:column;gap:18px;min-width:0}}
.h{{font-size:15px;letter-spacing:.18em;font-weight:800;color:#8b95a9;margin-bottom:10px}}
.trow{{display:grid;grid-template-columns:330px 1fr 40px;align-items:center;gap:12px;margin:9px 0}}
.tname{{font-size:23px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tbar{{height:12px;border-radius:8px;background:rgba(255,255,255,.07)}} .tbar div{{height:100%;border-radius:8px;background:linear-gradient(90deg,#f43f5e,#a78bfa)}}
.tn{{font-size:22px;font-weight:800;text-align:right;color:#cbd5e1}}
.chips{{display:flex;flex-wrap:nowrap;gap:10px;overflow:hidden}}
.chip{{font-size:19px;font-weight:600;padding:6px 13px;border-radius:999px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.1);white-space:nowrap}}
.chip b{{color:#fb7185;margin-left:4px}} .skill{{border-color:rgba(192,132,252,.5);color:#e9d5ff}}
.old{{background:linear-gradient(135deg,rgba(244,63,94,.14),rgba(255,255,255,.03));border:1px solid rgba(244,63,94,.35);border-radius:18px;padding:14px 18px}}
.olbl{{font-size:14px;letter-spacing:.18em;font-weight:800;color:#fb7185}}
.oq{{font-size:21px;font-weight:600;margin-top:6px;line-height:1.3}}
.oa{{font-size:16px;color:#94a3b8;margin-top:6px}}
.bottom{{position:absolute;left:46px;right:46px;bottom:28px}}
.bar{{display:flex;height:16px;border-radius:10px;overflow:hidden;gap:3px}}
.legend{{display:flex;gap:22px;margin-top:10px;font-size:17px;color:#cbd5e1;font-weight:600}}
.lg i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:7px;vertical-align:-1px}}
.foot{{position:absolute;right:46px;bottom:28px;font-size:16px;color:#64748b;font-weight:700}}
</style></head><body>
<div class="wrap">
 <div>
  <div class="kicker">BOOKMARK WRAPPED</div><div class="handle">{handle}</div>
  <div class="big">{total}</div><div class="bigl">bookmarks I meant to act on</div>
  <div class="range">posts from {_fmt_month(s['first'])} → {_fmt_month(s['last'])}</div>
  <div class="tiles">
   <div class="tile"><div class="tv amber">{s['open_actions']}</div><div class="tl">open actions</div></div>
   <div class="tile"><div class="tv green">{s['fresh_pct']}%</div><div class="tl">still fresh</div></div>
   <div class="tile"><div class="tv red">{s['by_status'].get('broken', 0)}</div><div class="tl">now broken</div></div>
   <div class="tile"><div class="tv blue">{s['self_bookmarks']}</div><div class="tl">were my own posts</div></div>
  </div>
 </div>
 <div class="right">
  <div><div class="h">TOP THEMES</div>{themes}</div>
  <div><div class="h">MOST-SAVED AUTHORS</div><div class="chips">{authors}</div></div>
  {oldtxt}
  {f'<div><div class="h">SKILLS I MEANT TO LEARN</div><div class="chips">{skills}</div></div>' if skills else ''}
 </div>
</div>
<div class="foot">Bookmark Debt Collector</div>
<div class="bottom"><div class="bar">{bar}</div><div class="legend">{legend}</div></div>
<script>/* drop chips that don't fit instead of clipping them */
document.querySelectorAll('.chips').forEach(c=>{{while(c.children.length>1&&c.scrollWidth>c.clientWidth+1)c.lastElementChild.remove();}});</script>
</body></html>"""


CARD_PNG_HELP = """card.png could not be rendered ({why}). card.html is written. Fix one of these and re-run:
  * .venv/bin/pip install playwright && .venv/bin/python -m playwright install --only-shell chromium   (no root)
  * if that Chromium then fails on missing system libraries: .venv/bin/python -m playwright install-deps chromium   (needs root)
  * or install any Chrome/Chromium and put it on PATH (google-chrome, chromium, chromium-browser), or set BDC_CHROME=/path/to/chrome"""


def _system_chrome() -> str | None:
    import os
    return os.environ.get("BDC_CHROME") or shutil.which("google-chrome") or shutil.which("chromium") \
        or shutil.which("chromium-browser") or shutil.which("google-chrome-stable")


def _render_playwright(html_path: Path, out_png: Path, scale: int, width: int, height: int) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = None
        exe = _system_chrome()
        if exe:
            try:
                b = p.chromium.launch(executable_path=exe)
            except Exception:
                b = None
        if b is None:
            b = p.chromium.launch()   # playwright's own chromium / headless shell
        pg = b.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
        pg.goto(html_path.resolve().as_uri())
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": width, "height": height})
        b.close()


def _render_chrome_cli(html_path: Path, out_png: Path, scale: int, width: int, height: int) -> None:
    """No playwright: drive a system Chrome directly (same engine, same pixels)."""
    import subprocess
    import tempfile
    exe = _system_chrome()
    if not exe:
        raise RuntimeError("no playwright and no Chrome/Chromium on PATH")
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--user-data-dir={prof}", f"--window-size={width},{height}",
                        f"--force-device-scale-factor={scale}", "--virtual-time-budget=1500",
                        f"--screenshot={Path(out_png).resolve()}", html_path.resolve().as_uri()],
                       check=True, capture_output=True, timeout=90)
    if not Path(out_png).exists():
        raise RuntimeError("chrome ran but wrote no screenshot")


def render_png(html_text: str, out_png: Path, scale: int = 2, width: int = 1200, height: int = 675) -> Path:
    """HTML -> PNG. Tries playwright (system Chrome first, then its own Chromium), then
    a system Chrome on the command line. Raises RuntimeError with fix-it steps."""
    import tempfile
    out_png = Path(out_png)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    tmp.write(html_text)
    tmp.close()
    html_path = Path(tmp.name)
    errors = []
    try:
        for fn in (_render_playwright, _render_chrome_cli):
            try:
                fn(html_path, out_png, scale, width, height)
                return out_png
            except Exception as e:  # noqa: BLE001
                errors.append(f"{fn.__name__[8:]}: {str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__}")
        raise RuntimeError(CARD_PNG_HELP.format(why="; ".join(errors)))
    finally:
        html_path.unlink(missing_ok=True)
