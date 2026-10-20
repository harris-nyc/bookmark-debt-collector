"""Normalize X bookmark data into one flat record per bookmark.

Accepted inputs (auto-detected):
  * An X API v2 response: {"data": [...], "includes": {...}, "errors": [...]}
    (this is also what the official X connector in Grok Bot returns)
  * A list of such responses (multiple pages)
  * A "simple" export: a list of {"url", "text", "author", "created_at", "links"?}

Note: X does not expose *when* you bookmarked something. `created_at` is the
post's creation time; `rank` is the position in the API response, which is
most-recently-bookmarked first.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

X_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com", "mobile.twitter.com"}
STATUS_RE = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/([^/]+)/status/(\d+)", re.I)
GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I)
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(v\d+)?", re.I)
TCO_RE = re.compile(r"https?://t\.co/\w+")


def _parse_time(s: str) -> str:
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")  # legacy archive format
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_x_internal(url: str) -> bool:
    """True for links that just point back into X (quotes, photos, videos)."""
    host = urlparse(url).netloc.lower()
    if host not in X_HOSTS:
        return False
    path = urlparse(url).path
    return "/status/" in path or path.startswith("/i/web")


def _classify_link(url: str) -> str:
    if GITHUB_RE.search(url):
        return "github"
    if ARXIV_RE.search(url):
        return "arxiv"
    host = urlparse(url).netloc.lower()
    if host in X_HOSTS and "/i/article/" in url:
        return "x_article"
    if host.endswith("x.ai") and "/bot/" in url:
        return "grok_bot"
    if host.endswith("youtube.com") or host == "youtu.be":
        return "video"
    if host.endswith("huggingface.co"):
        return "huggingface"
    return "web"


def _pages(raw) -> list[dict]:
    if isinstance(raw, dict) and "data" in raw:
        return [raw]
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and "data" in raw[0]:
        return raw
    return []


def normalize_api(pages: list[dict], self_username: str | None = None) -> list[dict]:
    users, posts, media, errors = {}, {}, {}, {}
    data = []
    for pg in pages:
        inc = pg.get("includes", {}) or {}
        users.update({u["id"]: u for u in inc.get("users", [])})
        posts.update({p["id"]: p for p in inc.get("posts", inc.get("tweets", []))})
        media.update({m["media_key"]: m for m in inc.get("media", [])})
        for e in pg.get("errors", []) or []:
            rid = e.get("resource_id") or e.get("value")
            if rid:
                kind = "not_found" if "not-found" in e.get("type", "") or "Not Found" in e.get("title", "") else "not_authorized"
                errors[rid] = kind
        data.extend(pg.get("data", []))

    out, seen = [], set()
    for rank, p in enumerate(data):
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        note = p.get("note_tweet") or {}
        text = note.get("text") or p.get("text", "")
        ents = [p.get("entities") or {}, note.get("entities") or {}]
        author = users.get(p.get("author_id"), {})
        uname = author.get("username") or (STATUS_RE.search(p.get("url", "")) or [None, "unknown"])[1]

        links, link_urls = [], set()
        mentions, hashtags = set(), set()
        for e in ents:
            for u in e.get("urls", []) or []:
                url = u.get("unwound_url") or u.get("expanded_url") or u.get("url")
                if not url or _is_x_internal(url) or url in link_urls:
                    continue
                link_urls.add(url)
                links.append({
                    "url": url,
                    "kind": _classify_link(url),
                    "title": u.get("title"),
                    "x_status_hint": u.get("status"),  # HTTP status X saw when unfurling
                })
            mentions.update(m["username"] for m in e.get("mentions", []) or [])
            hashtags.update(h["tag"] for h in e.get("hashtags", []) or [])

        quoted = []
        for r in p.get("referenced_tweets", []) or []:
            rid = r["id"]
            if rid in posts:
                rp = posts[rid]
                qa = users.get(rp.get("author_id"), {}).get("username")
                quoted.append({"id": rid, "type": r["type"], "status": "ok", "author": qa,
                               "text": ((rp.get("note_tweet") or {}).get("text") or rp.get("text", ""))[:500]})
            else:
                quoted.append({"id": rid, "type": r["type"], "status": errors.get(rid, "missing"), "author": None, "text": ""})

        media_types = sorted({media[k]["type"] for k in (p.get("attachments") or {}).get("media_keys", []) if k in media})
        m = p.get("public_metrics") or {}
        out.append({
            "id": p["id"],
            "rank": rank,
            "url": p.get("url") or f"https://x.com/{uname}/status/{p['id']}",
            "created_at": _parse_time(p["created_at"]) if p.get("created_at") else None,
            "author_username": uname,
            "author_name": author.get("name"),
            "author_followers": (author.get("public_metrics") or {}).get("followers_count"),
            "author_bio": author.get("description"),
            "text": text,
            "lang": p.get("lang"),
            "is_self": bool(self_username) and uname.lower() == self_username.lower().lstrip("@"),
            "is_reply": any(r["type"] == "replied_to" for r in p.get("referenced_tweets", []) or []),
            "mentions": sorted(mentions),
            "hashtags": sorted(hashtags),
            "links": links,
            "quoted": quoted,
            "media": media_types,
            "context": sorted({c["entity"]["name"] for c in p.get("context_annotations", []) or []}),
            "metrics": {k: m.get(k) for k in ("like_count", "repost_count", "reply_count", "quote_count", "bookmark_count", "impression_count")},
        })
    return out


def normalize_simple(items: list[dict], self_username: str | None = None) -> list[dict]:
    out = []
    for rank, it in enumerate(items):
        url = it.get("url", "")
        m = STATUS_RE.search(url)
        uname = (it.get("author") or (m.group(1) if m else "unknown")).lstrip("@")
        pid = str(it.get("id") or (m.group(2) if m else rank))
        text = it.get("text", "")
        link_list = list(it.get("links", [])) + [u for u in re.findall(r"https?://\S+", text) if not TCO_RE.match(u)]
        links, seen = [], set()
        for u in link_list:
            u = u.rstrip(").,")
            if u in seen or _is_x_internal(u):
                continue
            seen.add(u)
            links.append({"url": u, "kind": _classify_link(u), "title": None, "x_status_hint": None})
        out.append({
            "id": pid, "rank": rank, "url": url or f"https://x.com/{uname}/status/{pid}",
            "created_at": _parse_time(it["created_at"]) if it.get("created_at") else None,
            "author_username": uname, "author_name": it.get("author_name"), "author_followers": None,
            "author_bio": None, "text": text, "lang": it.get("lang", "en"),
            "is_self": bool(self_username) and uname.lower() == self_username.lower().lstrip("@"),
            "is_reply": False, "mentions": re.findall(r"@(\w+)", text), "hashtags": re.findall(r"#(\w+)", text),
            "links": links, "quoted": [], "media": [], "context": [], "metrics": it.get("metrics", {}),
        })
    return out


def load(path: str | Path, self_username: str | None = None) -> list[dict]:
    raw = json.loads(Path(path).read_text())
    pages = _pages(raw)
    if pages:
        return normalize_api(pages, self_username)
    if isinstance(raw, list):
        return normalize_simple(raw, self_username)
    raise ValueError(f"Unrecognized bookmarks format in {path}")


def github_repos(rec: dict) -> list[str]:
    repos = []
    for l in rec["links"]:
        m = GITHUB_RE.search(l["url"])
        if m:
            owner, repo = m.group(1), m.group(2).removesuffix(".git")
            if owner.lower() not in {"orgs", "sponsors", "features", "topics", "marketplace"}:
                repos.append(f"{owner}/{repo}")
    return sorted(set(repos))


def arxiv_ids(rec: dict) -> list[str]:
    ids = []
    for l in rec["links"]:
        m = ARXIV_RE.search(l["url"])
        if m:
            ids.append(m.group(1))
    return sorted(set(ids))


def clean_text(text: str) -> str:
    import html
    text = html.unescape(TCO_RE.sub("", text or ""))
    return re.sub(r"\s+", " ", text).strip()
