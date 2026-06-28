# Error Policy

## Principles

- Prefer explicit uncertainty over silent omission.
- Preserve artifacts even when a run is partial.
- Treat schema failures as blocking for downstream readout.
- Treat connector failures as health findings unless the flow marks that source
  as critical.

## Severity

| Level | Meaning | Action |
| --- | --- | --- |
| `ok` | stage completed | continue |
| `info` | nonblocking note | continue |
| `warn` | degraded input or partial output | continue with caveats |
| `error` | invalid or missing required artifact | stop dependent stages |
| `skipped` | intentionally not run | record reason |

## Required Handling

1. If evidence schema validation fails, do not run analysis agents.
2. If an analysis-agent output is missing, do not run `report_judge`.
3. If a report readout is missing, do not publish a final report.
4. If a connector fails, write the failure to health with source name, time, and
   whether cached data was used.
5. If a chat flow escalates, record the chosen next flow in `chat_judge.json`.

## Artifact Rule

Every failed run still writes `manifest.json` and, when possible, `health.json`.
The manifest is the primary audit record for what was attempted.
