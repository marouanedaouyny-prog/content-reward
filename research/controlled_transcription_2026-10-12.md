# Controlled transcription and empty-speech recovery

The automatic clipping path previously loaded and ran Whisper in the queue
worker. Its model initialization and segment generation did not consult Pause,
cancellation or shutdown and had no deadline. An empty automatic transcript also
raised a generic validation error, failing the job instead of allowing its SRT
handoff.

Optional CPU/int8 inference now runs in `clipping/_transcribe.py`, launched with
the app's Python executable and isolated import mode. The existing owned-process
runtime applies Pause, cancellation, shutdown and a 30-minute deadline, including
model loading and any attempted model download. The queue worker validates the
child's language, text and timestamps before writing a transcript checkpoint.
Interrupted inference propagates its interruption state; expired attempts,
missing dependencies, invalid results and no detected speech request a real
timed SRT. No inferred text is saved before successful validation. Existing
manual/practice transcript origins and campaign approval gates are preserved.

The inference calls follow the installed faster-whisper 1.0.3 contract: CPU/int8
model loading, language selection, VAD and iteration of the segment generator.
The generator performs transcription during iteration, which is why both loading
and collection belong in the controlled process. See the
[official versioned usage documentation](https://github.com/SYSTRAN/faster-whisper/tree/v1.0.3#usage).

Seven new regressions failed before the change. They cover Pause before
inference, interruption during owned processing, deadlines, empty speech and
invalid result boundaries/text/language. Further checks cover source-checkpoint
preservation and SRT recovery, Unicode serialization and safe worker errors.
The focused transcription/automation/process suite returned **30 passed** in
13.80 seconds. The full clipping suite returned **154 passed** in 45.69 seconds:

```powershell
python tests/clipping/run_tests.py tests/clipping -q --tb=short
```

An audible 45-second private excerpt from an older local video decoded to
720,000 samples at 16 kHz with RMS 0.132. The cached English model returned zero
segments with VAD. Disabling VAD as a diagnostic produced 12 segments, but this
did not establish their correctness and VAD remains enabled in the product.
Windows refused the initially attempted local voice-synthesis fixture. No
speech-recognition accuracy claim is made for this excerpt or for IShowSpeed.

The installed Python **3.11.15** runtime independently confirmed the empty-speech
SRT handoff in 2.69 seconds and interruption of the owned transcription attempt
in **0.53 seconds**, without a partial transcript checkpoint. Repeatable native
verification is `.workflow-tests/transcription-native-smoke.py` with its JSON
record at `.workflow-tests/transcription-native-verification-2026-10-12.json`.

The requested actual IShowSpeed preview still awaits source access. No alternate
footage was substituted into that job, and no publication or reward submission
was performed. The broader project goal remains active.
