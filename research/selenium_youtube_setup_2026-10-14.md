# Selenium discovery integration — 2026-10-14

The user's Selenium 4.45.0 installation is available to `C:/Python314/python.exe`.
It is not installed in the clipping Python 3.11 virtual environment. The browser
adapter now uses the existing system installation; transcription and FFmpeg
rendering continue in the project environment.

From normal PowerShell:

```powershell
Set-Location -LiteralPath "C:\Users\hp\Desktop\New folder\content rewerad"
.\start-youtube-clipping.ps1 -Selenium -BrowserPython "C:\Python314\python.exe"
```

`start-youtube-clipping.cmd` selects the same Selenium mode. Its launcher checks
the supplied Python, starts a public YouTube readiness check, and then prepares
the downloader and starts the search-to-one-captioned-clip workflow.

Implementation:

- `clipping/youtube_browser.py` runs an isolated Chrome session and reads public
  search/watch metadata. It keeps at most eight source IDs per niche, supports
  renderer data and a DOM link fallback, omits signed stream URLs and cookies,
  and retains exact counts/durations or unknown values. Publication dates are
  passed to existing source eligibility. One unavailable watch page does not
  discard other inspected results.
- The browser and Selenium Manager preserve inherited HTTP/HTTPS proxies.
  Authenticated or unsupported proxy configurations fail safely. No personal
  Chrome profile is reused, and no browser security switches are disabled.
  Driver cache and isolated temporary profiles stay inside the project.
- `clipping/trends.py` invokes the configured browser Python as an owned process
  with a three-minute deadline and consumes a bounded JSON metadata response.
  Selenium mode takes precedence over optional API discovery and starts a fresh
  scan when the provider changes. Existing eligibility, ranking, one-job
  idempotency, real-audio transcription and burned-in captions remain in use.
- The workspace displays **Chrome browser search · Selenium** and preserves
  unknown durations instead of displaying zero minutes.

Fresh checks:

- **166 clipping tests passed; one Instagram UI test was deselected**, in 44.25
  seconds. The four Instagram-specific Python test modules were excluded.
- The actual system Python imports Selenium 4.45.0. The actual clipping Python
  3.11 has no Selenium dependency and can invoke the browser helper separately.
- PowerShell launcher parsing completed with zero errors; port 8000 is free.
- The native browser readiness command returned `setup_blocked` with
  `driver_or_browser_unavailable`. Inspection of its exception chain confirmed
  `NoSuchDriverException`, caused by a driver-download request error, without a
  permission-denied error. No Chrome session or YouTube page was verified.
- The actual PowerShell launcher recognizes the installed Selenium and reports
  the blocked driver setup before starting the app or manufacturing any clip.

These tests verify parsing, provider handoff, failure handling and existing
clipping behavior with fixtures. Real public-page extraction, live video
download, replay data and caption accuracy still require the normal-terminal
run. There is no new real clip artifact yet. The workspace is left stopped so
the normal-terminal worker can own port 8000.

References: [Selenium Manager driver management](https://www.selenium.dev/documentation/selenium_manager/),
[proxy and cache configuration](https://www.selenium.dev/documentation/selenium_manager/#configuration),
and [Chrome options](https://www.selenium.dev/documentation/webdriver/browsers/chrome/).
