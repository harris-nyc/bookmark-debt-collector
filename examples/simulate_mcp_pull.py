"""Pretend to be the X plugin: split the synthetic sample into get_users_bookmarks
pages and save each one the way a Grok Bot tool result lands on disk (a wrapper
line, the JSON, then a rate-limit note). Lets you test `bdc ingest` and the whole
BOT.md flow without X credentials or credits.

  python examples/simulate_mcp_pull.py private/pulls --page-size 12
  -> private/pulls/page-1.txt, page-2.txt, ...   (follow meta.next_token like the real thing)
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("outdir")
ap.add_argument("--page-size", type=int, default=12)
a = ap.parse_args()

src = json.loads((ROOT / "sample_bookmarks.json").read_text())
posts = src["data"]
out = Path(a.outdir)
out.mkdir(parents=True, exist_ok=True)
chunks = [posts[i:i + a.page_size] for i in range(0, len(posts), a.page_size)]
for n, chunk in enumerate(chunks, 1):
    page = {"data": chunk, "includes": src.get("includes", {}), "errors": src.get("errors", []),
            "meta": {"result_count": len(chunk)}}
    if n < len(chunks):
        page["meta"]["next_token"] = f"synthetic-page-{n + 1}"
    body = ('<tool_result source="get_users_bookmarks">\n\n' + json.dumps(page) +
            "\nX reads left for this user: 29 of 30 this minute, 999 of 1000 today.\n\n</tool_result>\n")
    (out / f"page-{n}.txt").write_text(body)
    print(out / f"page-{n}.txt", len(chunk), "posts", page["meta"].get("next_token", "(last page)"))
