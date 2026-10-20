# Trending discovery and optional AI tools

Researched 2026-10-10 from upstream repositories, vendor pages, Google documentation, and the original GEO paper. This assessment concerns the Content Rewards clipping workflow. Integration suggestions below are engineering judgments, not validated performance claims. No tool was installed and no authenticated API request or live download benchmark was run for this research.

## Recommendation

Prioritize fresh source discovery, visible source dates and popularity metrics, transcript-based moment selection, and reliable resumable downloads. Consider Laya only after measuring a text-classification bottleneck. Keep MiroFish as an optional audience-research experiment. Apply GEO if the project later publishes searchable web pages. None of these tools supplies evidence that a chosen clip will go viral or earn a reward.

## What the names identify

| User's name | Verified identity | Potential role | Prerequisites / decision |
| --- | --- | --- | --- |
| Laya AI | [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya): a local text decision model with typed `choice`, `score`, and `noul` outputs. | Experimental topic tagging, transcript relevance checks, or choosing which model reviews a candidate. | Python 3.10+, PyTorch/Transformers, checkpoint download, memory budget, and evaluation on real clip decisions. |
| GEO | If this means **generative engine optimization**, the [original paper](https://arxiv.org/abs/2311.09735) studies improving web content visibility in generative search responses. | Later improve searchable campaign pages, clip transcripts, and creator pages. | A public indexed content surface and measurement of search/citation visibility. The acronym alone does not identify a specific service. |
| MiroFish | [666ghj/MiroFish](https://github.com/666ghj/MiroFish): multi-agent social simulation from seed documents, graph building, personas, and generated reports. | Optional brainstorming about audience objections, headline variants, or alternative interpretations. | Node 18+, Python 3.11-3.12, uv; LLM API and Zep Cloud credentials in its current quick start. |

**Laya remains ambiguous.** Its upstream decision model is distinct from the [LAYA AI agency](https://growlaya.com/about), which offers marketing, analytics, and video services. Also, [laya-ai.com](https://laya-ai.com/) explicitly identifies itself as an independent community site, unaffiliated with the upstream developer. Confirm the intended repository or product URL before adopting any integration.

The Laya repository documents short default context budgets (512 tokens for English, 1,024 for the other listed checkpoints), so a full video transcript needs bounded windows. The upstream confidence-gating example requires thresholds fitted and validated on the user's own held-out data. Its general decision-model probabilities are not probabilities of virality. Suggested application: label candidate transcript windows against a small, explicit rubric, compare results with reviewer decisions, and retain human review for uncertain cases. [Upstream Laya documentation](https://github.com/NandhaKishorM/laya)

The GEO paper evaluates visibility in generated search answers, rather than short-video retention or recommendation feeds. Therefore GEO is not a replacement for footage discovery, downloading, editing, or social performance feedback. A particular commercial tool called Geo could be something else; its URL is needed to assess it. [Original GEO paper](https://arxiv.org/abs/2311.09735)

MiroFish's README describes scenarios and reports, and warns that simulations can consume substantial LLM usage. The current example configuration includes LLM and Zep keys. Treat synthetic agents' reactions as hypotheses to test against real viewers; this assessment found no validated clip-specific viral-prediction benchmark in the reviewed README. Introducing its graph, simulation, and reporting services into every clipping job adds infrastructure without demonstrated workflow benefit. [MiroFish README](https://github.com/666ghj/MiroFish), [example configuration](https://github.com/666ghj/MiroFish/blob/main/.env.example)

## Fresh YouTube discovery

1. **Official charts:** `videos.list(chart=mostPopular, regionCode=..., videoCategoryId=...)` returns an official popularity chart. Since **July 21, 2025**, this reflects Trending Music, Movies, and Gaming rather than the former broad Trending Now list. Do not describe this as complete trending coverage for every niche. [Videos API](https://developers.google.com/youtube/v3/docs/videos/list), [July 2025 revision](https://developers.google.com/youtube/v3/revision_history)
2. **Niche discovery:** use `search.list(type=video, q=..., publishedAfter=..., order=...)`, then retrieve `videos.list(part=snippet,statistics,contentDetails, id=...)` for source metadata and duration. Search supports dates, language hints, and region availability; `order=viewCount` sorts by total views, not growth rate. Non-relevance sorts and date filters can return incomplete results. For monitored creator channels, Google recommends their uploads playlist over search for recent uploads. [Search API](https://developers.google.com/youtube/v3/docs/search/list), [video retrieval guide](https://developers.google.com/youtube/v3/guides/implementation/videos)
3. **Freshness and ranking, proposed:** timestamp observations, distinguish a fresh request from cached results, display observed views and publication time, and use recent view increments only when there are at least two snapshots. Views divided by age is an average activity proxy, not measured recent acceleration. Rank against the campaign's niche and permitted sources before downloading. Label editorial recommendations as heuristics.

Official API prerequisites are a Google Cloud project, enabled YouTube Data API, and authorization credentials. Current `search.list` documentation reports a separate Search Queries quota bucket with 100 default calls per day and one unit per call; earlier 100-unit search-cost advice is stale. Cache brief results, bound pagination, and consult the project's actual quota. [API setup](https://developers.google.com/youtube/v3/getting-started), [current search quota](https://developers.google.com/youtube/v3/docs/search/list)

An alternative adapter can use yt-dlp's documented `ytsearch:` support. Label it search-derived discovery, record observation timestamps, and handle missing metadata. [yt-dlp search support](https://github.com/yt-dlp/yt-dlp#new-features)

## Download improvements grounded in yt-dlp

The maintainers document `--concurrent-fragments` for DASH and native HLS, defaulting to one worker; it does not accelerate every protocol. Resume (`--continue`) and `.part` files are defaults. HTTP and fragment retries default to ten, and retry sleeps can use exponential backoff. Unavailable fragments are skipped by default; `--abort-on-unavailable-fragments` avoids silently accepting a gap. [yt-dlp options](https://github.com/yt-dlp/yt-dlp#usage-and-options)

Proposed policy: start with four fragment workers, finite retries, capped backoff, stable partial paths, and progress reporting. Preserve partials after retryable failures. Measure bytes, elapsed time, protocol, and retries before claiming higher throughput; reduce concurrency if errors increase. Reuse valid footage and download only selected candidates.

Embedded Python option names include `concurrent_fragment_downloads`, `continuedl`, `retries`, `fragment_retries`, and `retry_sleep_functions`; the latter maps retry types to functions returning sleep seconds. [Upstream Python API source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py)

Known moments can use `--download-sections` with ffmpeg; forced keyframes require slower re-encoding. Benchmark range downloads separately, and preserve original source timestamps. [yt-dlp range and keyframe options](https://github.com/yt-dlp/yt-dlp#usage-and-options)

## Evidence limits

The verified sources establish the tools' purposes and supported controls. They do not establish that Laya understands the project's clip rubric, that MiroFish predicts real viewers, that GEO improves Shorts distribution, or that four download workers are faster on this machine. Validate those questions with actual reviewer outcomes and timing measurements before making them product claims. These optional tools should not become prerequisites for the core discovery-to-review workflow.
