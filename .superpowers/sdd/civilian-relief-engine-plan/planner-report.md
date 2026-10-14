# Relief planner implementation report

Owned files: `services/ingestion/src/relief-planner.js`, `services/ingestion/test/relief-planner.test.js`.

Implemented a dependency-free bounded exact search for the sealed fictional one-wave civilian relief problem. Five specialist reports (`fleet`, `crew`, `weather`, `airport`, `cargo`) contain deterministic world-grounded findings and eligibility. The supervisor consumes eligibility and enumerates request/aircraft/crew/departure-slot choices, enforcing at most one delivery per aircraft and crew plus per-slot airport capacities. IDs and output ordering use a stable lexical comparison.

Objective fields are `{servedPriority, changedAssignments, totalArrivalSlots}`. Maximize priority first, minimize changes to previous assignments for request IDs still present in the current world second (dropping a surviving previously served request counts as changed), minimize summed arrival slots third; equal objectives break ties by sorted request/aircraft/crew/slot IDs. Previous assignments for removed request IDs do not incur change cost. `validateReliefPlan(world, plan, {previousAssignments})` supports the same previous-assignment context.

The independent checker walks the assignments and source world directly, without relying on candidate eligibility or search resource bookkeeping. It checks unknown/duplicate entity IDs, shape and slots, route/arrival arithmetic, availability/expiry, aircraft origin/payload/cold storage, crew qualification/duty, request expiry/deadline, airport closure/expiry/capacity, weather presence/expiry/limits, complete served/unserved accounting and objective arithmetic. It also rejects altered specialist findings/messages/eligibility, fabricated unserved reasons and inconsistent method/candidate-count/budget/status metadata. Report/reason checking shares the finite evidence-building functions, while assignment constraints and objective calculation are separately implemented. The checker certifies feasibility and arithmetic; it does not independently prove a claimed global optimum by rerunning search.

Input bounds fail closed: at most 3 aircraft/crews/airports/weather records, 2 single-slot routes, 5 ordinary medical/food/water/equipment requests, 3 fixed departure slots, 31 history points; finite bounded numbers, unique `SIM-` entity IDs, logical tick/revision bounds, fixed educational policy, strict assignment shape and integer node budget in 1..100000. Missing world evidence remains an explainable infeasibility; malformed world structure is rejected. No arbitrary objective, combat entities, tactical risks, external observations, navigation or real-world certification claim is supported.

At most 27 assignment candidates plus an unserved choice per request. Unpruned enumeration is O(28^R) for R <= 5; resource exclusivity and a safe priority upper bound prune it. Actual traversal is capped at `nodeLimit` visited nodes, with at most 27 bounded candidate checks per visited node and O(R + candidates + reports) working memory. The budget is a deterministic work bound, not a wall-clock guarantee. Feasible partial incumbents are retained, including the empty plan. Any incomplete traversal is labelled `feasible_budget`, never `optimal`; proven complete traversal is labelled `optimal`.

Validation evidence:

- TDD RED: initial focused run failed because the planner module did not exist. GREEN: initial 8 behavior tests passed after implementation.
- Additional RED: fabricated unserved reason was initially accepted. GREEN: grounded reason and diagnostic checks added; 12/12 focused tests pass.
- Independent exhaustive test oracle matches the full lexicographic objective for 8 small fixture variants.
- Canonical scenario priorities across all phases are `[9, 7, 7, 0, 10, 0]`; every revision verifies with its actual previous-assignment context.
- Known optimum, tie determinism and reordered input, objective hierarchy, node budget, empty blocked/expired plans, every hard constraint, malformed bounds and fabricated IDs/eligibility/objective/resources are covered.
- Mutation review: inverted the independent checker's cold-storage predicate; 3 tests failed. Restored the original file; focused suite returned to 12/12 passing.
- `npm run check` passed for 56 JavaScript files.
- Full `npm test` after root's service landed: **127/127 passed**, including the existing suite, planner, models, world and new simulation service persistence/atomicity tests. Root is responsible for final HTTP/Kafka/browser integration validation.

No new dependency, shared file edit, external tool call, runtime model execution or source credential is included.
