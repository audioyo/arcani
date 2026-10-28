# Review: Addendum Polish

Target: `addendum.md` (1,039 words before edits). Lenses: structure, then prose (bmad-review). Style guide: Microsoft Writing Style Guide. Reader: humans (architects and story writers). Terminology checked against the PRD glossary (`prd.md` §3).

Purpose read: this document exists to help the architecture and story steps pick up detail the PRD deliberately leaves out (stack options, recipe shape, cross-platform determinism, stem metadata, starter mode values, comparables).

Structure model: reference / supporting appendix (independent, scannable sections, each self-contained).

Constraints honored: no change to meaning, numbers, values, citations, or decisions; glossary terms used exactly; no em dashes; no restricted program names. Structural moves and merges are listed below as suggestions only. Line endings (CRLF) preserved.

## Structure findings (not applied)

| Pass | Original Text | Revised Text | Changes |
| --- | --- | --- | --- |
| structure | §Starter mode parameters: closing paragraph "Each value is checked against the design log... see design log 2026-10-27 (d)." (~35 words) | MOVE directly under the first mode table | It qualifies the table values; separated from them by a second table and two notes. No word change. |
| structure | §Starter mode parameters: the two mode tables (parameters; when to use and evidence strength) | QUESTION: MERGE into one table, or keep separate | Both are keyed by mode. Merging gives one row per mode but widens an already wide table. Keeping them separate is reasonable for phone-width reading. |
| structure | §Starter mode parameters: "Spacing check to run early" and the Alekseichuk note | QUESTION: give each a bold run-in label (for example **Spacing check (v0.1 story item)** and **Citation note**) | Two action items are buried in running text after the tables; labels help a story writer find them. Not applied because it adds new labels rather than fixing prose. |
| structure | §Stem metadata (168 words) | QUESTION: tag as post-v0.1 in the heading, as other sections are tagged "(for the architecture step)" | Stems are outside v0.1; the heading gives no scope cue, while sibling headings do. |
| structure | §Comparables (55 words) | QUESTION: MOVE to the PRD, or keep as a pointer | Table stakes and uncovered angles are product positioning, not downstream detail. Small enough to keep if the PRD already covers it. |
| structure | §Stack candidates, §Recipe file shape, §Cross-platform bit-exactness | PRESERVE | Each is self-contained, front-loaded, and sized to its purpose. |

Estimated reduction if all structure suggestions are accepted: about 0 words (moves and labels only). No length target was given.

## Prose findings (applied)

Style notes preserved: terse, declarative, table-heavy; sentence fragments in table cells; "illustrative" and "provisional" hedges are deliberate scope markers.

| Pass | Original Text | Revised Text | Changes |
| --- | --- | --- | --- |
| prose | Detail that belongs downstream (architecture, stories) rather than in the PRD. | This addendum holds detail that belongs downstream (architecture, stories) rather than in the PRD. | Opening fragment given a subject. |
| prose | Claude Code hooks for fast tests after each edit. | Claude Code hooks that run fast tests after each edit. | Clarifies what the hooks do. |
| prose | Differences come from: | Cross-platform differences come from: | Removes ambiguity about which differences. |
| prose | Stem decoding and a third-party Orbit spatializer are outside the synthesis core and use the -100 dBFS tolerance instead. | Stem decoding and third-party Orbit spatialization are outside the synthesis core and use the -100 dBFS cross-platform tolerance instead. | Matches the glossary wording for the synthesis core ("Orbit spatialization"); names which tolerance (PRD FR-6, NFR table). |
| prose | 40 Hz rate (60 selectable), 50 ms bursts at the theta peak | 40 Hz rate (60 Hz selectable), 50 ms bursts at the theta reference peak | Adds missing unit; glossary term "theta reference". |
| prose | 40 or 60 Hz, smooth swell peaking at 0 degrees (peak) | 40 or 60 Hz rate, smooth swell peaking at coupling phase 0 degrees (theta reference peak) | Names the quantity (rate, coupling phase) per the signal naming rule; removes the redundant bare "(peak)". |
| prose | Off in v0.1 (gamma is on); later option: 6 Hz beat on 250 Hz ... theta builds over first 10 min | Off in v0.1 (gamma PAC layer is on); later option: 6 Hz beat rate on a 250 Hz carrier ... theta reference builds over the first 10 min | Glossary terms "gamma PAC layer", "rate", "carrier", "theta reference"; adds missing article. |
| prose | Delta: 3 Hz sweeping to about 1 Hz ... beat sweeping 3 Hz to 0 on 100 Hz | Delta rate: 3 Hz sweeping to about 1 Hz ... beat rate sweeping from 3 Hz to 0 Hz on a 100 Hz carrier | Names rate and carrier (PRD FR line 202 confirms "100 Hz carrier"); adds unit to 0. |
| prose | Focus gamma bursts on a 300 Hz carrier | Focus gamma PAC layer bursts on a 300 Hz carrier | Glossary term. |
| prose | within 40 dB of the gamma layer's peak, they collide with the 450 Hz theta reference. ... fixes it. | within 40 dB of the gamma PAC layer's strongest line, they collide with the 450 Hz theta reference carrier. ... fixes the collision. | Glossary terms ("gamma PAC layer"; "strongest line" from the spectral component definition); 450 Hz is the carrier; clear antecedent for "it". |
| prose | Learn moved from trough to peak (0 degrees) | Learn's coupling phase moved from trough to peak (0 degrees) | Names what moved. |

## Summary

- Structure: 6 findings (5 suggestions not applied, 1 PRESERVE).
- Prose: 11 fixes applied across 10 lines. Net change about +25 words; no values, numbers, citations, or decisions altered.
- Checks after edits: no em dashes; no restricted program names.
