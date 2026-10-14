# Synthetic demand and local evidence selection

These modules belong only to the fixed fictional civilian relief simulation. Demand is an educational number, not a real-world prediction. Forecasts are read-only displays: they do not create requests, change constraints, or schedule deliveries. Specialist findings and the independently checked planner determine the plan. Local language models can only highlight existing findings.

## Reproduce the training artifact

From `services/ingestion` with the project's pinned Node runtime:

```powershell
node scripts/train-relief-models.js
node scripts/train-relief-models.js --seed 26250 --samples 120 --output relief-demand.json
```

The first command prints JSON; the second creates a new file and refuses to overwrite an existing one. Invalid arguments fail with a static message. The API is `trainDemandModel({seed=26250,samples=120})`; allowed seeds are unsigned 32-bit integers and sample counts are integers from 20 to 1000. It introduces no dependencies or external dataset downloads.

The published synthetic generator is:

```text
day = 0 .. samples-1
state = (1664525 * state + 1013904223) modulo 2^32
uniform = state / 2^32
demand = round(250 + 2*day + 50*sin(2*pi*day/7)
               + 15*cos(2*pi*day/7) + 30*(uniform - 0.5))
```

The initial PRNG state is the seed. The same generator then supplies Fisher–Yates shuffle choices, with `j = floor(uniform * (i+1))`, proceeding from `i=samples-1` to 1. Reserve the first `floor(samples*0.2)` shuffled records (at least four) for evaluation; train on the remainder. No held-out target enters fitting or the baseline. All day IDs are recorded under `split.trainingDays` and `split.testDays`, making overlap auditable. There is no timestamp in the model, so identical inputs produce identical artifacts.

Four-feature ordinary least squares uses `[1,day/30,sin(2*pi*day/7),cos(2*pi*day/7)]` and a pivoted four-by-four normal-equation solve. The baseline is the training targets' mean. Evaluate both on the held-out records using mean absolute error, in fictional demand units.

Default seed 26250 and 120 samples produce 96 training and 24 test records. Coefficients are approximately `[245.96385,61.39683,51.09614,15.35692]`; held-out MAE is `7.14252` and baseline MAE is `76.22917`. Example forecasts for days 120, 121, and 122 are `541`, `540`, and `504`. The artifact includes seed, feature definition, coefficients, split IDs, counts, errors, and forecast bounds. The CLI adds those three example forecasts.

`forecastDemand(model,day)` rejects invalid models or non-finite days, clamps finite days to `[0,3650]`, and returns an integer in `[0,10000]`. The random holdout measures interpolation under this known synthetic generator; it does not establish future forecasting accuracy, calibrated uncertainty, or real-world usefulness. The model has no external data or fitted real-world parameters.

## Annotator interface and configuration

```javascript
const config = loadReliefAIConfig(process.env);
const annotator = createReliefAnnotator(config);
const annotations = await annotator.annotate({ runId, revision, agentReports });
await annotator.close();
```

The configuration loader defaults to `deterministic`. It returns an immutable object and validates again when constructing an annotator, including programmatic configurations. It reads only these named environment variables:

| Variable | Default | Accepted values |
| --- | --- | --- |
| `RELIEF_AI_MODE` | `deterministic` | `deterministic` or `ollama` |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Canonical HTTP origin with hostname exactly `127.0.0.1`, `localhost`, or `[::1]`; no credentials, path, query, or fragment |
| `RELIEF_AI_MODELS_JSON` | map below | Exactly five agent keys and local model names with explicit tags; names have bounded length and no URL syntax |
| `RELIEF_AI_TIMEOUT_MS` | `10000` | Integer 20–60000; per request, including response body |
| `RELIEF_AI_MAX_RESPONSE_BYTES` | `32768` | Integer 1024–131072; entire response body |
| `RELIEF_AI_NUM_CTX` | `2048` | Integer 512–4096 |
| `RELIEF_AI_NUM_PREDICT` | `128` | Integer 16–256 |

Default model map:

```json
{"fleet":"gemma3:270m","crew":"qwen3:0.6b","weather":"gemma3:270m","airport":"qwen3:0.6b","cargo":"gemma3:270m"}
```

Install the configured models in the loopback Ollama instance before enabling `ollama`. The main simulation guide records the actual installed model versions and digests and the real-model smoke result. Unit tests use injected responses; they make no claim that a model is installed or was tested. A missing model or unreachable endpoint is a labelled deterministic fallback.

## Five-report contract and response validation

The input has exactly `runId`, `revision`, and `agentReports`. `runId` is a UUID and revision is an integer from 0 to 20. There must be exactly one report for each of `fleet`, `crew`, `weather`, `airport`, and `cargo`:

```json
{
  "agentId": "fleet",
  "findings": [{"id":"fleet:1","code":"available","message":"Fictional fixture finding.","entityIds":["SIM-FIXTURE"]}],
  "eligibleIds": ["SIM-FIXTURE"]
}
```

Report and finding objects reject unknown fields. Each report has at most 100 findings and 16 unique eligible IDs. Findings require unique IDs within that report, code, message, and at most 16 unique entity IDs. Strings have strict length and control-character limits; the complete input is capped at 60000 UTF-8 bytes. The annotator snapshots validated reports before async work, preventing caller mutation from changing the response allowlist.

In local mode the annotator calls `/api/generate` serially. The request uses `stream:false`, `think:false`, `keep_alive:0`, temperature 0, seed 26250, bounded context/output, and a JSON schema with `additionalProperties:false`. There is no tool definition, arbitrary chat endpoint, or action interface. The system instruction treats the sealed report as data. The prompt carries only that report's fixed findings. HTTP redirects fail closed.

The generated object must be exactly `{"findingIds":[...]}` with at most three distinct IDs present in that report. The envelope must be completed and identify the configured model. JSON/prose wrappers, extra generated properties, invented IDs, duplicates, malformed JSON, incomplete envelopes, or a mismatched model are rejected. Model text and reasoning never enter the saved annotation. A model selecting no IDs is valid. No-findings reports bypass the model explicitly.

The result contains `runId`, `revision`, `mode`, `modelsUsed`, `highlights`, and `generatedAt`. Each highlight has `agentId`, `findingIds`, and `status`; successful model highlights also carry `model`. Status is `model`, `deterministic`, or `deterministic-fallback`. Overall mode is `ollama` when at least one model succeeds and none fail, `deterministic` for deterministic/no-findings work, or `deterministic-fallback` when any specialist fails. `modelsUsed` lists only models whose validated output was accepted. Every finding remains independently visible in the specialist report.

Fallback selects the first three findings in stable report order and includes only a static `reasonCode`: `capacity`, `closed`, `timeout`, `response-too-large`, `invalid-output`, or `model-unavailable`. No raw exception, returned server error, credential, or environment value is logged or included. The entire body is byte-counted while read, including responses without Content-Length. Timeouts cover both connection and body reads. There is at most one active annotation and one active model call per annotator; concurrent work falls back immediately instead of accumulating a queue.

`close()` marks the annotator closed, aborts its current request, cancels body reading, and awaits the active annotation's settled fallback. Later calls return closed fallback. The simulation service must also compare returned runId/revision to current persisted state before attaching late results, and close the annotator before closing storage.

## Verification and documentation sources

Run the focused tests from `services/ingestion`:

```powershell
node --test test/relief-models.test.js test/relief-ai.test.js
```

Tests cover repeatable training, independent split IDs, baseline comparison, bounded forecasts, strict five-report inputs, configuration and programmatic remote-origin rejection, successful allowlist selection, malformed/prose/invented/duplicate output, missing model, non-completion, timeout, actual streamed byte overflow, stalled bodies, saturation, shutdown, and empty findings.

Context7 was resolved with library name `ollama` to `/ollama/ollama` and queried separately for schema-constrained generation and thinking control. The source material is Ollama's official [generate API documentation](https://docs.ollama.com/api/generate), [structured output documentation](https://docs.ollama.com/capabilities/structured-outputs), and [thinking documentation](https://docs.ollama.com/capabilities/thinking). Schema conformance is independently checked in this module regardless of provider support.
