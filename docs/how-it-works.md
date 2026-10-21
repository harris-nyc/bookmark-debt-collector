# How it works

```
X bookmarks ──► normalize ──► triage (rules) ──► review pass (Grok Bot) ──┐
 (X plugin or                                                               ▼
  your API token)          themes: embed → k-means → c-TF-IDF ──► theme names
                                                                            │
                           freshness: links · repos · papers · quotes ──────┤
                                                                            ▼
                      actions.md · freshness.md · wrapped.json → card.png · resurface.md
                                                                            │
                                  weekly routine ◄── state.json (do / snooze / archive, known ids)
```

| Step | Code | Output |
|---|---|---|
| Pull | X plugin `get_users_bookmarks` (Grok Bot) or `bdc pull` (your token) | raw X API v2 pages |
| Merge | `bdc ingest` / `fetch.merge_archive` | `archive.json` (deduplicated, newest first) |
| Normalize | `normalize.py` | one flat record per bookmark: full text (incl. long posts), author, outbound links, quoted posts and whether they still exist, X topic annotations, metrics |
| Triage | `triage.py` + `triage_overrides.json` | bucket + next action per bookmark ([triage.md](triage.md)) |
| Themes | `cluster.py` + `theme_names.json` | clusters with labels ([clustering.md](clustering.md)) |
| Freshness | `freshness.py` | status per bookmark ([freshness.md](freshness.md)) |
| Report | `report.py` | `actions.md`, `actions.public.md`, `freshness.md` |
| Wrapped | `wrapped.py` | `wrapped.json`, `card.html`, `card.png` (headless Chrome/Chromium, directly or via Playwright) |
| Resurface | `resurface.py` | `resurface.md`, `state.json` |

## Division of labour: scripts vs. the bot

The scripts are deterministic and offline-friendly: parsing, counting, HTTP checks, clustering, rendering. They never
call an LLM, so every number is reproducible.

The Grok Bot does what scripts are bad at, through the skills in `skills/`:
- calling the X plugin (read-only) and deciding how far to page (only what's new),
- the **review pass**: rewriting generic rule-based next actions into specific ones, fixing buckets,
- naming themes,
- the weekly conversation (do / snooze / archive) and recording answers.

The bot's judgement is stored as data (`triage_overrides.json`, `theme_names.json`), so you can see it, edit it,
and re-run without the bot.

## The weekly resurface ranker

A small two-stage recommender over your own backlog:

1. **Score** each open bookmark:
   `score = w(bucket) × (0.25 + debt) × quality × alive`
   - `w`: Install/Try 1.0, Follow up 1.0, Learn 0.9, Read 0.8, Archive 0 (never resurfaced)
   - `debt = min(1, log1p(age_days) / log1p(365))`: older unpaid debt ranks higher, with diminishing returns
   - `quality = 0.5 + 0.5 × percentile(bookmark_count / impression_count)`: the post's save rate among people who saw
     it, a cheap popularity-normalised quality prior
   - `alive = 0.3` if the bookmark is broken, else 1
2. **Re-rank with MMR** (λ = 0.5): greedily pick the next item maximising
   `λ·score − (1−λ)·max_sim(item, already picked)`, where similarity is 0.4·same theme + 0.2·same author + 0.4·same bucket.
   Three picks from the same cluster would be a bad week.

Done and archived items never come back; snoozed items come back after N days (default 14).
