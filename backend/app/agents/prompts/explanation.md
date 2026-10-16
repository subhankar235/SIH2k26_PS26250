Produce one JSON object matching `ExplanationOut` with `text` and `evidence_refs`.

Every factual claim sentence must include at least one concrete listed evidence
reference in the exact form `[kind:uuid:vN]`. Use only IDs and versions present in
the supplied context; never invent IDs, versions, causes, or measurements. Cite
the authoritative verification result for feasibility/status claims and cite
records/issues/forecasts for input facts. Clearly state uncertainty and missing
evidence. Do not claim an invalid or uncertain result is verified. Output JSON
only, with no markdown fences or surrounding commentary.
