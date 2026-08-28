# Production State

Snapshot of the deployed AWS resources for the QuickBooks → AvSight automation,
captured **2026-08-28** by reading the live Lambda packages and configuration
(`aws lambda get-function`, `aws events list-targets-by-rule`).

The code in this repo was synced to match these deployed packages byte-for-byte
and **verified** with `scripts/verify_against_prod.sh`, which re-downloads the
live packages and diffs every first-party file. Re-run it any time; it exits
non-zero on drift. Keep this file updated when infrastructure changes.

- **AWS account:** `904198142431`
- **Region:** `us-east-1`

## Lambda functions

| | `qb-avsight-sync` | `qb-avsight-end-of-day-email` |
|---|---|---|
| Source in repo | `functions/qb-avsight-sync/` | `functions/qb-avsight-end-of-day-email/` |
| Handler | `lambda_function.lambda_handler` | `lambda_function.lambda_handler` |
| Runtime | python3.11 | python3.11 |
| Timeout | 900s | 70s |
| Memory | 1024 MB | 256 MB |
| Ephemeral storage | 1024 MB | 512 MB |
| Env vars | *(none)* | `S3_BUCKET_NAME=qb-avsight-sync-daily-summaries` |
| IAM role | `lambda-execution-role` | `service-role/qb-avsight-sync2-role-cmwssj0z` |
| Log retention | 3 days | 3 days |
| Code deployed | 2026-08-05 | 2026-03-24 |
| `CodeSha256` at snapshot | `SEzIvo7h/+I/7QNzn8MYHKieuj97w73h2zsPfr3YjUs=` | `jyAuVyk+XJGkNTUt8eRID+dKoZ2nE/+BiReJjLlFBEs=` |

### Layers

| Function | Layers |
|---|---|
| `qb-avsight-sync` | `AWSSDKPandas-Python311:24`, `pioneer-email:10` |
| `qb-avsight-end-of-day-email` | `AWSSDKPandas-Python311:24`, `pioneer-email:8` |

`pandas`/`boto3` come from the AWSSDKPandas layer. `pioneer_email` (used by
`utils.py` for the `qb_sync_summary` / `qb_eod_summary` HTML templates) comes
from the internal `pioneer-email` layer. **Neither is vendored into this repo** —
`utils.py` will not import outside Lambda without them.

> The two functions run **different `pioneer-email` layer versions** (10 vs 8).
> Worth reconciling, but noted here rather than changed.

### Package contents

The main sync package ships: `lambda_function.py`, `quickbooks_connector.py`,
`salesforce_connector.py`, `utils.py`, `config.py`, `config.json`.
The end-of-day package ships the same minus `quickbooks_connector.py`.

### Known divergence between the two deployments

The functions are deployed independently and are **not** running the same build
of the shared modules. Each `functions/<name>/` directory mirrors its own
package, so the repo records this accurately rather than papering over it.

| | `qb-avsight-sync` | `qb-avsight-end-of-day-email` |
|---|---|---|
| `utils.py` | 2026-08-05 build | 2026-03-24 build |
| `config.py` | has PO sync accessors | no PO sync accessors |
| `salesforce_connector.py` | identical | identical |
| `attrs` | 25.4.0 | 26.1.0 |
| `charset-normalizer` | 3.4.5 | 3.4.6 |

### Why they differ

Deployment lag, not intent. `utils.py` is shared source; someone edited it,
deployed `qb-avsight-sync` (2026-08-05), and never redeployed
`qb-avsight-end-of-day-email` (last pushed 2026-03-24). The EOD copy is a
strict ancestor of the sync's — it contains nothing the sync lacks.

### Behavioural impact: none on the EOD function

Compared at AST level (which normalises whitespace, comments, and `—` vs
`—` escaping), exactly three functions differ in executable code, plus one
added function:

| Function | Difference | Reachable from EOD? |
|---|---|---|
| `find_order_number` | sync dropped the loose `\b\d{5,}\b` bare-number pattern | no |
| `format_timestamp_to_time` | sync renders 24h (`%H:%M`) instead of 12h (`%I:%M %p`) | no |
| `send_email_summary` | sync adds `po_sync_results`, switches template rows from tuples to dicts, prints a traceback on failure | no |
| `send_auth_failure_alert` | added in the sync build only | no |

The EOD handler imports just `get_secret`, `send_end_of_day_email`,
`get_s3_bucket_name` and `debug_print`. Walking the call graph transitively
from those gives `{get_secret, send_end_of_day_email, get_s3_bucket_name,
debug_print, get_daily_summary_from_s3}` — and **none of the differing
functions appear in it**. `send_end_of_day_email` itself is identical once
docstring whitespace is ignored. Module-level imports and constants are
identical in both copies, and the sync's `config.py` is a strict superset.

Consequence: the older EOD build is not a live defect, **and** swapping in the
sync's `utils.py` would be behaviourally inert for this function — the two are
interchangeable from EOD's perspective. (An earlier revision of this file
claimed such a swap "would be a behaviour change, not a no-op"; that was wrong,
and it also mislabelled `send_auth_failure_alert` as a difference rather than an
addition.)

## Schedules (EventBridge)

| Rule | Expression (UTC) | Target | Input |
|---|---|---|---|
| `qb-avsight-sync-schedule` | `cron(*/15 14-23 * * ? *)` | `qb-avsight-sync` | `{"sync_mode": "incremental"}` |
| `qb-avsight-sync-full-schedule` | `cron(50 13 * * ? *)` | `qb-avsight-sync` | `{"sync_mode": "full"}` |
| `qb-avsight-end-of-day-email` | `cron(2 23 * * ? *)` | `qb-avsight-end-of-day-email` | *(none)* |

Incremental sync runs every 15 minutes during business hours; a full sync runs
once daily at 13:50 UTC, ahead of the business-hours window.

## Secrets (AWS Secrets Manager)

Never committed. Read at runtime by `utils.get_secret()`.

- `quickbooks/credentials` — OAuth client id/secret, access + refresh token,
  realm id. **Rotated by the sync itself:** QuickBooks issues a new refresh
  token on every refresh, and `QuickBooksConnector` writes it back immediately
  via the `on_token_refresh` callback. The execution role needs
  `secretsmanager:UpdateSecret` on this secret.
- `salesforce/credentials` — username, password, security token, instance URL.
- `smtp/credentials` — legacy; the main sync now sends through SES and the
  `pioneer-email` layer.

## S3

Bucket `qb-avsight-sync-daily-summaries`:

| Prefix | Written by | Purpose |
|---|---|---|
| `daily-summaries/` | sync | per-run results the EOD email aggregates |
| `bulk-results/` | sync | full Salesforce bulk write results, for post-mortem |
| `alerts/qb-auth-failure/` | sync | daily throttle markers for OAuth failure alerts |
| `code-backups/`, `deployments/` | manual | pre-existing |

## Related functions (not in scope of this repo's sync)

- `qb-avsight-sync2` — described in AWS as *"formerly handled full sync;
  obsolete"*. No EventBridge rule targets it; full sync is now the
  `sync_mode: full` payload to `qb-avsight-sync`. Candidate for deletion.
- `airbridge-contact-form` — corresponds to `website/` and
  `deploy_packages/contact_form_function/`; a separate automation, not synced here.
