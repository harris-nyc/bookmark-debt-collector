---
name: freshness-check
description: >
  Check whether my saved X bookmarks are still alive and current: dead links, deleted or hidden quoted posts,
  GitHub repos (archived, dormant, stars, new releases since I saved them) and arXiv papers with newer versions.
  Use when I ask "what's dead in my bookmarks", "are my bookmarks still fresh", or run /freshness-check.
metadata:
  short-description: "Dead links, stale repos, new releases"
---

# Freshness check

## Inputs
- `~/bookmark-debt-collector/private/archive.json` (from bookmark-triage). If missing, run the bookmark-triage pull first.
- Network access from the bot's computer. Optional `GITHUB_TOKEN` env var for higher GitHub rate limits
  (60 req/h unauthenticated is enough for a few hundred bookmarks thanks to the cache).

## Steps
1. Run `.venv/bin/bdc run --input private/archive.json --out private/out --me <username> --state private/state.json --overrides private/triage_overrides.json --theme-names private/theme_names.json`.
   Results are cached in `private/out/.cache.json`; delete it to force a full re-check.
2. Read `private/out/freshness.md` and `freshness.json`.
3. For anything **broken**, update its next action (via `private/triage_overrides.json`) to say what died and what to do
   instead (usually: unbookmark, or find the new home of a moved repo).
4. For anything with **updates since saved** (new release, new paper version, renamed repo), make the next action point at
   the new version.
5. Reply with: % still fresh, counts by status, every broken item (one line each), every updated item.

## How statuses are defined (don't redefine them in replies)
- `broken`: a link 404/410s or fails to connect, a repo is deleted or archived, or a quoted/replied-to post is deleted or
  no longer visible to me.
- Otherwise by age vs. the bucket's half-life (Install/Try 90d, Read 60d, Learn 365d, Follow up 30d, Archive 14d):
  `fresh` < 1 half-life, `aging` < 3 half-lives, `stale` beyond.
- x.com pages (articles, profiles) sit behind a login wall for bots: report them as **unverifiable**, never as dead.
- 401/403/429 responses are **unknown**, not dead.

## Rules
- Read-only on X. No network calls other than GET requests to the linked pages, the GitHub API and the arXiv API.
- Never claim a link is dead without an HTTP status or connection error to back it up.
