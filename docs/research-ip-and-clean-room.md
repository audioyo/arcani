# IP and clean-room research

Research file: it describes sources, so it may name them. It holds the source table, the patent and brand-name record, and the motion-layer comparison that used to sit in the [project plan](project-plan.md). The plan keeps the rules themselves, in its "IP and clean-room rules" section, and links here for the record. Moved from the plan on 2026-11-03 (Story 0.4, design log entry (dd)). This is a working read, not legal advice.

## Source materials

The signal plan is reconciled against Monroe Technical Reference v5 (called v5 in the plan), shared in the planning conversation. Values that appear only in earlier discussion, not in v5, are marked as open decisions in the plan.

| Source | What it supplied | Confidence |
| --- | --- | --- |
| Monroe Technical Reference v5 | Carrier and gamma frequencies, PAC coupling, static-carrier rule, mix levels, research citations | High; source document |
| Theta-gamma conversation, post-feedback analysis | Ambisonic decoder crosstalk caused the monaural beat; carriers must bypass spatial processing | High |
| This conversation | Endel model, phases, AI-then-human stems, offline stem generation, Android first | High |
| [US 2013/0010967 A1, Google Patents](https://patents.google.com/patent/US20130010967A1) | SAM application status and scope | High, as reported by Google; not a legal opinion |
| [Monroe Sound Science page](https://www.monroeinstitute.org/pages/monroe-sound-science) | Public description of MSS technique families | High |

The "earlier project" the plan mentions is the Monroe challenge: a hiring challenge whose submitted track (built from v5) drew the reviewer feedback quoted in the plan's "Lessons from the earlier project" section. The plan's "research partner" goal (its partnership-ready principle and its BMAD handoff) refers to the Monroe Institute.

## Patents and brand names

The Monroe patents are not the real legal risk: the old binaural patents have expired by term, and the SAM application was abandoned without ever being granted. The live risk is other companies' active patents on audio modulation, which need a freedom-to-operate review before launch.

| Item | Status | What it means for us |
| --- | --- | --- |
| Monroe binaural patents (US 3884218, 5213562, 5356368) | Expired by term | Basic binaural beat generation is free to use |
| [SAM application US 2013/0010967](https://patents.google.com/patent/US20130010967A1) and its divisional US 2015/0016613 | Abandoned in 2015 for failure to respond to an office action; never granted | No enforceable rights, but we still design our own spatial method and never use the SAM name |
| Brain.fm patents citing the SAM family (US 11205414, 11957467, 11966661, 11392345) | Active, per the citing list | Cover neural stimulation through modulated audio; closest risk to our PAC and isochronic layers |
| Endel patents | Endel says its tech is patented | Check claims on adaptive, input-driven soundscape generation |
| Monroe, Hemi-Sync, Monroe Sound Science, Gateway, Focus levels | Brand names | Never in the app, store listing, or marketing |
| Monroe recordings, scripts, voice guidance | Copyrighted | Never sampled, imitated, or referenced |

The v5 element the plan keeps out of the app: its session arc was modeled on Gateway Voyage exercises, including resonant tuning and a pink-sound onboarding drawn from the Gateway guidance manual. The app's session arcs are designed from scratch, so nothing in them reads as a Gateway imitation. Generic elements like pink noise and a gentle fade-in are fine on their own.

## Motion layer versus the SAM application

The plan's spatial motion layer uses standard object panning rather than the abandoned SAM method:

|  | SAM application (not used) | Our motion layer |
| --- | --- | --- |
| How motion is made | One tone sent to both ears with opposite phase modulation, a Doppler-style shift | A sound object moved along a path with interaural level and time differences, or an HRTF spatializer |
| What moves | The entrainment tone itself | The gamma PAC layer; carriers stay fixed and dichotic |
| Name | Spatial Angle Modulation | Working name: Orbit layer |

The open decision on the term "SAP" in the project description is in the plan's [Open decisions](project-plan.md#open-decisions-risks-and-bmad-handoff).
