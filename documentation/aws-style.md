# AWS Style Guide for Eidolon Engine

## Overview

This document defines AWS infrastructure patterns and standards for the Eidolon Engine project. All infrastructure code must follow these guidelines to ensure consistency, maintainability, and architectural best practices.

## Core Principles

### 1. Lambda Function Decoupling

**REQUIREMENT**: Lambda functions must NOT directly invoke other Lambda functions. All inter-service communication must use intermediary messaging services.

#### Target State

Lambda functions should communicate through:

- **SQS** (Simple Queue Service) for reliable message queuing
- **EventBridge** for event-driven architectures
- **SNS** (Simple Notification Service) for pub/sub patterns
- **Step Functions** for complex orchestration

#### Example Pattern

```yaml
# EventBridge Rule for segment processing
SegmentProcessingRule:
  Type: AWS::Events::Rule
  Properties:
    EventPattern:
      source:
        - eidolon.segments
      detail-type:
        - Segment Completed
    Targets:
      - Arn: !GetAtt ProcessSegmentQueue.Arn
        Id: "1"

# SQS Queue for segment processing
ProcessSegmentQueue:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: eidolon-segments
    MessageRetentionPeriod: 1209600 # 14 days
    VisibilityTimeout: 180 # 3x Lambda timeout
```

### 2. Configuration File Format

**REQUIREMENT**: YAML is the preferred format for all configuration files.

#### Standards

- CloudFormation templates: YAML only
- CDK configuration: JSON allowed only for `cdk.json`
- API responses: JSON (for compatibility)
- Infrastructure definitions: YAML

#### File Naming Conventions

```
cloudformation/
├── master.yml          # Root template
├── cognito.yml         # Service-specific templates
├── dynamodb.yml
└── lambda.yml

deployment/
├── config.yml          # Deployment configuration
└── parameters.yml      # Environment parameters
```

### 3. Infrastructure as Code Hierarchy

**REQUIREMENT**: CDK is the primary IaC tool, but CloudFormation templates must be maintained for compatibility.

#### Development Workflow

1. **Primary Development**: Use CDK for all new infrastructure
2. **CloudFormation Sync**: Export CDK synthesized templates to CloudFormation directory
3. **Validation**: Ensure CloudFormation templates can deploy independently

#### CDK Standards

```python
# Stack naming convention
class LambdaStack(cdk.Stack):
    """Creates Lambda functions for Eidolon Engine applications."""

    def __init__(self, scope: Construct, lambda_id: str, config: dict, **kwargs):
        # Stack ID format: {project}-{component}-stack
        super().__init__(scope, lambda_id, **kwargs)
```

### 4. Resource Naming Conventions

#### Naming Pattern

`{project}-{component}`

Since each environment has its own AWS account, environment prefixes are unnecessary. Avoid Hungarian notation - the resource type is already clear from the AWS service.

Examples:

- `eidolon-api`
- `eidolon-segments`
- `eidolon-story`

#### Account Structure

- **Development**: Separate AWS account
- **Staging**: Separate AWS account
- **Production**: Separate AWS account

#### Lambda Function Naming

Lambda functions must use specific prefixes based on their purpose:

- **`api_`** - Functions accessible via API Gateway (e.g., `api_get_character`, `api_start_story`)
- **`cognito_`** - Functions triggered by Cognito events (e.g., `cognito_new_player`, `cognito_delete_player`)
- **`ops_`** - Backend operational functions (e.g., `ops_segment_poller`, `ops_process_segment`)

#### Tag Requirements

All resources must include:

```yaml
Tags:
  - Key: Project
    Value: eidolon
  - Key: ManagedBy
    Value: CDK # or CloudFormation
```

### 5. Database Operations Standards

#### DynamoDB Transactions

**GUIDANCE**: Use DynamoDB transactions when atomic, all-or-nothing operations are required across multiple items or tables. Transactions provide ACID guarantees but consume double the read/write capacity units.

##### When to Use Transactions

Use transactions for operations that:

- Must atomically update multiple items as a unit
- Require consistency guarantees across related records
- Need to prevent partial updates during failures
- Implement conditional updates across multiple items

##### When NOT to Use Transactions

Avoid transactions for:

- Single item updates (use standard operations)
- Bulk data imports or exports
- Operations where eventual consistency is acceptable
- High-throughput operations (due to 2x capacity cost)

##### Critical Operations Requiring Transactions

1. **Story Operations**:

   - Starting a story (Character + ActiveSegments + History)
   - Story completion/abandonment (atomic cleanup required)

2. **Character Operations**:

   - Creating character with initial items (Player + Character + Items)
   - Deleting character (ensures complete removal)

3. **Financial/Inventory Operations**:
   - Transferring items between characters
   - Applying rewards that affect multiple tables

##### Transaction Limitations

- Maximum 100 unique items per transaction
- Maximum 4MB total transaction size
- All items must be in same AWS Region
- Cannot target same item multiple times
- Consumes 2x the standard read/write capacity

##### Implementation Guidelines

- Use idempotency tokens to prevent duplicate transactions
- Design for transaction failures with proper error handling
- Monitor capacity consumption (2x standard operations)
- Consider eventual consistency where appropriate
- Batch operations carefully to stay within limits

### 6. Security Standards

#### Design Philosophy

The system is designed to avoid storing sensitive data:

- **Authentication**: Handled entirely by AWS Cognito
- **Payments**: Processed through third-party providers (no PCI data stored)
- **Personal Data**: Minimal - only game-related data stored

#### IAM Policies

- Follow least privilege principle
- Use managed policies where available
- Document custom policy requirements

```python
# Example: Minimal Lambda execution role
lambda_role = iam.Role(
    self, "execution-role",
    assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name(
            "service-role/AWSLambdaBasicExecutionRole"
        )
    ]
)
```

#### Configuration Management

Since CloudFormation doesn't support AWS Secrets Manager references:

- Use SSM Parameter Store for configuration values
- Environment variables for non-sensitive config
- CDK can reference Secrets Manager, but synthesized CF templates cannot

### 6. CDK Development Patterns

#### Critical CDK Lessons from Production

Based on extensive production deployment experience, these patterns must be followed:

##### CDK Synthesis Limitations

- **No AWS Access During Synthesis**: CDK synthesis happens without AWS credentials. Any boto3 calls or resource existence checks will fail
- **Fixed Logical IDs Required**: Use fixed IDs like `"PortalBucket"` not dynamic ones to prevent resource recreation
- **CDK Tokens vs Strings**: `self.region` returns a token, not a string. Pass actual region values as parameters
- **No Runtime Imports**: All imports must be at module level. No dynamic imports or module injection

##### Resource Management Patterns

```python
# CORRECT: Fixed logical ID with RETAIN policy
bucket = s3.Bucket(
    self,
    "ArtifactsBucket",  # Fixed ID - won't change between deployments
    bucket_name=bucket_name,
    removal_policy=RemovalPolicy.RETAIN,
    auto_delete_objects=False,
)

# WRONG: Dynamic ID causes recreation
bucket = s3.Bucket(
    self,
    f"Bucket-{timestamp}",  # Changes every deployment!
    bucket_name=bucket_name,
)
```

##### Import Pattern for Existing Resources

```python
# In deployment module (has AWS access)
def deploy_stack(params):
    from stacks.stack_utilities import check_s3_bucket_exists
    bucket_exists = check_s3_bucket_exists(params.bucket, params.region)
    
    context_args = [
        "-c", f"bucket_exists={'true' if bucket_exists else 'false'}",
    ]
    return run_cdk_deploy("stack", params.region, app_command, context_args)

# In CDK stack
def __init__(self, scope, id, bucket_exists: bool = False, **kwargs):
    if bucket_exists:
        bucket = s3.Bucket.from_bucket_name(self, "Bucket", bucket_name)
    else:
        bucket = s3.Bucket(self, "Bucket", bucket_name=bucket_name,
                          removal_policy=RemovalPolicy.RETAIN)
```

##### DynamoDB Table Protection

```python
# Tables need BOTH retention policies
table = dynamodb.Table(
    self, "PlayersTable",
    table_name="players",
    removal_policy=RemovalPolicy.RETAIN,
    # ... other config
)
# Add CloudFormation deletion policy
cfn_table = table.node.default_child
cfn_table.cfn_options.deletion_policy = CfnDeletionPolicy.RETAIN
```

##### Lambda Layer Version Management

```python
# Post-deployment cleanup of old layer versions
def update_lambda_layer(layer_name: str, s3_key: str):
    # Publish new version
    new_version = lambda_client.publish_layer_version(...)
    
    # Update all functions to use new version
    for function in functions:
        lambda_client.update_function_configuration(
            FunctionName=function,
            Layers=[new_version['LayerVersionArn']]
        )
    
    # Delete old version
    lambda_client.delete_layer_version(
        LayerName=layer_name,
        VersionNumber=old_version
    )
```

##### Module Organization Rules

- **300 Line Limit**: Each module should be under 300 lines (1000 max for complex modules)
- **Single Responsibility**: Each stack does ONE thing (e.g., DynamoDB, Lambda, not both)
- **Separate App Files**: Each stack gets its own `app_*.py` to prevent output contamination
- **Context Over Arguments**: Use CDK context instead of argparse

```python
# app_dynamodb.py
app = cdk.App()
region = app.node.try_get_context("region") or "us-east-1"
tables = json.loads(app.node.try_get_context("tables") or "[]")

dynamodb_stack = DynamoDBStack(app, "dynamodb", region_name=region, tables=tables)
app.synth()
```

##### CloudFront and S3 Integration

For imported S3 buckets, OAI permissions must be set post-deployment:

```python
def update_bucket_policy_for_cloudfront(bucket_name: str, distribution_id: str):
    # Get OAI from CloudFront distribution
    dist = cloudfront_client.get_distribution(Id=distribution_id)
    oai_id = extract_oai_id(dist)
    
    # Create bucket policy for OAI
    policy = {
        "Statement": [{
            "Principal": {
                "AWS": f"arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity {oai_id}"
            },
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket_name}/*"
        }]
    }
    s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
```

##### Build Monitoring Pattern

CodeBuild doesn't have built-in waiters:

```python
# WRONG: Waiter doesn't exist
waiter = codebuild.get_waiter("build_complete")  # Will fail!

# CORRECT: Polling pattern
while True:
    response = codebuild.batch_get_builds(ids=[build_id])
    status = response["builds"][0]["buildStatus"]
    if status in ["SUCCEEDED", "FAILED", "STOPPED"]:
        break
    time.sleep(10)
```

##### Common Pitfalls to Avoid

1. **Square Bracket Dictionary Access**: Use `.get()` method for safe access
2. **Environment Variable Manipulation**: Pass region explicitly, don't rely on CDK environment
3. **Inline IAM Policies**: Always use managed policies
4. **Dynamic Resource Naming**: Causes resource recreation on every deployment
5. **Resource Checks in CDK**: Will always fail during synthesis

### 7. Monitoring and Observability

#### CloudWatch Integration

```python
# Log retention standards
logs.LogGroup(
    self,
    f"{function_name}-logs",
    log_group_name=f"/aws/lambda/{function.function_name}",
    retention=logs.RetentionDays.ONE_WEEK,  # Dev
    # retention=logs.RetentionDays.ONE_MONTH,  # Prod
    removal_policy=cdk.RemovalPolicy.DESTROY
)
```

#### Metrics and Alarms

- Define SLOs for critical functions
- Create alarms for error rates > 1%
- Monitor queue depths and DLQs

### 7. Cost Optimization

#### DynamoDB

- Use on-demand billing for dev/test
- Implement auto-scaling for production
- Enable point-in-time recovery selectively

#### Lambda

- Right-size memory allocations
- Use ARM-based Graviton2 where compatible
- Implement proper timeout values

### 8. Deployment System Architecture

#### Stack Organization

The deployment system consists of 9 CDK stacks deployed sequentially:

1. **CodeBuild**: Build infrastructure for Lambda artifacts
2. **DynamoDB**: 14 tables with retention policies
3. **Lambda**: Layer and 16 functions with shared execution role
4. **Player**: Cognito User Pool with triggers
5. **Story**: SSM, SQS, EventBridge for async processing
6. **S3**: Scripts bucket for Lua files
7. **CloudWatch**: Centralized logging and metrics
8. **API**: API Gateway with custom domain
9. **Client**: S3, CloudFront, CodeBuild for portal

#### Deployment Modes

- **MUD Mode**: Traditional gameplay (excludes Story stack)
- **Incremental Mode**: Story-driven (excludes S3, CloudWatch stacks)  
- **Hybrid Mode**: Full feature set (all stacks)

#### Deployment Commands

```bash
# Deploy infrastructure
cd deployment && python3 deploy.py

# The system will prompt for:
# - AWS Region
# - Deployment Mode
# - S3 bucket names
# - GitHub repository details
# - Domain configuration
# - Cognito reply email
```

### 9. Compliance Checklist

Before deploying any infrastructure changes:

#### CDK Development
- [ ] Uses fixed logical IDs for all persistent resources
- [ ] No boto3 calls or resource checks in CDK synthesis
- [ ] Passes region as explicit parameter, not CDK token
- [ ] Uses CDK context for parameters, not argparse
- [ ] Each module under 300 lines (1000 max)
- [ ] Separate app file for each stack

#### Resource Management
- [ ] S3 buckets have RemovalPolicy.RETAIN
- [ ] DynamoDB tables have both RETAIN policies
- [ ] Existing resources checked in deployment layer
- [ ] Import patterns used for existing resources
- [ ] Post-deployment updates for Lambda code
- [ ] Old Lambda layer versions cleaned up

#### AWS Standards
- [ ] Uses YAML for CloudFormation templates
- [ ] No direct Lambda-to-Lambda invocations
- [ ] Follows naming conventions (eidolon-{component})
- [ ] Includes required tags (Project, ManagedBy)
- [ ] Has CloudWatch logs configured
- [ ] Implements least-privilege IAM with managed policies
- [ ] No sensitive data storage introduced
- [ ] Uses DynamoDB transactions for multi-item operations

#### Deployment Validation
- [ ] CDK code synthesizes successfully
- [ ] All resources verified post-deployment
- [ ] CloudFront OAI permissions updated for imported buckets
- [ ] Build monitoring uses polling, not waiters
- [ ] Cost implications documented
- [ ] Monitoring/alarms configured

## References

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS CDK Best Practices](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html)
- [Serverless Application Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)
