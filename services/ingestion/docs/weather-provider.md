# Civilian weather provider

`createReliefWeatherProvider()` performs a manual, single-flight request to the fixed
HTTPS endpoint `https://api.open-meteo.com/v1/forecast`. Supported aliases and fixed
city-centre coordinates are Delhi (`delhi`, 28.6139, 77.2090), Mumbai (`mumbai`,
19.0760, 72.8777), and Chennai (`chennai`, 13.0827, 80.2707). These are civilian
city presets mapped explicitly onto a fictional airport by the authenticated
simulation command. They do not identify airport sensors. No caller URL,
coordinates, credentials, API key, geocoding, redirect, or automatic polling is used.

The command schema is strict: UUID `commandId`, UUID `runId`, integer
`expectedRevision` from 0 through 18, `airportId` beginning `SIM-` with an
alphanumeric suffix and at most 20 total identifier characters, and one supported
`location`. The service checks the run, airport binding, mode, authority, and
revision before and after the network request.

## Sources and interpretation

Documentation was fetched through Context7, first resolving Open-Meteo and then
querying `/websites/open-meteo_en`; the main official API page was checked directly
to confirm the general forecast endpoint. The [Open-Meteo forecast documentation](https://open-meteo.com/en/docs)
defines `current` fields as weather model data, hourly visibility in metres, Celsius
temperature, `wind_speed_unit=ms`, GMT timestamps, and WMO weather codes. These
values are model estimates, not direct station observations or aviation reports.
The [Zod API documentation](https://zod.dev/api), fetched using Context7 resolution
and `/websites/zod_dev`, supplies strict object validation and finite numerical bounds.

The request selects `temperature_2m,wind_speed_10m,weather_code` from `current`
and `visibility` from `hourly`, with `timezone=GMT`, `timeformat=iso8601`,
`temperature_unit=celsius`, `wind_speed_unit=ms`, `past_hours=1`, and
`forecast_hours=3`. Response units and UTC offset zero are required. Timestamp
strings without an offset are interpreted explicitly as UTC, never host-local
time. Calendar validity is checked; non-UTC offsets are rejected.

Visibility uses the hour nearest to the current-weather timestamp, with ties
choosing the earlier hour. The selected sample must be within 30 minutes of the
current timestamp. It can therefore be a future forecast hour, and its exact time
is preserved in provenance. Missing or null visibility at that nearest hour fails
the refresh; the adapter does not substitute another hour or a default. Hour arrays
must be equally sized, sorted, unique, aligned to whole UTC hours, and at most 48
samples. Temperature is bounded to -100..60 degrees Celsius, wind to 0..150 m/s,
and visibility to 0..100000 m, matching canonical weather bounds.

WMO codes map to the canonical coarse conditions as follows:

| Canonical condition | WMO codes |
| --- | --- |
| clear | 0, 1, 2, 3 |
| fog | 45, 48 |
| rain | 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82 |
| snow | 71, 73, 75, 77, 85, 86 |
| storm | 95, 96, 99 |

The existing canonical `clear` category includes mainly clear, partly cloudy and
overcast model codes: it means no listed precipitation/fog/storm category and does
not assert a cloudless sky. Other codes fail validation. No weather value is invented,
clamped, or inferred from missing fields.

## Freshness and output

Freshness is an application policy. The current sample must be less than 30 minutes
old and no more than 60 seconds in the future, measured after body reception.
`observedAt` is that sample's UTC time. `validUntil` is the earliest of the current
sample plus 30 minutes, visibility sample plus 60 minutes, and fetch completion
plus 15 minutes. Validity must still end after fetch completion and observation.
A cached or slow response cannot extend freshness by being fetched again.

The result is `{data:{temperatureC,windSpeedMps,visibilityM,condition},observedAt,
validUntil,provenance:{provider,location,latitude,longitude,fetchedAt,weatherTime,
visibilityTime}}`. Provider is `open-meteo`; coordinates are the requested civilian
preset rather than an upstream grid-cell coordinate. All exposed timestamps are
canonical UTC ISO strings. The two sample times preserve the fact that the weather
and visibility inputs may have different valid times.

## Resource limits, errors and shutdown

The default total deadline is 10000 ms and body limit is 65536 bytes. Constructor
overrides are strictly bounded to 1..60000 ms and 1..131072 bytes. The deadline
covers headers and streaming body reads. Both advertised content length and actual
streamed bytes are checked; rejected or aborted bodies are cancelled. Only one
public operation can be active. `close()` permanently rejects new calls, aborts the
active transport, and drains the public operation, including when an injected
transport ignores its abort signal. A late response is cancelled and discarded.

Failures throw `ApiError` with fixed codes/messages, never upstream text or bodies:

| Code | HTTP status |
| --- | --- |
| WEATHER_INVALID_LOCATION | 422 |
| WEATHER_BUSY, WEATHER_CLOSED | 503 |
| WEATHER_TIMEOUT | 504 |
| WEATHER_UNAVAILABLE, WEATHER_RESPONSE_TOO_LARGE, WEATHER_INVALID_RESPONSE | 502 |

No fallback weather, retry, or world mutation occurs in this adapter. The service
retains error status/provenance and commits successful observations through its
existing transactional ingestion path.
