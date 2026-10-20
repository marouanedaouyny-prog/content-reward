# Windows media process cleanup

The existing source-deadline check failed because `taskkill /T /F` returned
`Access denied`. The original code ignored that exit status and killed only the
parent, leaving downloader descendants alive. Fresh regression checks also
reproduced descendants surviving Pause and successful parent completion.

Windows media commands that need cancellation or process-tree cleanup now use
an unnamed job object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
A small Python launcher waits on a private pipe until it is assigned to that
job; only then can it spawn the requested executable. This prevents children
starting before ownership is established. Closing the job stops its associated
processes on deadline, cancellation, success or unexpected failure. If job
creation or assignment is refused, the target is not started and the workflow
receives an explicit process-management error.

The implementation uses the standard library, with no additional dependency,
elevation, process enumeration or changes to system permissions. The POSIX
process-group path is preserved. Native behavior was checked on this Windows
host with Python 3.11 and 3.14; Linux execution was not checked here.

Microsoft documents automatic association of subsequently created children,
termination when the last kill-on-close job handle closes, and nested jobs on
Windows 8 and later. The job handle is created without inheritance, so the
launcher cannot keep it alive after its supervisor exits. Sources:
[job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[job creation and handle inheritance](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-createjobobjectw),
[process assignment](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject),
[extended limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).

Verification:

- The original deadline regression failed before the fix and passes afterward.
- Added Pause and detached-child regressions failed before implementation.
  Assignment refusal, argument/cwd preservation, stderr feedback and missing
  executable handling are also checked against actual subprocesses.
- Targeted cleanup/download tests: **14 passed** in 9.82 seconds.
- Full clipping suite: **126 passed** in 43.85 seconds, including actual FFmpeg
  rendering, workflow persistence, cancellation, HTTP and browser-script checks.
- Installed Python 3.11 ran a controlled command and separately proved cleanup
  after abrupt supervisor termination; its delayed orphan marker never appeared.
- Python syntax and Docker Compose configuration checks passed.
- The restarted Python 3.11 HTTP workspace prepared and downloaded a new
  five-second synthetic practice clip, verified as 1080x1920 H.264/AAC by
  ffprobe, then completed its saved reviews. Job
  `6b00c025-26e9-4306-9ff5-7ce7a7f9d1e2` has no publication or submission record.
  The downloaded fixture is `.workflow-tests/process-cleanup-practice.mp4`.

Instagram has app configuration but no authorized account token. Outbound
provider probing still fails. This cleanup fix does not establish real source
acquisition, Instagram authorization, publishing or browser visual verification.
