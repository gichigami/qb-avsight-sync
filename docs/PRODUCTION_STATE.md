# Production State

Snapshot of the deployed AWS resources for the QuickBooks → AvSight automation,
captured **2026-08-28** by reading the live Lambda packages and configuration
(`aws lambda get-function`, `aws events list-targets-by-rule`).

The code in this repo was synced to match these deployed packages byte-for-byte.
Keep this file updated when infrastructure changes.

- **AWS account:** `904198142431`
- **Region:** `us-east-1`

## Lambda functions

| | `qb-avsight-sync` | `qb-avsight-end-of-day-email` |
|---|---|---|
| Source in repo | `qb-avsight-sync.py` | `end_of_day_email.py` |
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
