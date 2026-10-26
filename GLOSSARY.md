# Strength coach engine

The rebuilt coach: code that owns invariants (arithmetic, units, kit rounding, safety bounds, data
integrity, Hevy shape) and an agent that owns coaching judgement with a recorded reason.

## Language

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
