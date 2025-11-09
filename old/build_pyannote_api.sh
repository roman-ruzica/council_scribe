#!/bin/bash
# Build and deployment script for Slovak Transcription Tool with pyannoteAI API

set -e

# Configuration
AWS_REGION=${AWS_REGION:-eu-west-1}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/slovak-transcription-pyannote
IMAGE_TAG=${IMAGE_TAG:-latest}
STACK_NAME=${STACK_NAME:-slovak-transcription-pyannote-api}

echo "Building Slovak Transcription Tool with pyannoteAI API..."

# Check required environment variables
if [ -z "$PYANNOTE_API_KEY" ]; then
    echo "❌ PYANNOTE_API_KEY environment variable is required"
    echo "   Get your API key at: https://console.pyannote.ai/"
    echo "   Set it with: export PYANNOTE_API_KEY=your_api_key_here"
    exit 1
fi

echo "✅ pyannoteAI API key found"

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -f Dockerfile.pyannote -t slovak-transcription-pyannote:${IMAGE_TAG} .

echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPOSITORY}

echo "🏗️  Creating ECR repository if it doesn't exist..."
aws ecr describe-repositories --repository-names slovak-transcription-pyannote --region ${AWS_REGION} || \
aws ecr create-repository --repository-name slovak-transcription-pyannote --region ${AWS_REGION}

echo "📤 Tagging and pushing image to ECR..."
docker tag slovak-transcription-pyannote:${IMAGE_TAG} ${ECR_REPOSITORY}:${IMAGE_TAG}
docker push ${ECR_REPOSITORY}:${IMAGE_TAG}

echo "🚀 Deploying with SAM..."
sam build --use-container --template template.pyannote.yaml
sam deploy \
    --template-file .aws-sam/build/template.yaml \
    --stack-name ${STACK_NAME} \
    --capabilities CAPABILITY_IAM \
    --region ${AWS_REGION} \
    --parameter-overrides \
        PyannoteApiKey=${PYANNOTE_API_KEY} \
    --confirm-changeset

echo "✅ Deployment completed successfully!"

# Get outputs
API_URL=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${AWS_REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
    --output text)

S3_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${AWS_REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
    --output text)

echo ""
echo "🎉 Deployment Summary:"
echo "   API Endpoint: ${API_URL}"
echo "   S3 Bucket: ${S3_BUCKET}"
echo "   ECR Repository: ${ECR_REPOSITORY}"
echo ""
echo "🧪 Test your deployment:"
echo 'curl -X POST "'${API_URL}'" \'
echo '  -H "Content-Type: application/json" \'
echo '  -d '"'"'{"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}'"'"