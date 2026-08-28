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
| Source in repo | `functions/_shared/` + `functions/qb-avsight-sync/` | `functions/_shared/` + `functions/qb-avsight-end-of-day-email/` |
| Handler | `lambda_function.lambda_handler` | `lambda_function.lambda_handler` |
| Runtime | python3.11 | python3.11 |
| Timeout | 900s | 70s |
| Memory | 1024 MB | 256 MB |
| Ephemeral storage | 1024 MB | 512 MB |
| Env vars | *(none)* | `S3_BUCKET_NAME=qb-avsight-sync-daily-summaries` |
| IAM role | `lambda-execution-role` | `service-role/qb-avsight-sync2-role-cmwssj0z` |
| Log retention | 3 days | 3 days |
| Code deployed | 2026-08-05 | 2026-08-28 |
| `CodeSha256` at snapshot | `SEzIvo7h/+I/7QNzn8MYHKieuj97w73h2zsPfr3YjUs=` | `WjTUwNfgwjmlrR5iiRDbWuMcI5/NfvYkeFnAqs8M9sk=` |

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

### Shared modules (divergence resolved 2026-08-28)

`utils.py`, `config.py` and `salesforce_connector.py` are now a single copy in
`functions/_shared/`, used by both Lambdas.

They had drifted apart through deployment lag, not intent: shared source was
edited, `qb-avsight-sync` was deployed 2026-08-05, and
`qb-avsight-end-of-day-email` was left on its 2026-03-24 build. The EOD copy was
a strict ancestor — it contained nothing the sync's lacked.

Collapsing them was verified safe before deploying. Compared at AST level
(normalising whitespace, comments and `—` vs `—` escaping), only three
functions differed in executable code, plus one addition:

| Function | Difference | Reachable from EOD? |
|---|---|---|
| `find_order_number` | sync dropped the loose `\b\d{5,}\b` bare-number pattern | no |
| `format_timestamp_to_time` | sync renders 24h (`%H:%M`) not 12h (`%I:%M %p`) | no |
| `send_email_summary` | sync adds `po_sync_results`, tuple→dict template rows, traceback on failure | no |
| `send_auth_failure_alert` | added in the sync build only | no |

The EOD handler imports only `get_secret`, `send_end_of_day_email`,
`get_s3_bucket_name` and `debug_print`; the transitive call graph from those
reaches `{get_secret, send_end_of_day_email, get_s3_bucket_name, debug_print,
get_daily_summary_from_s3}` and contains none of the differing functions.
`send_end_of_day_email` itself is identical apart from docstring whitespace, so
its `qb_eod_summary` call is unchanged. Module-level imports and constants
matched; `salesforce_connector.py` was already byte-identical.

`qb-avsight-end-of-day-email` was then redeployed from the shared modules
(2026-08-28, `WjTUwNfgwjmlrR5iiRDbWuMcI5/NfvYkeFnAqs8M9sk=`) and probed with a
date having no S3 summary, which exercises a cold-start import and the secrets,
config and S3 paths, then returns before sending any email. It imported and ran
cleanly under `pioneer-email:8`.

`config.json` and `requirements.txt` remain per-function: the deployments
legitimately differ there (PO-sync settings; `attrs` 25.4.0 vs 26.1.0,
`charset-normalizer` 3.4.5 vs 3.4.6).

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
