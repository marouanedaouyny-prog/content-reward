# YouTube scraper correction — 2026-10-14

The public discovery command used `ytsearchdate8:`. The installed yt-dlp
2026.08.19 does not recognize that search mode. A native command check failed
with an invalid-URL error, before a proxy connection was attempted. The old
adapter converted every command error into a temporary connection failure,
causing misleading status messages and repeated retries of an invalid command.

`clipping/trends.py` now uses supported `ytsearch8:`. This obtains a bounded
relevance sample; inspected publication metadata still enforces the existing
14-day source window and duration eligibility. It does not claim date-sorted
search results. Actual proxy refusal, connection failure, rate limiting and
timeouts remain retryable. Invalid commands and malformed JSON fail with safe
setup guidance instead of indefinite connection retries. Provider error text is
not copied into research reports.

The regression checks now validate the emitted command against yt-dlp's actual
search extractor, distinguish unsupported-command failure from proxy refusal,
and verify that neither state creates a substitute clip or exposes provider text.

Fresh verification:

- **155 clipping tests passed; one Instagram UI test deselected**, in 42.65 seconds.
  The four Instagram-specific Python modules were excluded as previously requested.
- Native Python 3.11: old search mode rejected; corrected mode recognized.
- Native corrected discovery reached the search operation and returned
  `DiscoveryUnavailable` with the safe connection-unavailable message.
- YouTube remains unreachable through this session's inherited proxy. No proxy
  settings, execution identity or network restrictions were changed.
- There is still no downloaded long source in project storage, and no real
  YouTube highlight or spoken-caption result has been produced.

```powershell
python tests/clipping/run_tests.py tests/clipping --ignore=tests/clipping/test_instagram.py --ignore=tests/clipping/test_instagram_oauth.py --ignore=tests/clipping/test_instagram_tunnel.py --ignore=tests/clipping/test_instagram_token.py -k 'not instagram' -q --tb=short
```

The normal-terminal launcher remains `start-youtube-clipping.cmd`. It delegates
to `start-youtube-clipping.ps1`, checks the runtime and installs the matching
YouTube solver if needed. The workspace has been left stopped so this launcher
can own port 8000 without a competing worker in the restricted tool environment.

Primary reference: [yt-dlp search extractor and supported search key](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/youtube/_search.py).
