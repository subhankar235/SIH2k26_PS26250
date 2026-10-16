# Synthetic dataset data dictionary

All tables are generated synthetic research data. Identifiers use deterministic
seeded strings and do not represent real assets, people, or locations. Timestamps
are ISO-8601 UTC strings.

## Raw source files

| File | Field | Type / unit | Meaning |
|---|---|---|---|
| `resources.csv` | `record_id` | string | Unique generated version/event record id. |
| | `entity_id`, `resource_id` | string | Synthetic resource identity; equal in the generated source row. |
| | `source_id` | string | Synthetic feed identity used to distinguish evidence sources. |
| | `name` | string | Synthetic resource label. |
| | `resource_type` | category | `solar`, `wind`, `hydro`, `thermal`, or `storage`. |
| | `capacity_mw` | float, MW | Synthetic nameplate capacity; may be null in a labelled missing-data example. |
| | `region` | category | One of `north`, `south`, `east`, `west`. |
| | `event_time` | ISO timestamp | Source observation time. |
| `crew.csv` | `record_id` | string | Unique generated crew record id. |
| | `entity_id`, `crew_id` | string | Synthetic crew identity; equal in generated source rows. |
| | `source_id` | string | Synthetic crew-feed identity. |
| | `name` | string | Synthetic crew label. |
| | `skills` | JSON array string | Synthetic skills, e.g. `["repair"]`. May be null in labelled missing data. |
| | `available_hours` | float, hours | Synthetic available work hours. |
| | `region` | category | Synthetic crew region. |
| | `event_time` | ISO timestamp | Source observation time. |
| `availability.csv` | `record_id` | string | Unique generated availability record id. |
| | `entity_id`, `resource_id` | string | Resource the time window describes. |
| | `crew_id` | string | Synthetic crew assigned to the window. |
| | `region` | category | Resource region. |
| | `available` | boolean | Whether the resource/crew pair is available. |
| | `start_time`, `end_time` | ISO timestamp | Half-open availability interval `[start_time, end_time)`. |
| | `event_time` | ISO timestamp | Source update time; may be shifted for a labelled stale-data example. |
| `weather.csv` | `record_id` | string | Unique generated weather record id; duplicate examples get a separate id. |
| | `entity_id` | string | Synthetic weather region identity (`weather:<region>`). |
| | `source_id` | string | Synthetic weather-feed identity. |
| | `region` | category | Synthetic region. |
| | `temperature_c` | float, °C | Synthetic daily temperature observation. |
| | `wind_speed_mps` | float, m/s | Synthetic daily wind-speed observation. |
| | `precipitation_mm` | float, mm | Synthetic daily precipitation observation. |
| | `event_time` | ISO timestamp | Source observation time. |
| `constraints.csv` | `record_id` | string | Unique generated constraint record id. |
| | `entity_id` | string | Resource governed by the limit. |
| | `source_id` | string | Synthetic constraint-feed identity. |
| | `constraint_type` | category | Currently `max_capacity_mw`. |
| | `limit_mw` | float, MW | Synthetic operating limit; may be changed in a labelled constraint-change example. |
| | `active` | boolean | Whether the constraint applies. |
| | `event_time` | ISO timestamp | Constraint source update time. |

## `labels.parquet`

| Field | Type | Meaning |
|---|---|---|
| `record_id` | string | Record id carrying the labelled synthetic fault. |
| `fault_type` | category | `missing`, `stale`, `duplicate`, `conflicting`, or `constraint_change`. |
| `true_value` | nullable JSON string | Ground-truth value before corruption or the expected value for the conflict group. |
| `duplicate_of` | nullable string | Original record id for a generated duplicate. |
| `conflict_group_id` | nullable string | Shared identifier for synthetic competing records. |
| `true_freshness_time` | nullable ISO timestamp | Correct source freshness timestamp before a stale-data shift. |

## Time-based ML splits

`data/generators/make_splits.py` writes `pairs_{train,val,test}.csv`,
`graph_{train,val,test}.parquet`, and `forecast_{train,val,test}.csv`. Splits are
chronological 70/15/15 partitions; a local seeded generator only breaks equal-time
ties. Graph rows carry any matching fault-label fields. Forecast rows exclude
records with injected faults. Ditto pair CSVs contain `left` and `right` JSON-object
columns, `label` (`match`/`no_match`), record-id references, and the pair's event time.
