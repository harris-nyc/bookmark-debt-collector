"""Freshness check: is the thing you saved still alive, and has it moved on?

Per bookmark we check:
  * every outbound link (HTTP status, following redirects)
  * GitHub repos: archived?, stars, last push, releases since the post
  * arXiv papers: newer versions since the post
  * quoted / replied-to posts: still visible? (from X API errors)
and combine that with a category-aware shelf life (see docs/freshness.md).

Results are cached in a JSON file so re-runs don't re-hit the network.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from .normalize import ARXIV_RE, GITHUB_RE, X_HOSTS

UA = "Mozilla/5.0 (X11; Linux x86_64) BookmarkDebtCollector/0.1 (+https://github.com/)"
TIMEOUT = 12

# Shelf life (half-life in days) per triage category. A bookmark is "fresh" while
# exp(-age * ln2 / half_life) >= 0.5, i.e. while it is younger than its half-life,
# AND nothing it depends on is dead.
HALF_LIFE_DAYS = {
    "Install/Try": 90,      # repos and tools move fast
    "Read": 60,             # takes, threads and articles go stale
    "Learn": 365,           # skills and guides are mostly evergreen
    "Follow up": 30,        # people forget you after a month
    "Archive": 14,          # news and hot takes
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def age_days(rec: dict, ref: datetime | None = None) -> float:
    if not rec.get("created_at"):
        return 0.0
    dt = datetime.fromisoformat(rec["created_at"].replace("Z", "+00:00"))
    return max(0.0, ((ref or now_utc()) - dt).total_seconds() / 86400)


class Cache:
    def __init__(self, path: Path | None):
        self.path = path
        self.data = json.loads(path.read_text()) if path and path.exists() else {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, val):
        self.data[key] = val

    def save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True))


def check_url(url: str) -> dict:
    """Return {"state": alive|dead|unknown, "http": code, "final_url": ...}."""
    host = urlparse(url).netloc.lower()
    if host in X_HOSTS:
        # X pages (articles, profiles) sit behind a login wall for bots; we can't verify them.
        return {"state": "unknown", "http": None, "note": "x.com page needs login; not verifiable"}
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True, stream=True)
        code = r.status_code
        r.close()
        final = r.url
    except requests.exceptions.ConnectionError as e:
        return {"state": "dead", "http": None, "note": f"connection failed: {type(e).__name__}"}
    except requests.RequestException as e:
        return {"state": "unknown", "http": None, "note": f"{type(e).__name__}"}
    if code in (404, 410, 451) or code >= 500 and code != 503:
        state = "dead"
    elif code in (401, 403, 429, 503) or code >= 400:
        state = "unknown"   # bot walls, rate limits: don't call it dead
    else:
        state = "alive"
    return {"state": state, "http": code, "final_url": final if final != url else None}


def check_github(repo: str, since: str | None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=TIMEOUT)
        if r.status_code == 404:
            return {"repo": repo, "state": "dead", "note": "repo not found (deleted, renamed or private)"}
        if r.status_code != 200:
            return {"repo": repo, "state": "unknown", "note": f"GitHub API {r.status_code}"}
        j = r.json()
        info = {
            "repo": j["full_name"], "state": "archived" if j.get("archived") else "alive",
            "stars": j.get("stargazers_count"), "pushed_at": j.get("pushed_at"),
            "archived": j.get("archived", False), "description": j.get("description"),
            "renamed_from": repo if j["full_name"].lower() != repo.lower() else None,
        }
        rr = requests.get(f"https://api.github.com/repos/{repo}/releases?per_page=30", headers=headers, timeout=TIMEOUT)
        rels = rr.json() if rr.status_code == 200 else []
        if rels:
            info["latest_release"] = rels[0].get("tag_name")
            info["latest_release_at"] = rels[0].get("published_at")
            if since:
                info["releases_since_saved"] = sum(1 for x in rels if (x.get("published_at") or "") > since)
        if j.get("pushed_at"):
            pushed = datetime.fromisoformat(j["pushed_at"].replace("Z", "+00:00"))
            info["days_since_push"] = round((now_utc() - pushed).total_seconds() / 86400)
            if not j.get("archived") and info["days_since_push"] > 365:
                info["state"] = "dormant"
        return info
    except requests.RequestException as e:
        return {"repo": repo, "state": "unknown", "note": type(e).__name__}


def check_arxiv(aid: str, since: str | None) -> dict:
    try:
        r = requests.get(f"https://export.arxiv.org/api/query?id_list={aid}", headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code != 200:
            return {"arxiv": aid, "state": "unknown", "note": f"arXiv API {r.status_code}"}
        entry = r.text.split("<entry>", 1)
        if len(entry) < 2 or "<id>" not in entry[1]:
            return {"arxiv": aid, "state": "dead", "note": "no such paper"}
        e = entry[1]
        vid = re.search(r"<id>http://arxiv.org/abs/[^<]*?(v\d+)</id>", e)
        upd = re.search(r"<updated>([^<]+)</updated>", e)
        title = re.search(r"<title>([^<]+)</title>", e)
        info = {"arxiv": aid, "state": "alive", "latest_version": vid.group(1) if vid else None,
                "updated": upd.group(1) if upd else None,
                "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else None}
        if since and info["updated"] and info["updated"] > since and info["latest_version"] not in (None, "v1"):
            info["updated_since_saved"] = True
        return info
    except requests.RequestException as e:
        return {"arxiv": aid, "state": "unknown", "note": type(e).__name__}


def run(records: list[dict], categories: dict[str, str] | None = None, cache_path: Path | None = None,
        offline: bool = False, ref_time: datetime | None = None) -> list[dict]:
    """Return one freshness result per record (same order)."""
    categories = categories or {}
    cache = Cache(cache_path)
    ref_time = ref_time or now_utc()

    # Gather unique network checks
    urls, repos, papers = set(), {}, {}
    for r in records:
        for l in r["links"]:
            urls.add(l["url"])
            m = GITHUB_RE.search(l["url"])
            if m:
                repos.setdefault(f"{m.group(1)}/{m.group(2).removesuffix('.git')}", r["created_at"])
            m = ARXIV_RE.search(l["url"])
            if m:
                papers.setdefault(m.group(1), r["created_at"])

    def cached(key, fn):
        hit = cache.get(key)
        if hit is not None:
            return hit
        val = fn()
        cache.set(key, val)
        return val

    hints = {l["url"]: l.get("x_status_hint") for r in records for l in r["links"]}
    if offline:
        url_res = {}
        for u in urls:
            h = hints.get(u)
            hit = cache.get("url:" + u)
            url_res[u] = hit or ({"state": "alive" if h and h < 400 else "dead" if h in (404, 410) else "unknown",
                                  "http": h, "note": "offline: using X unfurl status"})
        gh_res = {k: cache.get("gh:" + k) or {"repo": k, "state": "unknown", "note": "offline"} for k in repos}
        ax_res = {k: cache.get("arxiv:" + k) or {"arxiv": k, "state": "unknown", "note": "offline"} for k in papers}
    else:
        with ThreadPoolExecutor(max_workers=8) as ex:
            url_res = dict(zip(urls, ex.map(lambda u: cached("url:" + u, lambda: check_url(u)), urls)))
        gh_res = {k: cached("gh:" + k, lambda k=k, s=s: check_github(k, s)) for k, s in repos.items()}
        ax_res = {k: cached("arxiv:" + k, lambda k=k, s=s: check_arxiv(k, s)) for k, s in papers.items()}
        cache.save()

    results = []
    for r in records:
        issues, notes, checks = [], [], []
        for l in r["links"]:
            res = url_res.get(l["url"], {"state": "unknown"})
            checks.append({"type": "link", "url": l["url"], **res})
            if res["state"] == "dead":
                issues.append(f"dead link: {l['url']}")
        for k in sorted({f"{m.group(1)}/{m.group(2).removesuffix('.git')}" for l in r["links"] if (m := GITHUB_RE.search(l["url"]))}):
            g = gh_res[k]
            checks.append({"type": "github", **g})
            if g["state"] in ("dead", "archived"):
                issues.append(f"repo {g['state']}: {k}")
            if g["state"] == "dormant":
                notes.append(f"{k}: no commits in {g.get('days_since_push')} days")
            if g.get("releases_since_saved"):
                notes.append(f"{k}: {g['releases_since_saved']} new release(s) since you saved it (latest {g.get('latest_release')})")
            if g.get("renamed_from"):
                notes.append(f"{k} moved to {g['repo']}")
        for k in sorted({m.group(1) for l in r["links"] if (m := ARXIV_RE.search(l["url"]))}):
            a = ax_res[k]
            checks.append({"type": "arxiv", **a})
            if a["state"] == "dead":
                issues.append(f"paper not found: arXiv {k}")
            if a.get("updated_since_saved"):
                notes.append(f"arXiv {k} has a newer version ({a['latest_version']})")
        for q in r["quoted"]:
            checks.append({"type": "quoted_post", "id": q["id"], "state": "alive" if q["status"] == "ok" else "dead", "x_status": q["status"]})
            if q["status"] != "ok":
                why = "deleted" if q["status"] == "not_found" else "no longer visible to you: protected, suspended or restricted"
                issues.append(f"{q['type'].replace('_', ' ')} post {q['id']} is gone ({why})")

        cat = categories.get(r["id"], "Read")
        hl = HALF_LIFE_DAYS.get(cat, 60)
        age = age_days(r, ref_time)
        decay = math.exp(-age * math.log(2) / hl)
        broken = bool(issues)
        if broken:
            status = "broken"
        elif decay >= 0.5:
            status = "fresh"
        elif decay >= 0.125:
            status = "aging"
        else:
            status = "stale"
        results.append({
            "id": r["id"], "url": r["url"], "category": cat, "age_days": round(age, 1),
            "half_life_days": hl, "decay": round(decay, 3), "status": status,
            "issues": issues, "notes": notes, "checks": checks,
        })
    return results


def summarize(results: list[dict]) -> dict:
    n = len(results) or 1
    by = {}
    for x in results:
        by[x["status"]] = by.get(x["status"], 0) + 1
    checks = [c for x in results for c in x["checks"]]
    dead = [c for c in checks if c["state"] == "dead"]
    return {
        "total": len(results),
        "by_status": by,
        "fresh_pct": round(100 * by.get("fresh", 0) / n),
        "checked": len(checks),
        "dead": len(dead),
        "archived_repos": sum(1 for c in checks if c["state"] == "archived"),
        "dormant_repos": sum(1 for c in checks if c["state"] == "dormant"),
        "unverifiable": sum(1 for c in checks if c["state"] == "unknown"),
        "alive_pct_of_verifiable": round(100 * sum(1 for c in checks if c["state"] in ("alive", "dormant", "archived")) /
                                         max(1, sum(1 for c in checks if c["state"] != "unknown"))),
        "with_updates": sum(1 for x in results if x["notes"]),
    }
