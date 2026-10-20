"""Credit-aware bookmark pulls.

X API reads cost credits per returned post, and the bookmarks endpoint has no
since_id. So after the first run we:
  1. ask for a small probe page (default 10)
  2. stop as soon as a page contains a bookmark we already have
  3. only page further (100 at a time) while every item is new
A weekly run with 0-5 new bookmarks therefore costs ~10 post reads, not 100+.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

FIELDS = {
    "expansions": "author_id,attachments.media_keys,referenced_tweets.id",
    "post.fields": "created_at,author_id,public_metrics,entities,lang,conversation_id,note_tweet,referenced_tweets,context_annotations",
    "user.fields": "username,name,public_metrics,verified,description",
    "media.fields": "type,url,preview_image_url",
}
COST_PER_READ = 0.001  # USD, X API "Owned Reads" for your own bookmarks (Oct 2026); expansions may bill extra


def pull(user_id: str, token: str, known_ids: set[str], probe: int = 10, max_pages: int = 10) -> tuple[list[dict], dict]:
    url = f"https://api.x.com/2/users/{user_id}/bookmarks"
    params = {**FIELDS, "max_results": probe if known_ids else 100}
    pages, returned, new = [], 0, 0
    for _ in range(max_pages):
        r = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("x-rate-limit-reset", time.time() + 60)) - time.time() + 1)
            continue
        r.raise_for_status()
        j = r.json()
        pages.append(j)
        ids = [p["id"] for p in j.get("data", [])]
        returned += len(ids)
        fresh = [i for i in ids if i not in known_ids]
        new += len(fresh)
        tok = (j.get("meta") or {}).get("next_token")
        if len(fresh) < len(ids) or not tok:
            break
        params = {**FIELDS, "max_results": 100, "pagination_token": tok}
    return pages, {"returned": returned, "new": new, "est_cost_usd": round(returned * COST_PER_READ, 4)}


def merge_archive(archive_path: Path, new_pages: list[dict]) -> tuple[list[dict], int]:
    """Archive = list of raw API pages, most recently bookmarked first. Returns (pages, n_new_posts).

    A fresh pull goes in front of the archive. When a pull is ingested one page at a time,
    the page that still had a next_token is marked `_bdc_continue`, and the following pages
    are slotted in right after it, so the archive keeps API order."""
    old = json.loads(archive_path.read_text()) if archive_path.exists() else []
    if isinstance(old, dict):
        old = [old]
    known = {p["id"] for pg in old for p in pg.get("data", [])}
    n_new, hit_known = 0, False
    trimmed = []
    for pg in new_pages:
        pg = {k: v for k, v in pg.items() if k != "_bdc_continue"}
        data = [p for p in pg.get("data", []) if p["id"] not in known]
        hit_known = hit_known or len(data) < len(pg.get("data", []))
        n_new += len(data)
        known.update(p["id"] for p in data)
        if data:
            trimmed.append({**pg, "data": data})
    at = next((i + 1 for i, pg in enumerate(old) if pg.get("_bdc_continue")), 0)
    for pg in old:
        pg.pop("_bdc_continue", None)
    if trimmed and not hit_known and (new_pages[-1].get("meta") or {}).get("next_token"):
        trimmed[-1]["_bdc_continue"] = True
    merged = old[:at] + trimmed + old[at:]
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(json.dumps(merged))
    return merged, n_new


# ---------------------------------------------------------------- connector pages
# A Grok Bot calls the X plugin's get_users_bookmarks and saves the tool result to a
# file. That file is not always clean JSON: it can be wrapped in a fence/tag line, an
# MCP {"content": [{"type": "text", "text": "..."}]} envelope, or followed by a
# rate-limit note. extract_pages() digs every bookmarks page out of whatever it gets.

def _is_page(x) -> bool:
    return isinstance(x, dict) and (isinstance(x.get("data"), list) or
                                    ("meta" in x and "data" not in x and "result_count" in (x.get("meta") or {})))


def _unwrap(x) -> list[dict]:
    if _is_page(x):
        return [{**x, "data": x.get("data", [])}]
    if isinstance(x, list):
        return [pg for item in x for pg in _unwrap(item)]
    if isinstance(x, dict):
        for key in ("content", "result", "structuredContent", "output", "response"):
            if key in x:
                got = _unwrap(x[key])
                if got:
                    return got
        if isinstance(x.get("text"), str):
            return extract_pages(x["text"])
    if isinstance(x, str):
        return extract_pages(x)
    return []


def extract_pages(text: str) -> list[dict]:
    """Return every X API bookmarks page found in `text` (raw JSON, a list of pages,
    an MCP envelope, or JSON surrounded by other text)."""
    try:
        return _unwrap(json.loads(text))
    except ValueError:
        pass
    dec, pages, i = json.JSONDecoder(), [], 0
    while i < len(text):
        if text[i] in "{[":
            try:
                obj, end = dec.raw_decode(text, i)
            except ValueError:
                i += 1
                continue
            got = _unwrap(obj)
            if got:
                pages.extend(got)
                i = end
                continue
        i += 1
    return pages
