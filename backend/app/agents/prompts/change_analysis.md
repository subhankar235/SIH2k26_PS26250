Analyze only the supplied versioned inputs and change events.

Return a JSON object matching `ChangeAnalysisOutput` with `changes` and
`uncertainty`. Each change must identify its `input_type`, `input_id`, prior
version (if known), and persisted current version. Cite only supplied IDs and
versions; never invent a change, ID, or version. If versions do not establish a
real change, return an empty change list and explain uncertainty in the
`uncertainty` list. Output JSON only.
