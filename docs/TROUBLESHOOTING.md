# Troubleshooting

## Setup and smoke

Run `.venv/Scripts/content-reward.exe smoke` in a normal PowerShell terminal.
Each check reports a concrete dependency or runtime result. A missing optional
Whisper installation fails its check rather than pretending transcription works.
Install the project extras in the same interpreter used by the launcher. FFmpeg
and ffprobe must be on PATH. Use FFmpeg 9.0 or newer for bounded YouTube section
downloads; older FFmpeg builds can stall when seeking into later source ranges.
Smoke uses temporary isolated DB/media folders and loopback startup; it does not
inspect accounts or download source videos/models.

## Source or network failures

Read `content-reward status` and the saved order ID/reason. Temporary network,
proxy/TLS or rate limits preserve progress and obey finite backoff. Repair the
actual network environment and resume the exact order. Missing public captions or
bounded media access means trying another eligible source or reporting a genuine
shortfall. Never substitute a full download or an old clip for a fresh order.

## Discovery

Run `content-reward discover --niche <name> --dry-run` to see the candidate
pool, the provider outcomes and the diagnostics without changing an order, and
`content-reward discovery-health` for the observed provider health.

- `ALL_PROVIDERS_FAILED` means no provider answered. The report lists the
  providers and queries that were attempted. Repair the network, proxy, TLS or
  the named install and try again; the chain order and the per-provider
  requirements are in [PROVIDERS.md](PROVIDERS.md).
- `NO_SUITABLE_SOURCES` means providers answered but nothing passed the rules.
  The `reason_counts` in the report say why: `duration`, `views`, `age`,
  `live`, `score` or an `*_unknown` reason for missing metadata. An unknown
  transcript state is not a rejection.
- A `PROVIDER_TIMEOUT` means the provider did not answer in time. A hanging
  provider is reported as a timeout and does not block the order.
- A run that used the `relaxed` tier found weaker sources than usual. The tier
  is part of the result, so report it with the selection.
- A source with no publication date, view count or duration is not usable for
  a clip window. It is counted as unknown metadata, not silently dropped.
- Discovery never downloads media and never publishes. A clip still needs
  public captions and a bounded media window from the clip pipeline.

## DB, manifest and resume

The domain DB owns order state. A missing/stale `order.json` or `latest.json`
does not override an existing DB record. Historical import records invalid files
as warnings and waits for busy order locks. If no safe historical order can be
identified, automatic runs fail clearly rather than silently starting over.
Repair malformed historical input from a reviewed backup before importing again.
Never edit a live DB or copy only its main file while WAL writes are active.
Use `Store.backup()` for a consistent snapshot. Pre-migration `.bak` files remain
in ignored local storage. Stale concurrent writers must reload instead of retrying
their old snapshot over a newer revision.

Artifact integrity errors invalidate only necessary stages. Restore the intended
source/transcript, then resume; intact stages are reused. Missing SRT/ASS files
cause a render repair. Changed artifacts invalidate their old review fingerprint.
The same manual-export key can rebuild a deleted package; changed inputs require
a different key and a fresh review.

## Quality failures

Inspect structured QC checks and saved review frames. Corrupt media, audio silence,
black frames, implausible FPS, missing speech, overflowing caption lines and wrong
dimensions must be corrected. FFmpeg decoder errors fail even if ordinary FFmpeg
would otherwise return zero. Captions matching their own ASR are not independent
speech evidence: compare source-reference cues and listen to the actual export.

## Publishing and metrics

READY manual exports are local review files. Missing official API access is an
explicit unavailable capability; no token workaround or browser upload is used.
Existing Instagram verification only verifies the corresponding account access.
No publishing is enabled by setting an environment flag.

Performance import requires a real saved clip ID, nonnegative counters, finite
rates within 0-1, timezone-aware collection time and manual/export provenance.
Do not convert missing metrics to zero. Conflicting data at the same observation
timestamp is rejected. Multiple observations of one clip count once for feedback.
Reported reward observations are distinct from verified payment receipts.

## Supported and legacy tests

Use `python tests/clipping/run_tests.py tests -q` for supported tests. The runner
uses isolated temporary folders compatible with Windows permissions. Root pytest
configuration excludes `legacy/`. Archived tests require their own historical
dependencies and do not establish current runtime correctness.
