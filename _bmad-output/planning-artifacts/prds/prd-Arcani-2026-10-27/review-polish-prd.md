# Editorial Review: Arcani PRD (polish pass)

- **Target:** `prd.md` (5,924 words before edits)
- **Lenses:** structure, then prose (bmad-review, reader type: humans, style guide: Microsoft Writing Style Guide)
- **Date:** 2026-10-27

**Purpose read:** this document exists to help Audio and the downstream BMAD agents (architecture, epics and stories, test design) build and verify Arcani in phases, starting with v0.1, with every requirement traceable to an ID and a source.

**Structure model:** Strategic/Context (Pyramid). The document already leads with purpose and vision, groups requirements by feature, and closes with phases, success checkpoints, risks, open questions, and assumptions. The shape fits the purpose; the findings below are local.

**Hard constraints held:** no change to meaning, numbers, thresholds, FR/UJ/SC IDs or their order, glossary substance, decisions, or cross-references; no requirement added or removed; frontmatter untouched; no em dashes; no banned terms.

## Structure pass

None of these were applied: each would move, merge, cut, or add scaffolding, so each is left for Audio to decide.

| Pass | Original Text | Revised Text | Changes |
| --- | --- | --- | --- |
| structure | §3 Glossary, term order (614 words) | MOVE: order terms dependency-first (Carrier, Rate, AM, Engine clock, Spectral component, then the layers, rules, and process terms) | "Spacing rule" uses "spectral component" before it is defined, near the end of the list. Reordering avoids a forward reference. No word change. |
| structure | §4.1 "Notes" paragraph after FR-6 (proposed gamma rate and coupling phase defaults) | MOVE: to sit after the FR-8 locked ranges table, or fold into §11 Q4 | Default values are recipe parameters, not engine-core behavior; readers looking for defaults will look beside the ranges. About 40 words relocated, none saved. |
| structure | §6 "No summing" | MERGE into FR-4 bullet "The engine never sums or downmixes its output channels", or reduce §6 to a pointer | Same rule stated twice. PRESERVE is also reasonable: §6 is the guardrail list and this is the exact failure that broke an earlier project. Saves about 25 words if merged. |
| structure | §6 "Privacy" (one line) | MERGE into FR-38, or keep as a pointer | Only restates FR-38. Saves about 6 words. |
| structure | §6 "Hearing safety" and §5 Hearing safety row | PRESERVE | Overlap is intentional: §5 sets the measurable bar, §6 sets the guardrail and listener guidance. |
| structure | §7 "No coupling to a binaural beat, ever." | PRESERVE | Repeats FR-3 and FR-4, but a non-goal list is where a downstream agent checks scope; the reinforcement earns its place. |
| structure | FR-29 looping bullet and FR-7 maximum run time | PRESERVE | Same rule from the recipe side and the listener side; each serves a different story. |
| structure | §4.10 Accounts, monetization, analytics | QUESTION: add a one-line Description and "Realizes" line like other feature groups | Every other group except §4.8 has one; §4.10 has none and no UJ traces to it. Not applied because it would add text that implies new traceability. |
| structure | §11 Q10 (sham-controlled EEG pilot) | QUESTION: name the gate it blocks | The section intro says each question names its gate; Q10 does not. Not applied because choosing a gate is a decision. |
| structure | Heading case: H2s in title case ("Cross-Cutting NFRs", "Jobs To Be Done"), H3 feature headings in sentence case | QUESTION: pick one (Microsoft style uses sentence case) | Not applied because other documents may link to these headings by text. |

**Structure summary:** 10 recommendations (4 MOVE/MERGE, 3 PRESERVE, 3 QUESTION). If both merges are accepted, the reduction is about 31 words (0.5 percent). No length target was given. No comprehension trade-off: the merges remove pure repetition only.

## Prose pass

Voice noted and preserved: terse, declarative requirement statements; bullet fragments inside FR acceptance lists; the plain "Honesty note" voice; US spelling; number-dense technical register.

All rows below were applied to `prd.md`.

| # | Pass | Original Text | Revised Text | Changes |
| --- | --- | --- | --- | --- |
| 1 | prose | UJ-1: "the gamma carrier is under 4 times the gamma rate" | "the gamma PAC carrier is under 4 times the gamma rate" | Glossary term, matching the FR-8 table. |
| 2 | prose | UJ-3: "opens Arcani in bed with no signal" | "with no network connection" | "Signal" is a technical term in this document; removes the ambiguity. |
| 3 | prose | §3 Theta reference: "The only thing PAC couples to." | "It is the only thing PAC couples to." | Completes the fragment, matching CLAUDE.md. |
| 4 | prose | §3 Coupling phase: "the centre of the on plateau" | "the center of the on plateau" | US spelling, consistent with the rest of the document. |
| 5 | prose | §4.1 Description: "Plain C++ with no framework dependency, so it can sit..." | "The engine is plain C++ with no framework dependency, so it can sit..." | Gives the fragment a subject. |
| 6 | prose | FR-2: "generates a carrier AM at the theta rate" | "generates a carrier amplitude-modulated at the theta rate" | "AM" is a noun in the glossary; matches the Theta reference definition. |
| 7 | prose | FR-3: "generates a separate carrier AM at the gamma rate" | "generates a separate carrier amplitude-modulated at the gamma rate" | Same as row 6; matches the Gamma PAC layer definition. |
| 8 | prose | FR-3: "short bursts per theta cycle" | "short bursts per theta reference cycle" | Glossary term, matching the Coupling phase definition. |
| 9 | prose | FR-6: "produce a byte-identical output" | "produce byte-identical output" | Removes a stray article. |
| 10 | prose | FR-13: "carrier rule and spacing" | "carrier rule and spacing rule" | Both glossary terms in full. |
| 11 | prose | FR-16: "Relax keeps its low-depth gamma" | "Relax keeps its low-depth gamma PAC layer" | Glossary term. |
| 12 | prose | FR-16: "beat sweeping 3 Hz to 0" | "beat rate sweeping from 3 Hz to 0 Hz" | Glossary term "beat rate"; unit on both ends. Values unchanged. |
| 13 | prose | FR-21: "(for example a sawtooth carrier)" | "(for example, a sawtooth carrier)" | Punctuation. |
| 14 | prose | FR-28: "static versus moving gamma" | "static versus moving gamma PAC layer" | Glossary term. |
| 15 | prose | FR-31: "A listener cannot change the binaural layer on/off, its carrier, or any rate" | "A listener cannot turn the binaural layer on or off, or change its carrier or any rate" | "Change ... on/off" did not parse; same three restrictions. |
| 16 | prose | §5 Accuracy: "theta drift under 1 ms" | "theta reference drift under 1 ms" | Glossary term, matching FR-1. |
| 17 | prose | §5 Isolation: "60 dB after master" | "60 dB after the master chain" | Glossary term, matching FR-4. |
| 18 | prose | §5 Reference match "Engine vs Python reference"; §8 Phase 1 and §11 Q10 "peak vs trough vs uncoupled" | "versus" in all three places | Microsoft style spells out "versus"; the document already uses it in FR-28. |
| 19 | prose | §5 Clicks: "at seams, ramp edges, burst edges" | "at seams, ramp edges, and burst edges" | Completes the series. |
| 20 | prose | §6 Clean room: "Specifics are in the project plan, IP and clean-room rules." | "Specifics are in the project plan's IP and clean-room rules." | The comma read as a list of three places; it is one section. Reference target unchanged. |
| 21 | prose | §6 Privacy: "Analytics anonymous only (FR-38)." | "Analytics are anonymous only (FR-38)." | Adds the verb. |
| 22 | prose | §8 Phase 0 part 1: "CLI and Python reference renderers" | "command-line and Python reference renderers" | Uses the FR-11 name instead of a synonym. |
| 23 | prose | §10 Risks: "spatial-audio re-mixes the ears" | "spatial-audio remixes the ears" | Spelling. |

Applied as 24 exact replacements (row 18 covers three locations through two replacement rules).

### Prose items considered and not applied

| Pass | Original Text | Revised Text | Changes |
| --- | --- | --- | --- |
| prose | §11 Q2: "(200/206 Hz or higher)" | Consider: "(a 200 Hz and 206 Hz pair, or higher)"? | The slash is compact but may read as a ratio. Left as is because the intended reading should be confirmed by Audio. |
| prose | FR-13: "envelope shape passes through the reference match" | Consider: "envelope shape is checked by the reference match"? | "Passes through" can read as routing. Left as is to avoid any shift in what the test means. |
| prose | §4.3 Description: "the obviously correct way" | none | Informal but deliberate voice; preserved. |
