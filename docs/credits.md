# Credits and cost

X API reads are billed per returned resource. As of the X developer docs in October 2026 (check the Developer Console
for current rates; prices change):

- **Owned Reads**: `GET /2/users/{id}/bookmarks` for *your own* bookmarks through *your own* developer app:
  **$0.001 per returned post** (1,000 for $1).
- Regular post reads: $0.005 per post. User reads: $0.010 per user.
- Resources are deduplicated within a 24-hour UTC window: fetching the same post twice in a day is billed once.
- Expansions (authors, quoted posts) arrive in `includes`; how they are billed isn't spelled out on the pricing page,
  so treat the per-bookmark number as a floor.

Through Grok Bot's X plugin, reads draw on the plugin's X API credits instead of your own app; same principle, same
habits.

## How this project keeps reads down
- **First run**: one full pull (100 per page). ~100 bookmarks ≈ $0.10 at Owned-Read pricing. X only returns your 800
  most recent bookmarks, so a first run tops out around $0.80.
- **Every later run**: a **probe** of `max_results=10`. If any of those 10 is already known, stop. Only if all 10 are
  new do we page further, 100 at a time, stopping at the first page that contains a known id. The bookmarks endpoint
  has no `since_id`, so this is the cheapest correct way to get "just the new ones".
- A normal week therefore costs **10 post reads**.
- Freshness checks hit GitHub, arXiv and the linked sites, not the X API. Quoted-post liveness comes free with the
  bookmark pull (the `errors` array).
- Everything is cached locally (`archive.json`, `.cache.json`, `state.json`).

## Trade-off
Incremental pulls can't see **un-bookmarks**: if you remove a bookmark on X it stays in the local archive. Archive it in
the weekly conversation, or do an occasional full pull (delete `known_ids` from `state.json`).
