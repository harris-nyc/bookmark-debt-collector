# BOT.md: make a Bookmark Wrapped card for your user

for a Grok Bot that got here from an `@bot make one for me` reply (or any "make me one" ask). you only need the post
and this repo. goal: your user's own Bookmark Wrapped card (1200x675 PNG) plus their top 3 open actions, delivered in
your chat with them. ~5 min of your time, one or two taps from them.

## rules (all steps)
- **read-only on X.** never post, reply, quote, like, repost, follow, bookmark, unbookmark or DM. not even the card.
- **their data stays private.** everything lives in `~/bookmark-debt-collector/private/` on your computer (gitignored).
  never commit it, push it, upload it, paste it in a gist/pastebin/public URL, or send it anywhere but your chat with them.
- **ask first** before anything that needs a login other than the X plugin, and before creating skills or routines.
- run every command from `~/bookmark-debt-collector`. never make up numbers: they all come from `bdc` output.

## 1. check the X plugin
call `get_users_me` on the X plugin (connector namespace `user-X`). keep `data.id` and `data.username`.
if the plugin isn't connected or the call fails: tell the user "connect the X plugin (Connect apps → X) and i'll make
your card", show the connect card if you can, and **stop until they've connected it**.

## 2. install (~1 min)
```bash
git clone --depth 1 https://github.com/harris-nyc/bookmark-debt-collector ~/bookmark-debt-collector
cd ~/bookmark-debt-collector && python3 -m venv .venv && .venv/bin/pip install -q -e .
command -v google-chrome || command -v chromium || command -v chromium-browser \
  || { .venv/bin/pip install -q playwright && .venv/bin/python -m playwright install --only-shell chromium; }
```
- needs python 3.10+. the card is rendered by headless chrome: an installed Chrome/Chromium is used as is, otherwise
  playwright's headless shell is downloaded (~275 MB on disk, no root, ~15 s).
- `python3 -m venv` fails (no `python3-venv`)? use `python3 -m pip install --user -e .` and replace `.venv/bin/bdc`
  with `python3 -m bdc` below.
- skip `fastembed` for the first card. themes fall back to TF-IDF; you'll name them in step 5 anyway.

## 3. pull bookmarks
call `get_users_bookmarks` on the X plugin with exactly:
```json
{"id": "<data.id from step 1>", "max_results": 100,
 "expansions": "author_id,attachments.media_keys,referenced_tweets.id",
 "post.fields": "created_at,author_id,public_metrics,entities,lang,conversation_id,note_tweet,referenced_tweets,context_annotations",
 "user.fields": "username,name,public_metrics,verified,description",
 "media.fields": "type,url,preview_image_url"}
```
save the raw result to a file (use your tool call's write-to-file option if it has one; otherwise write the JSON exactly
as returned). wrappers and notes around the JSON are fine. then:
```bash
.venv/bin/bdc ingest <saved file>
```
it prints `NEXT: ...`. if it says `call get_users_bookmarks again with pagination_token=...`, call again with the same
args plus that `pagination_token`, save, ingest. repeat until it says `done` or `stop`.

## 4. run it (~1 min, checks links, GitHub and arXiv)
```bash
.venv/bin/bdc run --input private/archive.json --out private/out --me <username> --state private/state.json \
  --overrides private/triage_overrides.json --theme-names private/theme_names.json
```
the two json files don't exist yet, that's fine. exit 0 = done. exit 3 = card.png missing: do what it printed, re-run.

## 5. polish (2 min, worth it)
- read `private/out/themes.json`. write `private/theme_names.json`: a 2-4 word name per theme,
  keyed `"term:<one of its top 4 terms>"`, e.g. `{"term:inference": "fast inference", "term:founders": "founder advice"}`.
  prefix a name with `_` to keep a personal theme (dating, health, politics, money) off the card.
- optional: for the top 3 in `private/out/resurface.md`, write sharper next actions in `private/triage_overrides.json`:
  `{"<post id>": {"category": "Read", "next_action": "read the eval section, 10 min"}}` (format: `docs/triage.md`).
- re-run step 4.

## 6. look at the card, then deliver
open `private/out/card@1x.png` (1200x675) yourself. if anything is clipped or looks personal, hide it in step 5 and
re-run. then, in your chat with the user only:
1. attach `private/out/card@1x.png` (mention `card.png` is the 2x version)
2. paste the 3 items from `private/out/resurface.md`
3. one line: total bookmarks, open actions, % still fresh (from the `bdc` output)
4. "share your card if you want: quote the launch post with it." (they post it, you don't)

## 7. offer the weekly nudge (ask, don't auto-create)
ask once: "want me to keep this going? i'd save 4 skills and a weekly sunday check (3 bookmarks: do / snooze /
archive)." only if yes: save each of `skills/bookmark-triage`, `skills/freshness-check`,
`skills/bookmark-wrapped`, `skills/weekly-resurface` (`SKILL.md`) as a private skill, then create the routine from
`routine/weekly-routine.md` in their time zone and echo the schedule back. record later answers with
`.venv/bin/bdc decide --state private/state.json <1-3> <do|snooze|archive>`.

## test without X
```bash
.venv/bin/python examples/simulate_mcp_pull.py private/pulls        # writes page-1..3.txt like the plugin would
for f in private/pulls/page-*.txt; do .venv/bin/bdc ingest "$f"; done
.venv/bin/bdc run --input private/archive.json --out private/out --me demo_you --state private/state.json --theme-names examples/theme_names.json
```

## if something breaks
| symptom | fix |
|---|---|
| `no bookmarks page found` from `ingest` | the file isn't the get_users_bookmarks result. save the raw tool output, unedited |
| `no bookmarks in the input` | X returned none. tell the user to bookmark a few posts first |
| exit 3, `card.png could not be rendered` | run the fix it printed (install playwright's chromium), re-run step 4 |
| rate limited by X | wait a minute, retry the same page (the plugin allows ~30 calls/min) |
| card shows something personal | `_`-prefix that theme or add `"_hide": ["term:<word>"]` in `theme_names.json`, re-run |
