# Planning optimization

This package contains the standalone CP-SAT schedule solver and adapters to the
backend's planning request and `Schedule` persistence contract. It does not open
database sessions, import ORM models, or perform verification or approval.

All time values are integer **minute ticks on one common time axis**. Task
bounds and resource availability must use the same tick unit; timestamp
conversion is not implicit and non-integer times are rejected. Tasks require a
stable id, duration, required resource type, earliest start, latest end, and
priority. Resources require an id, type, positive capacity, and explicit
availability intervals. Each task consumes one resource capacity unit unless
`resource_units` is specified.

The supported objective names are `makespan` and `weighted_completion`.
Supported policies currently consist of `max_makespan` with an integer
`parameters.maximum`. Unsupported policy/objective names fail validation rather
than being ignored. Partial resolution runs the updated model with compatible,
unaffected prior assignments as solver hints; changed, removed, and unavailable
assignments are not forced. ALNS is not wired into the planning endpoint.

The planning endpoint accepts a complete task/resource snapshot. Current
normalized `Record` payloads do not contain task timing, priority, or precedence
data; solver input therefore comes from the existing `ProblemIn` request. No
input-version dependencies or forecast constraints are inferred. Solver status
is retained in `solver_meta`; independent verification is persisted separately,
and schedules are never automatically approved.
