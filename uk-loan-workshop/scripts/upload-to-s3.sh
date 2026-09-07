#!/bin/bash
# Upload workshop assets to S3
# Uses Workshop Studio session token (set env vars first from Workshop Studio → Repository access)

WORKSHOP_ID="09251ea8-b1f3-444a-92c7-035dc45055b8"
S3_BUCKET="ws-assets-us-east-1"
S3_PREFIX="${WORKSHOP_ID}"
REGION=${AWS_DEFAULT_REGION:-us-east-1}
ASSETS_DIR="./assets"

echo "📤 Workshop S3 Asset Manager"
echo "============================="
echo "Bucket: s3://${S3_BUCKET}/${S3_PREFIX}"
echo ""

ACTION=${1:-upload}

case "$ACTION" in
    download)
        echo "⬇️  Downloading assets from S3..."
        mkdir -p "$ASSETS_DIR"
        aws s3 sync "s3://${S3_BUCKET}/${S3_PREFIX}" "$ASSETS_DIR" --delete --region "$REGION"
        echo "✅ Assets downloaded to: ${ASSETS_DIR}/"
        ;;
    
    upload)
        echo "⬆️  Uploading assets to S3..."
        if [ ! -d "$ASSETS_DIR" ]; then
            echo "❌ Assets directory not found: ${ASSETS_DIR}"
            echo "   Create the directory and add your files first."
            exit 1
        fi
        aws s3 sync "$ASSETS_DIR" "s3://${S3_BUCKET}/${S3_PREFIX}" --delete --region "$REGION"
        echo "✅ Assets uploaded to: s3://${S3_BUCKET}/${S3_PREFIX}"
        ;;
    
    upload-layer)
        echo "⬆️  Uploading Strands SDK Lambda layer..."
        LAYER_DIR="/tmp/strands-layer"
        LAYER_ZIP="/tmp/strands-sdk-layer.zip"
        
        echo "   Installing packages..."
        mkdir -p "${LAYER_DIR}/python"
        pip3 install strands-agents boto3 pydantic mcp -t "${LAYER_DIR}/python" -q
        
        echo "   Creating zip..."
        cd "$LAYER_DIR" && zip -r "$LAYER_ZIP" python/ -q && cd -
        
        echo "   Uploading to S3..."
        aws s3 cp "$LAYER_ZIP" \
            "s3://${S3_BUCKET}/${S3_PREFIX}/layers/strands-sdk-layer.zip" \
            --region "$REGION"
        
        echo "✅ Lambda layer uploaded: s3://${S3_BUCKET}/${S3_PREFIX}/layers/strands-sdk-layer.zip"
        ;;
    
    *)
        echo "Usage: $0 [download|upload|upload-layer]"
        echo ""
        echo "  download      — Sync assets from S3 to local ./assets/ folder"
        echo "  upload        — Sync local ./assets/ folder to S3 (default)"
        echo "  upload-layer  — Build and upload Strands SDK Lambda layer"
        exit 1
        ;;
esac
