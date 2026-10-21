# Freshness check

Bookmarks rot. Links die, repos get archived, quoted posts get deleted, papers get v3.

## What gets checked
| Check | How | Dead when |
|---|---|---|
| Outbound links | `GET` with redirects, 12 s timeout | 404 / 410 / 451, 5xx (except 503), or connection failure |
| GitHub repos | `api.github.com/repos/{owner}/{repo}` + `/releases` | 404 (deleted, renamed away or private) or `archived: true` |
| arXiv papers | `export.arxiv.org/api/query?id_list=` | no such paper |
| Quoted / replied-to posts | the X API's own `errors` array for `referenced_tweets.id` | "Not Found" (deleted) or "not authorized" (protected, suspended or restricted) |

Also reported, not counted as dead:
- **dormant** repos: no push in over 365 days
- **new releases since you saved it**: releases published after the bookmarked post
- **renamed** repos (the API follows the redirect)
- **newer arXiv version** posted after the bookmark

Not verifiable, never called dead:
- x.com pages (X Articles, profiles) need a login, so a bot gets a 404 or a wall. We report them as `unknown`.
- 401 / 403 / 429 / 503 responses (bot walls, rate limits)

## Status per bookmark
1. `broken` if any check above is dead.
2. Otherwise by **shelf life**: each bucket has a half-life, and decay = `exp(−age · ln2 / half_life)`.

| Bucket | Half-life |
|---|---|
| Install/Try | 90 days |
| Read | 60 days |
| Learn | 365 days |
| Follow up | 30 days |
| Archive | 14 days |

`fresh` while decay ≥ 0.5 (younger than one half-life), `aging` while ≥ 0.125 (up to three half-lives), `stale` after.

**"% still fresh"** on the card = bookmarks with status `fresh` / all bookmarks.

Age is measured from the **post's** creation date because X does not expose when you bookmarked it.

## Caching
All results are cached in `out/.cache.json` (or `--cache`). Re-runs only check new URLs. Delete the cache to re-check
everything. Unauthenticated GitHub allows 60 requests per hour; set `GITHUB_TOKEN` if you have many repos.
`--offline` skips the network and uses the HTTP status X recorded when it unfurled each link.
