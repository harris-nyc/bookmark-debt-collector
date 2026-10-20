# Theme clustering

Goal: group ~100 short posts into 5-10 themes a human would recognise, on a laptop, in seconds, with no API calls.

## Pipeline (`src/bdc/cluster.py`)
1. **Document** per bookmark = post text (full long-post text) + quoted post text + link titles + X's own topic
   annotations (`context_annotations`, e.g. "Artificial intelligence"). @handles and t.co links are stripped.
2. **Vectors**, two interchangeable backends:
   - `embed` (default if `fastembed` is installed): `BAAI/bge-small-en-v1.5`, a 33M-parameter sentence embedding model,
     run locally on CPU via ONNX. 384-d, L2-normalised.
   - `tfidf` (no extra deps): TF-IDF (1-2 grams, sublinear tf, min_df=2, max_df=0.4) → TruncatedSVD/LSA (≤ 12 dims) →
     L2-normalised.
3. **k-means** (20 restarts, fixed seed) for k in 5..10 (capped at n/4), keeping the k with the best **cosine
   silhouette**. With L2-normalised vectors this approximates spherical k-means.
4. **Labels**, BERTopic-style class-based TF-IDF: average the TF-IDF vectors of a cluster's members, subtract half the
   corpus mean (so labels are distinctive, not just frequent), take the top terms. Labels stay readable even when the
   clustering was done in dense embedding space.
5. **Names**: the bot (or you) turns `["inference", "vllm", "kv", ...]` into "Inference & serving" in
   `theme_names.json`. Keys can be the cluster id or `term:<word>` (matches if the word is in the theme's top 4 terms),
   which survives re-runs. A name starting with `_` hides the theme from the card, and so does listing it under
   `"_hide"`. Sensitive themes are also hidden automatically ([privacy](privacy.md)).

## Why this design
- **Retrieval-style features**: this is the candidate-generation half of a recommender, scaled down to one user.
  Embeddings for semantic similarity, TF-IDF for interpretable labels.
- **Short-text reality**: on a real set of 96 bookmarks, TF-IDF+LSA at 40 dims put 69 posts in one blob. At ~10 dims
  the cluster sizes balanced out but the clusters mixed unrelated posts (chip-demand takes next to code-review takes).
  bge-small gave 9 coherent themes (inference & compute, AI business, Grok Bot builders, code review, ...). So:
  embeddings by default, TF-IDF as the zero-dependency fallback.
- **Silhouette depends on the space**: TF-IDF+LSA scores much higher (~0.4) than embeddings (~0.1) on the same data
  because low-dim LSA spaces are "clumpier", not because its clusters are better. Compare silhouettes only within a
  backend.
- **Silhouette is used to choose k, not as a quality claim.** The real check is reading the members of each cluster, which `themes.json` lists, ordered by closeness to the
  centre.
- **Known gaps**: bge-small is English-first, so non-English posts tend to land together or in a "misc" cluster. Swap in
  a multilingual model (e.g. `paraphrase-multilingual-MiniLM-L12-v2`) via `EMBED_MODEL` if that matters to you.
