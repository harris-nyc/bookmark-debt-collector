"""Theme discovery: embed -> k-means (k by silhouette) -> c-TF-IDF labels.

The recipe is the retrieval half of a recommender, shrunk to one user:

  1. Document = post text + quoted post text + link titles + X topic annotations
  2. Vectors, two interchangeable backends:
     * "embed" (default when `fastembed` is installed): BAAI/bge-small-en-v1.5,
       a 33M-param sentence embedding model that runs locally on CPU via ONNX.
     * "tfidf" (zero extra deps): TF-IDF (1-2 grams, sublinear tf) -> TruncatedSVD
       (LSA) to <=12 dims. Cheaper, noticeably worse on short posts.
     Both are L2-normalised so k-means approximates cosine (spherical) clustering.
  3. k-means for k in [k_min, k_max]; keep the k with the best cosine silhouette.
  4. Label each cluster BERTopic-style: top terms of the cluster's TF-IDF
     centroid ("class-based TF-IDF"), so labels are readable even when vectors
     are dense embeddings.

A Grok Bot (or you) can then rename clusters into human theme names via
theme_names.json. Everything downstream only needs `labels` and `themes`.
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize as l2

from .normalize import clean_text

EXTRA_STOP = {
    "https", "http", "amp", "just", "like", "really", "im", "dont", "people", "think", "thing", "things",
    "know", "going", "get", "got", "make", "way", "say", "said", "want", "need", "actually", "lot",
    "new", "good", "great", "time", "years", "year", "today", "day", "week", "weeks", "100",
    "ve", "ll", "re", "don", "doesn", "isn", "didn", "won", "let", "use", "using", "used", "post",
    "yes", "did", "does", "doing", "come", "came", "look", "best", "better", "big", "bigger",
}
STOP = list(ENGLISH_STOP_WORDS | EXTRA_STOP)


def document(rec: dict) -> str:
    parts = [clean_text(rec["text"])]
    parts += [clean_text(q.get("text") or "") for q in rec.get("quoted", [])]
    parts += [l["title"] for l in rec.get("links", []) if l.get("title")]
    parts += [c for c in rec.get("context", []) if len(c) < 40]
    doc = " ".join(p for p in parts if p)
    doc = re.sub(r"@\w+", " ", doc)          # handles are authors, not topics
    doc = re.sub(r"\$([A-Za-z]{2,5})", r"\1", doc)
    return doc


EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def _embed(docs: list[str]):
    try:
        from fastembed import TextEmbedding
    except ImportError:
        return None
    import logging
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    m = TextEmbedding(EMBED_MODEL)
    return l2(np.array(list(m.embed(docs))))


def discover(records: list[dict], k_min: int = 5, k_max: int = 10, seed: int = 42, backend: str = "auto",
             k: int | None = None) -> dict:
    docs = [document(r) for r in records]
    n = len(docs)
    if n < 6:
        return {"labels": [0] * n, "themes": [{"id": 0, "terms": [], "size": n, "members": [r["id"] for r in records]}],
                "k": 1, "silhouette": None, "method": "too few bookmarks to cluster"}
    vec = TfidfVectorizer(stop_words=STOP, ngram_range=(1, 2), min_df=2, max_df=0.4, sublinear_tf=True,
                          token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9+.-]{1,}\b")
    X = vec.fit_transform(docs)
    Z = _embed(docs) if backend in ("auto", "embed") else None
    if Z is None and backend == "embed":
        raise SystemExit("backend=embed needs `pip install fastembed`")
    if Z is not None:
        vec_desc = f"{EMBED_MODEL} embeddings (384d, local)"
    else:
        dims = max(2, min(12, X.shape[1] - 1, n - 1))
        Z = l2(TruncatedSVD(n_components=dims, random_state=seed).fit_transform(X))
        vec_desc = f"TF-IDF({X.shape[1]} terms) -> LSA({dims}d)"
    k_min, k_max = (k, k) if k else (k_min, k_max)

    best = None
    for kk in range(min(k_min, max(2, n // 4)), max(2, min(k_max, n // 4)) + 1):
        km = KMeans(n_clusters=kk, n_init=20, random_state=seed).fit(Z)
        sc = silhouette_score(Z, km.labels_, metric="cosine")
        if best is None or sc > best[0]:
            best = (sc, kk, km.labels_)
    sil, k, labels = best

    terms = np.array(vec.get_feature_names_out())
    global_mean = np.asarray(X.mean(axis=0)).ravel()
    themes = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        centroid = np.asarray(X[idx].mean(axis=0)).ravel() - 0.5 * global_mean  # distinctive, not just frequent
        order_t = centroid.argsort()[::-1]
        top = [terms[j] for j in order_t[:12] if centroid[j] > 0]
        # drop unigrams already covered by a chosen bigram
        chosen = []
        for t in top:
            if any(t in c2.split() for c2 in chosen if " " in c2):
                continue
            chosen.append(t)
        # exemplars = members closest to the cluster centre
        zc = Z[idx].mean(axis=0)
        order = idx[np.argsort(-(Z[idx] @ zc))]
        themes.append({"id": int(c), "terms": chosen[:6], "size": int(len(idx)),
                       "members": [records[i]["id"] for i in order]})
    themes.sort(key=lambda t: -t["size"])
    return {"labels": [int(x) for x in labels], "themes": themes, "k": int(k), "silhouette": round(float(sil), 3),
            "method": f"{vec_desc} -> k-means(k={k}, cosine silhouette={sil:.3f}) -> c-TF-IDF labels",
            "vectors": Z}


def theme_name(theme: dict, names: dict | None) -> str | None:
    """Look up a human name for a theme. Keys can be a cluster id ("3") or
    "term:<word>" which matches if <word> is among the theme's top terms
    (robust across backends/re-runs)."""
    names = names or {}
    if str(theme["id"]) in names:
        return names[str(theme["id"])]
    for key, val in names.items():
        if key.startswith("term:") and key[5:].lower() in [t.lower() for t in theme.get("terms", [])[:4]]:
            return val
    return None


def resolve_names(themes: list[dict], names: dict | None) -> dict[str, str]:
    """Map cluster id -> name (falls back to top terms)."""
    return {str(t["id"]): theme_name(t, names) or " · ".join(t["terms"][:3]) or "misc" for t in themes}
