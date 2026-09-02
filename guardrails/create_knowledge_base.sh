#!/bin/bash
set -euo pipefail

KB_NAME="demokb123"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="kb-${KB_NAME}-${ACCOUNT_ID}"
ROLE_NAME="AmazonBedrockExecutionRoleForKB-${KB_NAME}"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
EMBEDDING_MODEL="amazon.titan-embed-text-v2:0"
EMBEDDING_MODEL_ARN="arn:aws:bedrock:${REGION}::foundation-model/${EMBEDDING_MODEL}"
VECTOR_BUCKET_NAME="${KB_NAME}-vectors-${ACCOUNT_ID}"
VECTOR_INDEX_NAME="${KB_NAME}-index"

echo "============================================"
echo " Bedrock KB Setup: ${KB_NAME} (S3 Vectors)"
echo "============================================"
echo "  Account: ${ACCOUNT_ID} | Region: ${REGION}"
echo ""

# --- Step 1: S3 bucket for source documents ---
echo "[1/5] Creating S3 bucket: ${BUCKET_NAME}..."
if aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null; then
  echo "  Already exists, skipping."
else
  if [ "${REGION}" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "${BUCKET_NAME}" > /dev/null
  else
    aws s3api create-bucket --bucket "${BUCKET_NAME}" \
      --create-bucket-configuration LocationConstraint="${REGION}" > /dev/null
  fi
  echo "  Created."
fi

# --- Step 2: S3 Vectors bucket + index ---
echo ""
echo "[2/5] Creating S3 Vectors bucket and index..."
VB_OUTPUT=$(aws s3vectors create-vector-bucket \
  --vector-bucket-name "${VECTOR_BUCKET_NAME}" \
  --output json 2>&1) || true
if echo "${VB_OUTPUT}" | grep -q "ConflictException\|vectorBucket"; then
  echo "  Vector bucket ready."
else
  echo "  ERROR: ${VB_OUTPUT}" && exit 1
fi

VECTOR_BUCKET_ARN="arn:aws:s3vectors:${REGION}:${ACCOUNT_ID}:bucket/${VECTOR_BUCKET_NAME}"

VI_OUTPUT=$(aws s3vectors create-index \
  --vector-bucket-name "${VECTOR_BUCKET_NAME}" \
  --index-name "${VECTOR_INDEX_NAME}" \
  --data-type float32 \
  --dimension 1024 \
  --distance-metric cosine \
  --metadata-configuration 'nonFilterableMetadataKeys=AMAZON_BEDROCK_TEXT_CHUNK,AMAZON_BEDROCK_METADATA' \
  --output json 2>&1) || true
if echo "${VI_OUTPUT}" | grep -q "ConflictException\|index"; then
  echo "  Vector index ready."
else
  echo "  ERROR: ${VI_OUTPUT}" && exit 1
fi

VECTOR_INDEX_ARN="${VECTOR_BUCKET_ARN}/index/${VECTOR_INDEX_NAME}"

# --- Step 3: IAM service role ---
echo ""
echo "[3/5] Creating IAM role: ${ROLE_NAME}..."
ROLE_OUTPUT=$(aws iam create-role \
  --role-name "${ROLE_NAME}" \
  --assume-role-policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Principal\": {\"Service\": \"bedrock.amazonaws.com\"},
      \"Action\": \"sts:AssumeRole\",
      \"Condition\": {
        \"StringEquals\": {\"aws:SourceAccount\": \"${ACCOUNT_ID}\"},
        \"ArnLike\": {\"aws:SourceArn\": \"arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:knowledge-base/*\"}
      }
    }]
  }" --output json 2>&1) || true
ROLE_CREATED=false
if echo "${ROLE_OUTPUT}" | grep -q "EntityAlreadyExists"; then
  echo "  Role already exists."
elif echo "${ROLE_OUTPUT}" | grep -q "Role"; then
  echo "  Role created."
  ROLE_CREATED=true
else
  echo "  ERROR creating role: ${ROLE_OUTPUT}" && exit 1
fi

aws iam put-role-policy \
  --role-name "${ROLE_NAME}" \
  --policy-name KBPermissions \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [
      {
        \"Effect\": \"Allow\",
        \"Action\": [\"bedrock:ListFoundationModels\",\"bedrock:ListCustomModels\"],
        \"Resource\": \"*\"
      },
      {
        \"Effect\": \"Allow\",
        \"Action\": \"bedrock:InvokeModel\",
        \"Resource\": \"${EMBEDDING_MODEL_ARN}\"
      },
      {
        \"Effect\": \"Allow\",
        \"Action\": [\"s3:GetObject\",\"s3:ListBucket\"],
        \"Resource\": [\"arn:aws:s3:::${BUCKET_NAME}\",\"arn:aws:s3:::${BUCKET_NAME}/*\"]
      },
      {
        \"Effect\": \"Allow\",
        \"Action\": [\"s3vectors:PutVectors\",\"s3vectors:GetVectors\",\"s3vectors:DeleteVectors\",\"s3vectors:QueryVectors\",\"s3vectors:GetIndex\"],
        \"Resource\": \"${VECTOR_INDEX_ARN}\"
      }
    ]
  }"
echo "  Role and policies ready."

if [ "${ROLE_CREATED}" = true ]; then
  echo "  Waiting 15s for IAM propagation..."
  sleep 15
fi

# --- Step 4: Create Knowledge Base ---
echo ""
echo "[4/5] Creating Knowledge Base: ${KB_NAME}..."
EXISTING_KB=$(aws bedrock-agent list-knowledge-bases --output json 2>&1 \
  | jq -r ".knowledgeBaseSummaries[] | select(.name==\"${KB_NAME}\") | .knowledgeBaseId")

if [ -n "${EXISTING_KB}" ]; then
  KB_ID="${EXISTING_KB}"
  echo "  Already exists. KB ID: ${KB_ID}"
else
  KB_RESPONSE=$(aws bedrock-agent create-knowledge-base \
    --name "${KB_NAME}" \
    --role-arn "${ROLE_ARN}" \
    --knowledge-base-configuration "{
      \"type\": \"VECTOR\",
      \"vectorKnowledgeBaseConfiguration\": {
        \"embeddingModelArn\": \"${EMBEDDING_MODEL_ARN}\"
      }
    }" \
    --storage-configuration "{
      \"type\": \"S3_VECTORS\",
      \"s3VectorsConfiguration\": {
        \"vectorBucketArn\": \"${VECTOR_BUCKET_ARN}\",
        \"indexName\": \"${VECTOR_INDEX_NAME}\"
      }
    }" \
    --output json)
  KB_ID=$(echo "${KB_RESPONSE}" | jq -r '.knowledgeBase.knowledgeBaseId')
  echo "  Created. KB ID: ${KB_ID}"
fi

# --- Step 5: Create data source ---
echo ""
echo "[5/5] Creating S3 data source (fixed-size chunking)..."
EXISTING_DS=$(aws bedrock-agent list-data-sources --knowledge-base-id "${KB_ID}" --output json 2>&1 \
  | jq -r ".dataSourceSummaries[] | select(.name==\"${KB_NAME}-s3-source\") | .dataSourceId")

if [ -n "${EXISTING_DS}" ]; then
  DS_ID="${EXISTING_DS}"
  echo "  Already exists. Data Source ID: ${DS_ID}"
else
  DS_RESPONSE=$(aws bedrock-agent create-data-source \
    --knowledge-base-id "${KB_ID}" \
    --name "${KB_NAME}-s3-source" \
    --data-source-configuration "{
      \"type\": \"S3\",
      \"s3Configuration\": {
        \"bucketArn\": \"arn:aws:s3:::${BUCKET_NAME}\"
      }
    }" \
    --vector-ingestion-configuration "{
      \"chunkingConfiguration\": {
        \"chunkingStrategy\": \"FIXED_SIZE\",
        \"fixedSizeChunkingConfiguration\": {
          \"maxTokens\": 300,
          \"overlapPercentage\": 15
        }
      }
    }" \
    --output json)
  DS_ID=$(echo "${DS_RESPONSE}" | jq -r '.dataSource.dataSourceId')
  echo "  Created. Data Source ID: ${DS_ID}"
fi

# --- Done ---
echo ""
echo "============================================"
echo " Done!"
echo "============================================"
echo "  KB ID:       ${KB_ID}"
echo "  S3 Bucket:   s3://${BUCKET_NAME}/"
echo "  DS ID:       ${DS_ID}"
echo ""
echo "Next steps:"
echo "  aws s3 cp your-file.pdf s3://${BUCKET_NAME}/"
echo "  aws bedrock-agent start-ingestion-job --knowledge-base-id ${KB_ID} --data-source-id ${DS_ID}"
echo "  export STRANDS_KNOWLEDGE_BASE_ID=${KB_ID}"
