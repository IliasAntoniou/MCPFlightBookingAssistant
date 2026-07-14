# Cache Benchmark Analysis — Exact vs. Similarity Caching

Analysis of the MCP flight-booking agent (Ollama/Llama backend) comparing a
no-cache baseline against a combined exact + semantic-similarity cache. Intended
as a results section for a thesis on semantic caching of LLM-agent responses.

## 1. Experimental setup

- **Workload:** `flight_queries_100_unique_each_duplicated.csv` — 100 unique
  natural-language flight-search queries, each immediately repeated verbatim,
  for 200 sequential requests.
- **Query template:** `search all flights from <Origin> to <Destination> in <YYYY-MM-DD>`
  over ~20 European airports.
- **Pipeline per query:** (1) LLM tool-decision, (2) MCP tool / DB lookup,
  (3) LLM final-answer formation.
- **Similarity cache configuration:** embedding model **all-mpnet-base-v2**,
  cosine-similarity threshold **0.99**. The 0.99 threshold was selected because
  it maximised the **F0.5** score for this model on the **QQP** duplicate-detection
  dataset, i.e. it is tuned to favour *precision* (avoiding false cache hits).
- **Conditions:**
  - `duplicated_results_no_cache.csv` — caching disabled (baseline).
  - `duplicated_results_both_cache.csv` — exact + similarity cache enabled.
- **Hit classifier (for analysis):** `total_latency_seconds < 1.0`. The
  distribution is sharply bimodal (hits ~0.05 s, misses ~7 s), so the cut is
  unambiguous.

## 2. Aggregate results

| Metric | No cache | Both caches |
|---|---|---|
| Total wall-clock (200 queries) | **1423.1 s** | **535.0 s** |
| Mean latency / query | 7.115 s | 2.675 s |
| Median (p50) latency | 7.031 s | **0.063 s** |
| p95 latency | 7.690 s | 7.382 s |

- **Overall wall-clock reduction: 62.4 %** (2.66× throughput).
- **Per-hit speedup: ~139×** (mean hit 0.051 s vs. mean baseline 7.115 s).
- **Negligible overhead on a miss:** 7.048 s with the cache enabled vs. 7.115 s
  baseline — the lookup is essentially free when it does not fire.

## 3. Where the time goes (per-phase mean latency, seconds)

| Phase | No cache | Cache miss | Cache hit |
|---|---|---|---|
| LLM tool-decision | 3.299 | 3.340 | 0.051 |
| MCP tool / DB pipeline | 0.017 | 0.015 | 0.000 |
| LLM answer-formation | 3.806 | 3.794 | 0.000 |
| **Total** | **7.115** | **7.048** | **0.051** |

The two LLM phases account for ~99.8 % of latency; the actual tool/DB work is
~17 ms. **The cache's entire benefit is avoided LLM inference, not avoided
database work** — the central argument for response-level caching in an LLM agent.

## 4. Cache-hit decomposition — exact vs. similarity

Total hits: **125 / 200 (62.5 %)**.

| Hit source | Count | What it caught |
|---|---|---|
| **Exact cache** | 100 | All 100 verbatim repeats (2nd occurrence) — 100 % recall on exact duplicates |
| **Similarity cache** | 25 | First-occurrence queries matched (cos ≥ 0.99) to an *earlier, differently-worded* query |

The exact cache is a perfect, safe win on repeated traffic. The similarity cache
*adds* 25 hits the exact cache could never catch (a +25 % first-occurrence hit
rate), which is where the "semantic" benefit shows up. Among the 125 hits, **75
distinct cached replies** were served — far from the degenerate "everything maps
to one entry" failure mode, confirming that the strict 0.99 threshold keeps the
cache mostly discriminating.

## 5. Correctness cost of the similarity cache ⚠️

The exact-cache hits are correct by construction (identical query → the answer
its own first occurrence produced): **100/100 correct.**

The 25 similarity hits are the risk surface. Parsing the route out of each
returned reply and comparing it to the query's route:

| Outcome | Count | Notes |
|---|---|---|
| **Wrong route returned** | 8 | All 8 are **origin↔destination reversals** |
| Correct route | 2 | Matched an earlier same-route query |
| Undetermined from reply | 15 | Reply was a generic error (e.g. "can't search past date") that does not restate a route in the preview; answer still came from a *different* query |

Concrete wrong hits (query → served reply route):

- `Frankfurt → Berlin` → **`Berlin → Frankfurt`**
- `Munich → Zurich` → **`Zurich → Munich`**
- `Helsinki → Frankfurt` → **`Frankfurt → Helsinki`**
- `Barcelona → Munich` → **`Munich → Barcelona`**
- `Berlin → London` → **`London → Berlin`**

**Key insight:** even at a precision-tuned 0.99 threshold, all of the detectable
similarity errors are **route reversals**. Sentence embeddings such as
all-mpnet-base-v2 are largely word-order / direction insensitive, so *A→B* and
*B→A* — which share an identical token set — land above 0.99 cosine and collide.
The single most semantically important attribute of a flight query (its
direction) is exactly the one the embedding underweights.

## 6. Thesis takeaways

1. **Response caching is highly effective on latency:** 62 % wall-clock
   reduction, ~139× per-hit speedup, with no measurable penalty on misses.
2. **The benefit is inference-avoidance, not I/O-avoidance:** ~99.8 % of latency
   is LLM time; the DB call is ~17 ms.
3. **Exact vs. similarity is a precision/recall trade-off.** Exact caching: 100 %
   precision but fires only on identical input (100/200). Adding similarity
   caching at 0.99 raised the hit rate to 125/200 and, unlike a looser threshold,
   *avoided wholesale over-matching* (75 distinct replies served) — yet it still
   produced incorrect answers, dominated by **origin↔destination reversals**.
4. **A QQP-optimal threshold does not transfer to a parameter-bearing agent
   workload.** 0.99 maximised F0.5 on QQP sentence pairs, but flight queries are
   near-identical templates differing only in slots (origin / destination / date)
   that embeddings weight weakly; the operating point that is "high precision" on
   QQP is still unsafe here.
5. **Implication / mitigations to discuss:** key the cache on extracted slots
   (origin, destination, date) rather than raw-text embeddings; add an asymmetric
   or order-sensitive signal so reversed routes do not collide; or use similarity
   only to *retrieve a candidate* and then verify slot-equality before reuse.

---

### Reproduce the numbers

```python
import pandas as pd, numpy as np, re
no = pd.read_csv("duplicated_results_no_cache.csv")
bo = pd.read_csv("duplicated_results_both_cache.csv")
print("reduction:", 1 - bo.total_latency_seconds.sum()/no.total_latency_seconds.sum())
bo["hit"] = bo.total_latency_seconds < 1.0
bo["occ"] = np.where(bo.query_id % 2 == 1, "first", "repeat")  # first=miss expected, repeat=exact dup
print(pd.crosstab(bo.occ, bo.hit))          # exact vs similarity decomposition
print("distinct replies among hits:", bo[bo.hit].reply_preview.nunique())
```
