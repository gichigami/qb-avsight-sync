#!/usr/bin/env bash
#
# Build and deploy a QuickBooks -> AvSight Lambda from this repo.
#
# A package is assembled from functions/_shared/ (utils.py, config.py,
# salesforce_connector.py - one canonical copy) plus functions/<function-name>/
# (its handler and anything specific to it). Files are already named as the
# deployed handler expects (lambda_function.lambda_handler), so the build is a
# straight copy plus pinned dependencies.
#
# Usage:
#   scripts/build_and_deploy.sh qb-avsight-sync
#   scripts/build_and_deploy.sh qb-avsight-end-of-day-email
#   scripts/build_and_deploy.sh qb-avsight-sync --dry-run
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FUNCTION_NAME="${1:-}"
DRY_RUN=""
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=1

SRC_DIR="functions/$FUNCTION_NAME"
if [[ -z "$FUNCTION_NAME" || "$FUNCTION_NAME" == "_shared" || ! -d "$SRC_DIR" ]]; then
  echo "usage: $0 <function-name> [--dry-run]" >&2
  echo "available:" >&2
  ls functions/ | grep -v '^_shared$' | sed 's/^/  /' >&2
  exit 2
fi

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "==> Building $FUNCTION_NAME from $SRC_DIR + functions/_shared"

# Shared modules first, then the function's own files (which win on collision).
find functions/_shared -maxdepth 1 -type f -exec cp {} "$BUILD_DIR/" \;
find "$SRC_DIR" -maxdepth 1 -type f ! -name requirements.txt \
  -exec cp {} "$BUILD_DIR/" \;

echo "==> Installing pinned dependencies"
# manylinux wheels so compiled deps (cryptography, cffi, lxml) match the
# Lambda runtime rather than the build machine.
pip install \
  --quiet \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --only-binary=:all: \
  --implementation cp \
  -r "$SRC_DIR/requirements.txt"

# pandas/boto3 come from the AWSSDKPandas layer, pioneer_email from the
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
echo "    scripts/verify_against_prod.sh"
echo "    aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
