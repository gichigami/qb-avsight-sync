#!/usr/bin/env bash
#
# Build and deploy the QuickBooks -> AvSight sync Lambdas from this repo.
#
# This repo is the source of truth for these functions. Both deployed Lambdas
# use the handler `lambda_function.lambda_handler`, so the descriptive source
# filename is renamed to lambda_function.py inside the package.
#
# Usage:
#   scripts/build_and_deploy.sh sync           # build + deploy qb-avsight-sync
#   scripts/build_and_deploy.sh eod            # build + deploy end-of-day email
#   scripts/build_and_deploy.sh sync --dry-run # build the zip, don't upload
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGET="${1:-}"
DRY_RUN=""
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=1

case "$TARGET" in
  sync)
    FUNCTION_NAME="qb-avsight-sync"
    HANDLER_SRC="qb-avsight-sync.py"
    # quickbooks_connector is only used by the main sync function.
    MODULES=(quickbooks_connector.py salesforce_connector.py utils.py config.py config.json)
    ;;
  eod)
    FUNCTION_NAME="qb-avsight-end-of-day-email"
    HANDLER_SRC="end_of_day_email.py"
    MODULES=(salesforce_connector.py utils.py config.py config.json)
    ;;
  *)
    echo "usage: $0 {sync|eod} [--dry-run]" >&2
    exit 2
    ;;
esac

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> Building $FUNCTION_NAME from $HANDLER_SRC"

# Lambda's configured handler is lambda_function.lambda_handler.
cp "$HANDLER_SRC" "$BUILD_DIR/lambda_function.py"
for m in "${MODULES[@]}"; do
  cp "$m" "$BUILD_DIR/$m"
done

echo "==> Installing pinned dependencies"
# --only-binary=:all: keeps manylinux wheels so compiled deps (cryptography,
# cffi, lxml) match the Lambda runtime rather than the local machine.
pip install \
  --quiet \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --only-binary=:all: \
  --implementation cp \
  -r requirements.txt

# pandas/boto3 come from the AWSSDKPandas layer; pioneer_email from the
# pioneer-email layer. Drop them if a transitive dep pulled them in.
rm -rf "$BUILD_DIR"/{pandas,numpy,boto3,botocore,pioneer_email}
rm -rf "$BUILD_DIR"/{pandas,numpy,boto3,botocore}-*.dist-info

ZIP_PATH="$REPO_ROOT/build/${FUNCTION_NAME}.zip"
mkdir -p "$REPO_ROOT/build"
rm -f "$ZIP_PATH"
(cd "$BUILD_DIR" && zip -qr "$ZIP_PATH" .)
echo "==> Built $ZIP_PATH ($(du -h "$ZIP_PATH" | cut -f1))"

if [[ -n "$DRY_RUN" ]]; then
  echo "==> Dry run: not uploading."
  exit 0
fi

echo "==> Deploying to $FUNCTION_NAME"
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --output table \
  --query '{Function:FunctionName,Sha:CodeSha256,Size:CodeSize,Modified:LastModified}'

echo "==> Done. Verify with:"
echo "    aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
