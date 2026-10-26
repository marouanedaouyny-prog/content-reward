# Selection retrospective: saved production order 79cc9a45

Audited on 2026-10-22 against the authoritative SQLite order
`79cc9a45-cf13-4248-9789-28e9b90ff6c7` and its stored source excerpts.
This audit does not alter saved orders, source timestamps, media or captions.

The order records 20 completed clips and three rejected candidates. Running the
current strict pre-render candidate assessment against its 20 stored moments
flags five excerpts for editorial correction. The other 15 satisfy these
transcript checks; that does not independently verify speech accuracy or predict
viewer response. The historical mechanical export reviews remain historical
evidence and do not replace these structural checks.

| Clip | Source | Saved interval (seconds) | Flag | Transcript evidence |
|---|---|---|---|---|
| 10 | `VkE3ibwrfSs` | 459.440–493.199 | Context-dependent opening | “He hasn't spoken since he left Manchester United.” The clip does not identify the person in its opening. |
| 11 | `VkE3ibwrfSs` | 1686.240–1722.799 | Context-dependent opening | “That's all positive from Tenhog on the current boss Michael Carrick.” The opening summarizes unseen preceding remarks. |
| 14 | `VkE3ibwrfSs` | 1124.720–1164.320 | Host setup | “We've got another voice note. This one's from Jacob.” Host administration precedes the useful point. |
| 17 | `VkE3ibwrfSs` | 1262.199–1282.400 | Unanswered ending | The last sentence is “What would that do to your mindset and your teammates?” The selected window stops before an answer. |
| 18 | `VkE3ibwrfSs` | 1733.440–1754.559 | Context-dependent opening | “I suppose he wasn't there either, was he?” The opening relies on an unidentified person and prior context. |

The updated gates recognize contracted pronouns, contextual summaries and voice
note setup, and reject unanswered final questions even when old saved flags say
the punctuation completes a thought. Complete question-and-answer excerpts,
explicit named subjects and self-contained impersonal hooks remain eligible.
These are conservative transcript heuristics; a human editor still decides the
best replacement window and confirms it against the actual audio and picture.

The public source transcript also contains name variations such as “Tenhog”.
Agreement between generated subtitles and those public cues cannot establish the
correct spelling of a name or perfect speech accuracy.

At the time of this audit the domain database contained 31 normalized clips,
zero performance observations, zero experiments and zero publication records.
There is no measured outcome evidence here to establish which clips became
popular or whether a ranking change improved retention or follower conversion.

Regression coverage lives in `tests/clipping/test_planning.py`,
`tests/unit/test_quality.py` and `tests/unit/test_selection.py`. It exercises
these past excerpt patterns, complete alternative hooks, strict missing-evidence
handling, configured growth ranking before overlap pruning and bounded supported
feedback before the candidate limit.
