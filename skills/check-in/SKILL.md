---
name: check-in
description: The weekly review. Use when a check-in is due, when the athlete reports on their
  week, or when the newest check-in is more than a week old. Also /check-in.
---

## Read first
The profile, once. Ask the athlete's readiness (`poor`, `ok`, `good`) first and pass it to
`coach checkin open --readiness`. The card it returns states what the store already knows and
asks only what it cannot. Never change its figures or the order of its fields.

## Ask
Send the card as one message in the coach's voice; the athlete answers by number. A fact the log
already answers is stated for confirmation, not asked. Follow up only for a gap that blocks the
read or next week's plan. On a deep tier, settle every open niggle and follow-up with the athlete
rather than carrying them.

## Judge
- **Readiness.** The athlete's own words and their Hevy set notes are the signal, and the card's
  Readiness field records it; an RPE drift trigger on the card's Block line matters on the
  compound lifts, elsewhere a rising RPE is a note.
- **Misses.** A tag per missed core session. Pattern over blame: a run of `time` misses is a
  schedule problem for the plan, not a willpower problem.
- **Sleep and weight.** Read the trend, not the week. A short-sleep week (`short_sleep_week`)
  shapes next week's dose; one bad night does not.
- **Phase.** When the card says the until condition is met or the trend is off, propose
  closing or keeping it with the athlete; a new Phase opens in the record.
- **Niggles.** Reported, aggravated, easing, resolved. Escalate to a professional when pain
  changes gait, sleep or daily tasks; never diagnose.
- **Block and tier.** When the card's Block line carries a proposal or the derived tier is deep,
  propose and let the athlete adopt, decline with a reason or defer. When adherence is `low`,
  present a smaller schedule with the same weekly hard sets per muscle. The rotation position is
  confirmed, not asked.
- **Patterns.** Raise an Observation when something has held across check-ins; retire one that
  stopped holding. Cite the exposures or notes it rests on (`coach query`).

## Explain
The read is one or two sentences on the week, then what the tables cannot say. Lead with a win
when there is one. Quote every number from the card or the rendered record; never retype a load.
Name each decision and its reason in plain words. Say what next week will feel like, not what
it will contain; the plan does that.

Run the verb's dry run, quote what it shows, and the athlete says yes before the verb records it.

## Verbs
`coach status`, `coach checkin open`, `coach checkin record`, `coach query`
