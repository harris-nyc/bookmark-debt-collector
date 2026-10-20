---
name: bookmark-wrapped
description: >
  Make my "Bookmark Wrapped" card: a 1200x675 dark PNG with real stats from my X bookmarks (total saved, date range,
  open actions, % still fresh, top themes, most-saved authors, oldest untouched bookmark, skills I meant to learn).
  Use when I ask for my bookmark wrapped, a shareable bookmark card, or run /bookmark-wrapped.
metadata:
  short-description: "Shareable stats card from real data"
---

# Bookmark Wrapped

## Steps
1. Make sure bookmark-triage has run (needs `private/out/triage.json`, `themes.json`, `freshness.json`). If the triage
   review pass or theme naming hasn't happened, do those first: the card is only as good as the names and skills.
2. Run `.venv/bin/bdc run ... ` (same command as bookmark-triage). It writes:
   - `private/out/wrapped.json`: every number on the card
   - `private/out/card.png` (2400x1350, for posting) and `card@1x.png` (1200x675)
   - `private/out/card.html` (edit + re-render if I want a different look)
3. Open `card.png` and check it: nothing clipped, no private-topic text, numbers match `wrapped.json`.
4. Reply with the card attached and a 3-line summary of the stats. Suggest one post caption, but **do not post it**.

## What's on the card and where it comes from
| Card element | Source |
|---|---|
| big number | count of bookmarks returned by the X API |
| posts from A → B | min/max `created_at` of the bookmarked posts (X does not expose when you bookmarked) |
| open actions | bookmarks not in the Archive bucket |
| still fresh | `freshness.summarize().fresh_pct` |
| now broken | bookmarks with status `broken` |
| my own posts | bookmarks whose author is me |
| top themes | 4 largest clusters, names from `theme_names.json` (sensitive themes are skipped: `_...` names, `_hide`, personal-looking names/terms, mostly private posts; see `privacy.json`) |
| most-saved authors | top 3 authors by bookmark count, excluding me and private-topic posts |
| oldest untouched | oldest bookmarked post with no do/snooze/archive decision, excluding private-topic posts |
| skills I meant to learn | `skill` labels of Learn bookmarks, oldest first |

## Rules
- Only real numbers. If a stat can't be computed, drop the element; never estimate it.
- Private-topic posts (see `src/bdc/privacy.py` and `--private-keywords`) count toward totals but never appear as text.
- Posting the card anywhere needs my explicit approval.
