# Strength coach engine

The rebuilt coach: code that owns invariants (arithmetic, units, kit rounding, safety bounds, data
integrity, Hevy shape) and an agent that owns coaching judgement with a recorded reason.

## Language

### Program

**Program**:
The athlete's authored training structure, as an identity that persists across its versions.
_Avoid_: routine, plan, template

**Program version**:
One immutable adopted snapshot of a program: its sessions, lines, schemes, schedule rule and block
policy. A persisting swap or a block-boundary redesign is a new version.
_Avoid_: program edit, revision, patch

**Lifting goal**:
What a program version is for: hypertrophy, strength or maintenance. Set when the version is
authored, it fixes the default weekly dose target and what the week is checked against.
_Avoid_: goal (fine in prose), objective, training focus

**Session**:
A template with a title, lines, kind and tier, inside a program version or carried by a niggle.
It knows nothing about the calendar.
_Avoid_: routine, day, workout (which is what was logged), add-on

**Session kind**:
What a session is: lifting, conditioning, practice (a daily drill with nothing to progress), or
coach-led.
_Avoid_: type, category

**Coach-led session**:
A session whose content someone else programs, carried as estimated sets per muscle rather than
lines. It fills a slot and counts when it happened.
_Avoid_: external session, PT session

**Session tier**:
Whether a session is core (a week is judged on it) or optional (bonus volume; skipping it is not a
miss). A practice is always optional.
_Avoid_: priority, importance

**Rehab session**:
A session a niggle carries, from a physio or the coach: planned while the niggle is open, retired
when it resolves, never part of a program version.
_Avoid_: rehab routine, prehab, add-on

**Parked session**:
A program version's session taken out of force by a Decision until a later Decision resumes it.
The version itself never changes.
_Avoid_: status, parked (as a field), disabled

**Slot**:
A place in a program version's schedule rule that names which session fills it: a rotation week
and weekday, or none, plus a cadence.
_Avoid_: day, position

**Cadence**:
How often a slot expects its session: weekly (a weekday in a rotation week), standing (any day,
when it fits) or daily.
_Avoid_: frequency, schedule type

**Line**:
One exercise in a session: the exercise, its load mode, set groups, rest, cues and progression
scheme.
_Avoid_: entry, item, session exercise

**Set type**:
What a prescribed or logged set is for: warm-up, working or activation. A rep-out is a working set
with an open top, not a type.
_Avoid_: set kind

**Rotation position**:
The schedule-rule week a WeekPlan is planned against. Proposed by the engine, confirmed by the
athlete when the WeekPlan is approved.
_Avoid_: week letter, current week, inferred week

### Week

**Week**:
The Monday-to-Sunday span a WeekPlan covers, and the unit adherence and the hard-week count are
judged in.
_Avoid_: span, cycle

**WeekPlan**:
The plan for one week: its rotation position, its overrides with their reasons, its status
(approved, superseded) and its frozen prescriptions. It exists only once approved; before that
there is only the plan file the agent is editing.
_Avoid_: overlay, proposal, draft, one-off

**Override**:
A typed, reasoned departure from the program version's rule, scoped to a week, a planned session
or a line. A load appears in one only as the typed field of a pin, never in prose. A WeekPlan
holds those that live for its span; a Decision holds those that last longer.
_Avoid_: delta, tweak, adjustment, standing override (say "override Decision")

**Recovery ceiling**:
The lowest load or RPE a line may be set to on a date: a niggle's cap, the return band's cut,
the illness cap on the first session back, or a light week's RPE ceiling.
_Avoid_: limit, safety cap

**Violation**:
A hard constraint a WeekPlan breaks: an off-grid load, a recovery ceiling exceeded, a return
band that disagrees with the days off, a block ceiling passed without a Decision. Approval is
refused while one stands anywhere in the plan.
_Avoid_: error, hard flag

**Warning**:
A coaching signal the validator reports on a line and the agent must read but may leave: a top
set above the e1RM model, a stall streak, a short-sleep week, unexplained drift from last week.
_Avoid_: soft flag, notice

**Planned session**:
A session put on a calendar date by a WeekPlan. A moved session is a planned session on its new
date; a one-off is a planned session with no slot behind it.
_Avoid_: scheduled session, instance

**Prescription**:
The derived numbers for one line of one planned session: sets, load, reps or range and RPE target,
computed from the program version, history and overrides, and frozen into the WeekPlan at approval.
_Avoid_: target, proposal, projection

**Prescribed set**:
One set inside a prescription: its type, load, reps or range and RPE.
_Avoid_: set target

**Week kind**:
What a closed week counted as: hard, light, return, one-off, minimum, break or partial. Derived by
one precedence order, never stored.
_Avoid_: week type, week status

**Approval**:
The athlete's recorded yes to one WeekPlan, by id, given at the prompt for the one write that
pushes it. The only thing a Hevy push can bind to. There is no approve step of its own.
_Avoid_: sign-off, confirmation, approval hash, self-approval

**Write plan**:
Exactly what a push would do, as one hash: the WeekPlan that would be frozen, each Hevy write,
and the version of each routine touched. Shown with the dry run, handed back to the write, and
refused when anything underneath it has moved.
_Avoid_: approval hash, plan hash, expect-plan

### Log

**Workout**:
What was logged on a date, imported from Hevy or entered by hand: raw facts, append-only, never
deleted. A workout Hevy no longer has is tombstoned.
_Avoid_: history entry, mirror, session (which is the template)

**Logged set**:
One raw set in a workout, as recorded.
_Avoid_: actual set, performed set

**Annotation**:
A correction applied when a workout or planned session is read (discount, repair, load mode,
void, trained-unlogged, cancelled, miss tag, match). It has a stable id, is withdrawn by a later annotation and is
never written into the workout or sent to Hevy.
_Avoid_: correction, edit, fix

**Exposure**:
An exercise in a workout with at least one working set left after annotations: the unit
progression and e1RM read from.
_Avoid_: performance, session log

**Match**:
The link from a workout to the planned session it fulfilled, or none. Derived from date and
session kind, corrected by a match annotation, never stored.
_Avoid_: mapping, reconciliation

**Miss**:
A planned session whose week has ended with no match, no move and no cancellation. Derived, never
stored.
_Avoid_: skipped session (an optional session skipped is not a miss)

**Activity**:
A logged non-lifting bout (a run, a class, a conditioning session's workout) with date, duration,
RPE and whether it was quality work.
_Avoid_: cardio entry, bout, wellness

**Weigh-in**:
One bodyweight observation on a date, typed in or imported, with its source. Read for a trend and
for total system mass in bodyweight and assisted lifts.
_Avoid_: reading, bodyweight record, scale weight

**Sleep night**:
Hours asleep on one night, typed in or imported, with its source. A weekly mean is not a night.
_Avoid_: wellness row, sleep reading

**Status span**:
A dated span of ill, injured, travel or no-training, open-ended allowed, withdrawn never deleted.
_Avoid_: status day, availability, wellness day

**e1RM**:
Estimated one-rep max from a qualifying exposure. Recomputed from exposures, never stored.
_Avoid_: training max (a Decision), strength estimate

**Hard set**:
A working set at RPE above 5. Counted as one for the muscle it targets directly and a half for a
muscle it works indirectly.
_Avoid_: effective set, real set

### Athlete

**Profile**:
The athlete's own prose: who they are, the goal and phase in words, why the week has its shape,
limits in words, coaching preferences and history. Read by a coach, never by code.
_Avoid_: profile.md (the file; fine in paths), athlete doc, status

**Coaching preference**:
A standing agreement about how to coach the athlete, kept in the profile. An agreement that
constrains a line or a load is an override Decision instead.
_Avoid_: rule, note, preference (alone)

### Ledger

**Check-in**:
The dated event of a review: its tier (light or deep), the window it reviews and the coach's
read. The athlete's answers are records of their own that point back to it. Closes every week
its window covers.
_Avoid_: review, week review, card (which is the rendered form), record (which is the rendered page)

**Check-in window**:
The span a check-in reviews: from the day after the previous check-in's window to its own date.
One longer than the first return band makes the check-in a catch-up.
_Avoid_: period, gap

**Coach's read**:
The coach's own prose in a check-in: voice, never data. Shown verbatim beside the generated
facts and never parsed.
_Avoid_: summary, assessment, narrative

**Athlete note**:
Something the athlete said at a check-in, kept verbatim with the date and, when it is about one
thing, a pointer to it. Surfaced where it is next useful, never classified by code.
_Avoid_: free text, comment, feedback

**Block**:
A run of weeks under one hard-week ceiling, opened at adoption or after a reset and closed by the
check-in that resets the count.
_Avoid_: mesocycle, cycle, phase

**Decision**:
A coaching choice recorded with its reason and outcome: an override with an until date, a light
week, a training max, a declined ceiling, or going against a research claim.
_Avoid_: note, rationale, flag

**Niggle**:
A reported discomfort tracked over time, with a status history, the load constraints it imposes
and any rehab session it carries.
_Avoid_: injury (which needs a professional), issue, pain entry

**Follow-up**:
Something to revisit on a date, with the events that raised, deferred, kept, resolved or dropped
it.
_Avoid_: todo, reminder, action item

**Observation**:
A pattern the coach has noticed about the athlete, dated, with the evidence that raised it,
confirmed by the athlete and retired with a reason when it stops holding.
_Avoid_: coach's note, note, insight

**Short-sleep week**:
The fatigue trigger: at least 4 of the last 7 measured nights under 7 hours.
_Avoid_: sleep trigger, poor sleep

### Kit and loads

**Exercise**:
A library entry a line references: name, Hevy template id, load mode, muscles and movement
pattern.
_Avoid_: movement, lift (fine in prose, not as the noun)

**Equipment**:
The kit the athlete has at a location, which fixes the loads an exercise can be set to.
_Avoid_: kit (fine in prose), inventory, gear

**Location**:
A named place the athlete trains, with its own equipment. A session names its default location;
a planned session may be moved to another.
_Avoid_: gym (fine in prose), venue, site

**Rack**:
The enumerated loads one implement can be set to at a location. At home every implement is a
rack, taken from plate-pool's published achievable loads; at a kit-less location only dumbbells
and kettlebells are.
_Avoid_: grid (which is an increment rule, not a list), inventory

**Equipment kind**:
What an exercise is done with: barbell, dumbbell, kettlebell, leg attachment, vest, machine,
cable, band or bodyweight. A location maps each kind it supplies to one of its implements.
_Avoid_: equipment (which is the kit itself), implement type

**Safety ceiling**:
A load the athlete will not go above on one exercise, set with a reason. Not a kit limit, which
is whatever the rack can build.
_Avoid_: cap, max

**Load mode**:
How an exercise's load is counted: total, per hand doubled, single implement, bodyweight, assisted,
band, duration or distance.
_Avoid_: weight type, load type

**Load**:
A weight in athlete units together with its load mode. The one place unit conversion and
per-hand doubling happen.
_Avoid_: weight, kg, hevy weight

### Hevy

**Routine**:
Hevy's own object for a session. The engine projects into it and never owns its content.
_Avoid_: hevy session, remote routine

**Routine map**:
The stored link from a session to a Hevy routine id and its status (active, retired, missing),
recorded only after a verified write.
_Avoid_: routine ids, mapping table

**Spare routine**:
A retired routine, renamed and moved to the Retired folder, that a later session may take over.
Hevy cannot delete a routine, so nothing is ever removed.
_Avoid_: deleted routine, unused routine, temporary routine

**Tombstone**:
The record that Hevy no longer returns a workout. The workout and its sets stay; reads skip it.
Never withdrawn.
_Avoid_: deletion, removal

**Drift**:
A live routine that differs from the plan in force, found at import. Resolved by an override or
by the next push; never adopted into the store.
_Avoid_: app edit, out of sync

**Write audit**:
The committed append-only file holding every request the engine sent to Hevy and every read-back
verify, written at request time.
_Avoid_: writes log, hevy log

### Agent interface

**Verb**:
One command the agent can run, doing a whole job (validate, diff, write, verify, record) and safe
to re-run. The engine has a small, budgeted set of them.
_Avoid_: subcommand, tool, endpoint

**Envelope**:
The one JSON document a verb prints: whether it succeeded, its result or error, and any warnings.
_Avoid_: response, output, payload

**Result class**:
The kind of outcome a verb had, carried by its exit code: ok, data or check failed, a guard
refused a write, Hevy unreachable, or setup stops it. The specific reason lives in the envelope.
_Avoid_: status, error level

**Writing verb**:
A verb that changes something outside the engine's own store: Hevy, or git. The only kind of verb
a permission prompt attaches to.
_Avoid_: gated command, mutation

**Dry run**:
A writing verb run without writing, returning what it would send and whether a guard would refuse
it. What the permission prompt shows.
_Avoid_: preview, simulate, plan (which is a noun here)

**Service**:
A plain function behind a verb that owns the procedure and the transaction, taking a typed request
and returning a typed result. It knows nothing about the command line.
_Avoid_: handler, controller, use case

**Compact summary**:
The default output of a read verb: the few facts an agent needs next, within a fixed size budget.
The whole record is a separate request.
_Avoid_: digest, overview

**Rendered page**:
A markdown file the engine writes from the store for the athlete to read: the weekly sheet, a
routine page, a check-in record, the athlete page, progress. Written whole at every publish, read
by no code, edited by nobody.
_Avoid_: document (fine in prose), report, dashboard, generated file

### Distribution

**Engine**:
The coach itself: the code, verbs, skills and hooks, released as one versioned whole. One
installed engine serves any number of instances.
_Avoid_: framework, template, core

**Instance**:
One athlete's directory: config, profile, the store and its committed export, and nothing of the
engine. Where every verb runs.
_Avoid_: workspace, data repo, my-training

**Engine pin**:
The one engine version an instance declares it was last upgraded to. A verb from any other
version stops before touching the instance.
_Avoid_: requirement, compatibility range

**Upgrade**:
Bringing an instance up to a newer installed engine in one approved step: migrate the store,
regenerate what the engine owns in the instance, move the pin, commit.
_Avoid_: sync, framework-sync, migrate (one part of it)
