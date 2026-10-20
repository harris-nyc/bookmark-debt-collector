"""Keep private-feeling bookmarks off anything shareable (card, public action list,
freshness report).

Totals still count every bookmark; only the *text* of flagged items is withheld
from public outputs. A bookmark is flagged when any of these hold:

1. keyword: its text, quoted/replied-to text or link titles match
   DEFAULT_PRIVATE (+ --private-keywords),
2. sensitive theme: it sits in a theme that is hidden from the card (see
   `sensitive_themes`),
3. conversation: it quotes or replies to the same post as a flagged bookmark, or
   quotes/replies to a flagged bookmark. This catches posts whose own text is
   harmless but whose context (often a deleted quoted post) is not.

Themes are hidden from the card when their name starts with "_", when they are
listed under "_hide" in theme_names.json (or --hide-themes), when their name or
top terms hit SENSITIVE_THEME_WORDS, or when at least `share` of their members
are keyword-flagged.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_PRIVATE = [
    # dating / relationships / body
    "dating", "date her", "first date", "girls", "girlfriend", "boyfriend", "get laid", "heartbr", "no contact",
    "ex ", "breakup", "break up", "broke up", "get over", "over her", "over him", "relationship", "situationship",
    "tinder", "hinge", "bumble", "rizz", "seduc", "flirt", "chasing you", "push-pull", "pickup line",
    "testosterone", "ugly", "looksmax", "mewing", "jawline", "libido", "porn", "nofap", "sexual", "lonel",
    "grieve", "grief", "heal ",
    # health / mental health
    "therapy", "adhd", "anxiety", "depression", "vitamin", "biotin", "acne", "hair loss", "collagen",
    "supplement", "ozempic", "steroid", "fat loss", "weight loss", "skincare", "skin care",
    # politics / profanity
    "kamala", "trump", "biden", "election", "retard", "bitch", "fuck", "shit", "dumbass", "asshole", "dickhead",
    # money / personal
    "salary", "my bank",
]

# X topic annotations (record["context"]) that mark a post as private on their own. Empty by default: in practice
# X tags coding posts with debate topics and AI launches with "Sports & Fitness", so they're too noisy to trust.
PRIVATE_CONTEXT: list[str] = []

# words in a theme's name or top terms that keep it off the card
SENSITIVE_THEME_WORDS = [
    "health", "self-improvement", "self improvement", "dating", "relationship", "love", "heartbreak", "breakup",
    "looks", "skin", "testosterone", "fitness", "body", "diet", "therapy", "mental", "politic", "religion",
    "grief", "lonely",
]

DEFAULT_THEME_SHARE = 0.34


def _kw_re(kws):
    return [re.compile(r"(?<![a-z])" + re.escape(k.lower())) for k in kws]


_DEFAULT_RES = _kw_re(DEFAULT_PRIVATE)


def _haystack(rec: dict) -> str:
    parts = [rec.get("text") or ""]
    parts += [q.get("text") or "" for q in rec.get("quoted", [])]
    parts += [l.get("title") or "" for l in rec.get("links", [])]
    return " " + " \n ".join(parts).lower() + " "


def keyword_reason(rec: dict, extra: list[str] | None = None) -> str | None:
    """The first private keyword or topic annotation a bookmark hits, else None."""
    text = _haystack(rec)
    for kw, rx in zip(DEFAULT_PRIVATE, _DEFAULT_RES):
        if rx.search(text):
            return f"keyword “{kw.strip()}”"
    for kw, rx in zip(extra or [], _kw_re(extra or [])):
        if rx.search(text):
            return f"keyword “{kw.strip()}”"
    for c in rec.get("context") or []:
        if any(p in c.lower() for p in PRIVATE_CONTEXT):
            return f"topic “{c}”"
    return None


def is_private(rec: dict, extra: list[str] | None = None) -> bool:
    """Keyword/topic check for a single bookmark (no theme or conversation context)."""
    return keyword_reason(rec, extra) is not None


def _theme_word_hit(words: list[str]) -> str | None:
    for w in words:
        wl = (w or "").lower()
        for s in SENSITIVE_THEME_WORDS:
            if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", wl):
                return s
    return None


def sensitive_themes(themes: list[dict], names: dict, flagged: set[str], hide: list[str] | None = None,
                     share: float = DEFAULT_THEME_SHARE) -> dict[str, str]:
    """Return {theme id: reason} for themes that must stay off the card and whose
    members are kept out of public outputs."""
    hide = [h.lower() for h in (hide or [])]
    out = {}
    for t in themes:
        tid = str(t["id"])
        name = names.get(tid) or ""
        terms = [x.lower() for x in t.get("terms", [])]
        if name.startswith("_"):
            out[tid] = f"named {name}"
        elif tid in hide or name.lower() in hide or any(h.startswith("term:") and h[5:] in terms[:4] for h in hide):
            out[tid] = "listed in _hide"
        elif (w := _theme_word_hit([name] + terms[:5])):
            out[tid] = f"sensitive word “{w}”"
        elif share > 0 and t["members"]:
            frac = sum(1 for m in t["members"] if m in flagged) / len(t["members"])
            if frac >= share:
                out[tid] = f"{frac:.0%} of posts are private-topic"
    return out


class PrivacyFilter:
    """Callable rec -> bool, built once over the whole run."""

    def __init__(self, records: list[dict], extra: list[str] | None = None, clusters: list[dict] | None = None,
                 names: dict | None = None, hide_themes: list[str] | None = None,
                 theme_share: float = DEFAULT_THEME_SHARE):
        self.reasons: dict[str, str] = {}
        for r in records:
            why = keyword_reason(r, extra)
            if why:
                self.reasons[r["id"]] = why
        self.hidden_themes = sensitive_themes(clusters or [], names or {}, set(self.reasons), hide_themes, theme_share)
        for t in clusters or []:
            why = self.hidden_themes.get(str(t["id"]))
            if why:
                for m in t["members"]:
                    self.reasons.setdefault(m, f"in hidden theme ({why})")
        self._propagate(records)

    def _propagate(self, records):
        """A bookmark that quotes/replies to a flagged bookmark is flagged. Bookmarks that quote the same
        post whose text we can't see (deleted, hidden) inherit each other's flag: the missing post is the
        shared context, and it was probably the private part."""
        refs = {r["id"]: {q["id"] for q in r.get("quoted", []) if q.get("id")} for r in records}
        seen_text = {q["id"] for r in records for q in r.get("quoted", []) if q.get("id") and (q.get("text") or "").strip()}
        changed = True
        while changed:
            changed = False
            bad_refs = {q for pid in self.reasons for q in refs.get(pid, ()) if q not in seen_text} | set(self.reasons)
            for pid, qs in refs.items():
                if pid not in self.reasons and qs & bad_refs:
                    hit = next(iter(qs & bad_refs))
                    self.reasons[pid] = f"same conversation as a private-topic post ({hit})"
                    changed = True

    def __call__(self, rec: dict) -> bool:
        return rec["id"] in self.reasons

    def to_json(self) -> dict:
        return {"hidden_themes": self.hidden_themes, "private_ids": self.reasons}

    @classmethod
    def from_saved(cls, path: Path):
        d = json.loads(Path(path).read_text())
        f = cls.__new__(cls)
        f.reasons = d.get("private_ids", {})
        f.hidden_themes = d.get("hidden_themes", {})
        return f


def load_for_run(out: Path, records: list[dict] | None = None):
    """Filter for an existing run dir: privacy.json if the run wrote one, else keyword-only."""
    p = Path(out) / "privacy.json"
    if p.exists():
        return PrivacyFilter.from_saved(p)
    recs = records if records is not None else json.loads((Path(out) / "bookmarks.normalized.json").read_text())
    return PrivacyFilter(recs)
