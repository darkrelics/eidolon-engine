# Eidolon Engine CloudFormation Templates

This directory contains CloudFormation templates that match the infrastructure created by the CDK deployment in the `../deployment` directory. These templates provide an alternative way to deploy the Eidolon Engine infrastructure using native CloudFormation.

## Template Overview

### Core Infrastructure Templates

1. **iam.yml** - IAM roles and instance profiles for server and Lambda execution
2. **cloudwatch.yml** - CloudWatch log groups and metrics configuration
3. **s3.yml** - S3 buckets for portal, scripts, and Lambda deployment packages
4. **dynamo.yml** - DynamoDB tables for game data including the new story definitions table
5. **cognito.yml** - Cognito User Pool, Identity Pool, and Lambda triggers
6. **lambda.yml** - Lambda functions and API Gateway for both MUD and incremental game
7. **cloudfront.yml** - CloudFront distribution for portal delivery
8. **codebuild.yml** - CodeBuild projects for automated builds

### Master Template

**master.yml** - Orchestrates all stacks in the correct dependency order

## Key Updates for Incremental Game

The templates have been updated to support the incremental game mode:

- **DynamoDB**:
  - Consolidated to use shared tables between MUD and incremental modes
  - Added `story` table with composite key (PlayerID, StoryID)
  - Added `story_definitions` table for story content
  - Removed separate incremental-specific tables

- **Lambda Functions**:
  - Added story management functions (get stories, start story, etc.)
  - Added segment processing function for timed story progression
  - All functions are dual-purpose, serving both Portal and Incremental UI

- **API Gateway**:
  - Extended with `/story` endpoints
  - Maintains existing character management endpoints
  - Single API serves both game modes

## Deployment Instructions

### Prerequisites

1. AWS CLI configured with appropriate credentials
2. S3 bucket for Lambda deployment packages (create this first)
3. Lambda deployment package (`lambda.zip`) and layer (`layer.zip`) uploaded to the S3 bucket

### Individual Stack Deployment

Deploy stacks in this order:

```bash
# 1. IAM roles
aws cloudformation create-stack \
  --stack-name eidolon-iam \
  --template-body file://iam.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=GameName,ParameterValue=eidolon

# 2. CloudWatch
aws cloudformation create-stack \
  --stack-name eidolon-cloudwatch \
  --template-body file://cloudwatch.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=GameName,ParameterValue=eidolon

# 3. S3 buckets
aws cloudformation create-stack \
  --stack-name eidolon-s3 \
  --template-body file://s3.yml \
  --parameters ParameterKey=GameName,ParameterValue=eidolon

# 4. DynamoDB
aws cloudformation create-stack \
  --stack-name eidolon-dynamodb \
  --template-body file://dynamo.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters ParameterKey=GameName,ParameterValue=eidolon

# Continue with remaining stacks...
```

### Master Stack Deployment

Alternatively, use the master template to deploy everything:

```bash
aws cloudformation create-stack \
  --stack-name eidolon-master \
  --template-body file://master.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=GameName,ParameterValue=eidolon \
    ParameterKey=LambdaBucketName,ParameterValue=your-lambda-bucket \
    ParameterKey=ReplyEmailAddress,ParameterValue=noreply@yourdomain.com
```

## Configuration Parameters

### Common Parameters

- **GameName**: Base name for all resources (default: "eidolon")
- **LambdaBucketName**: S3 bucket containing Lambda deployment packages
- **LambdaZipKey**: S3 key for Lambda code (default: "lambda.zip")
- **LayerZipKey**: S3 key for Lambda layer (default: "layer.zip")

### Optional Parameters

- **PortalDomainName**: Custom domain for CloudFront distribution
- **ApiDomainName**: Custom domain for API Gateway
- **CertificateArn**: ACM certificate for custom domains
- **CloudWatchRetentionDays**: Log retention period (default: 365)

## Differences from CDK Deployment

While these templates create the same infrastructure as the CDK deployment, there are some differences:

1. **Configuration**: Uses CloudFormation parameters instead of config.yml
2. **Table Names**: Fixed naming convention vs CDK's configurable names
3. **Import Support**: Limited compared to CDK's existing resource import
4. **Custom Domains**: Requires manual Route53 configuration
5. **EventBridge**: Story timing uses scheduled Lambda invocations

## Story Timing Implementation

Instead of a Fargate container, the CloudFormation approach uses:

- EventBridge rules created dynamically for each story segment
- Lambda function (`process-segment`) triggered by EventBridge
- 1-second resolution maintained through Lambda scheduling

## Cost Considerations

The CloudFormation deployment maintains the same serverless, pay-per-use model:

- DynamoDB: Pay-per-request pricing
- Lambda: Pay per invocation
- S3: Pay for storage and requests
- CloudFront: Pay for data transfer

Estimated monthly cost for 10,000 concurrent users: $160-320

## Troubleshooting

1. **Stack Creation Failures**: Check CloudFormation events for specific errors
2. **Lambda Deployment**: Ensure deployment packages exist in S3 bucket
3. **Custom Domains**: Verify ACM certificate is in us-east-1 for CloudFront
4. **IAM Permissions**: Use CAPABILITY_NAMED_IAM for stacks with IAM resources

## Next Steps

After deployment:

1. Upload Lambda code to the Lambda S3 bucket
2. Upload portal build to the portal S3 bucket
3. Create story definitions in the story_definitions table
4. Configure Route53 for custom domains (if used)
5. Test the API endpoints and portal access
