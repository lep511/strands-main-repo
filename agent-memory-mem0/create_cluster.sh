#!/bin/bash
# Create an OpenSearch Serverless (AOSS) vector search collection for use with mem0

set -e

COLLECTION_NAME="mem0"
REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN=$(aws sts get-caller-identity --query Arn --output text)
# Extract the role name from the ARN (e.g., arn:aws:sts::123456:assumed-role/MyRole/session -> MyRole)
ROLE_NAME=$(echo "$ROLE_ARN" | cut -d'/' -f2)
IAM_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

echo "Account ID: $ACCOUNT_ID"
echo "IAM Role: $IAM_ROLE_ARN"
echo "Region: $REGION"
echo "Collection: $COLLECTION_NAME"
echo ""

# Step 1: Create encryption policy (required before creating the collection)
echo "Creating encryption policy..."
aws opensearchserverless create-security-policy \
  --name "${COLLECTION_NAME}-encryption" \
  --type encryption \
  --policy "{\"Rules\":[{\"ResourceType\":\"collection\",\"Resource\":[\"collection/${COLLECTION_NAME}\"]}],\"AWSOwnedKey\":true}" \
  --region "$REGION" > /dev/null

echo "Encryption policy created."

# Step 2: Create network policy (public access for simplicity)
echo "Creating network policy..."
aws opensearchserverless create-security-policy \
  --name "${COLLECTION_NAME}-network" \
  --type network \
  --policy "[{\"Rules\":[{\"ResourceType\":\"collection\",\"Resource\":[\"collection/${COLLECTION_NAME}\"]},{\"ResourceType\":\"dashboard\",\"Resource\":[\"collection/${COLLECTION_NAME}\"]}],\"AllowFromPublic\":true}]" \
  --region "$REGION" > /dev/null

echo "Network policy created."

# Step 3: Create data access policy
echo "Creating data access policy..."
aws opensearchserverless create-access-policy \
  --name "${COLLECTION_NAME}-access" \
  --type data \
  --policy "[{\"Rules\":[{\"ResourceType\":\"index\",\"Resource\":[\"index/${COLLECTION_NAME}/*\"],\"Permission\":[\"aoss:CreateIndex\",\"aoss:DeleteIndex\",\"aoss:UpdateIndex\",\"aoss:DescribeIndex\",\"aoss:ReadDocument\",\"aoss:WriteDocument\"]},{\"ResourceType\":\"collection\",\"Resource\":[\"collection/${COLLECTION_NAME}\"],\"Permission\":[\"aoss:CreateCollectionItems\",\"aoss:DeleteCollectionItems\",\"aoss:DescribeCollectionItems\",\"aoss:UpdateCollectionItems\"]}],\"Principal\":[\"${IAM_ROLE_ARN}\"]}]" \
  --region "$REGION" > /dev/null

echo "Data access policy created."

# Step 4: Create the vector search collection
echo "Creating collection '${COLLECTION_NAME}'..."
COLLECTION_ID=$(aws opensearchserverless create-collection \
  --name "$COLLECTION_NAME" \
  --type VECTORSEARCH \
  --region "$REGION" \
  --query "createCollectionDetail.id" \
  --output text)

echo "Collection created with ID: $COLLECTION_ID"

# Step 5: Wait for the collection to become active
echo "Waiting for collection to become ACTIVE (this may take 1-3 minutes)..."
while true; do
  STATUS=$(aws opensearchserverless batch-get-collection \
    --ids "$COLLECTION_ID" \
    --region "$REGION" \
    --query "collectionDetails[0].status" \
    --output text)

  if [ "$STATUS" = "ACTIVE" ]; then
    break
  elif [ "$STATUS" = "FAILED" ]; then
    echo "ERROR: Collection creation failed."
    exit 1
  fi

  echo "  Status: $STATUS - waiting..."
  sleep 10
done

# Step 6: Get the collection endpoint
ENDPOINT=$(aws opensearchserverless batch-get-collection \
  --ids "$COLLECTION_ID" \
  --region "$REGION" \
  --query "collectionDetails[0].collectionEndpoint" \
  --output text)

# Remove the https:// prefix for use in the Python config
HOST=$(echo "$ENDPOINT" | sed 's|https://||')

echo ""
echo "=========================================="
echo "Collection is ACTIVE!"
echo "=========================================="
echo "Collection ID: $COLLECTION_ID"
echo "Endpoint:      $ENDPOINT"
echo "Host:          $HOST"
echo ""
echo "Update open_search_mem0.py with:"
echo "  \"host\": \"${HOST}\""
echo "=========================================="
