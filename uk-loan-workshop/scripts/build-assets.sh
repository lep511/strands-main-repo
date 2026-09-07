#!/bin/bash
# Build workshop assets for S3 upload
# Creates zip files for Lambda agents and Lambda layer
# Must be run before upload-to-s3.sh

set -e

WORKSHOP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS_DIR="${WORKSHOP_DIR}/../assets"
WORKSHOP_ID="09251ea8-b1f3-444a-92c7-035dc45055b8"
S3_BUCKET="ws-assets-us-east-1"
REGION=${AWS_DEFAULT_REGION:-us-east-1}

echo "🏗️  Building Workshop Assets"
echo "============================="
echo ""

mkdir -p "$ASSETS_DIR/layers"

# ─────────────────────────────────────────────
# 1. Build Strands SDK Lambda Layer
# ─────────────────────────────────────────────
echo "📦 Building Strands SDK Lambda layer..."
LAYER_TMP="/tmp/strands-layer-build"
rm -rf "$LAYER_TMP"
mkdir -p "${LAYER_TMP}/python"

pip3 install \
    "strands-agents>=0.1.0" \
    "boto3>=1.34.0" \
    "pydantic>=2.0.0" \
    "mcp>=1.0.0" \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    -t "${LAYER_TMP}/python" \
    -q --no-cache-dir

cd "$LAYER_TMP"
zip -r "${ASSETS_DIR}/layers/strands-sdk-layer.zip" python/ -q
cd -
echo "   ✅ layers/strands-sdk-layer.zip"

# ─────────────────────────────────────────────
# 2. Package workshop code as zip
# (participants download this to get started)
# ─────────────────────────────────────────────
echo ""
echo "📦 Packaging workshop code..."
cd "$WORKSHOP_DIR/.."
zip -r "${ASSETS_DIR}/workshop-code.zip" workshop/ \
    --exclude "workshop/.claude/*" \
    --exclude "*.pyc" \
    --exclude "*__pycache__*" \
    -q
echo "   ✅ workshop-code.zip"

# ─────────────────────────────────────────────
# 3. Upload to S3
# ─────────────────────────────────────────────
echo ""
echo "⬆️  Uploading to Workshop Studio S3..."
aws s3 sync "$ASSETS_DIR" "s3://${S3_BUCKET}/${WORKSHOP_ID}" \
    --delete \
    --region "$REGION"

echo ""
echo "✅ All assets built and uploaded!"
echo ""
echo "S3 paths:"
echo "  s3://${S3_BUCKET}/${WORKSHOP_ID}/layers/strands-sdk-layer.zip"
echo "  s3://${S3_BUCKET}/${WORKSHOP_ID}/workshop-code.zip"
echo ""
echo "Workshop Studio magic variables:"
echo "  {{.AssetsBucketName}} → ${S3_BUCKET}"
echo "  {{.AssetsBucketPrefix}} → ${WORKSHOP_ID}/"
