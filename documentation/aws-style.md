# AWS Infrastructure Style Guide for Eidolon Engine

## Overview

This document defines coding standards and naming conventions for AWS infrastructure code in the Eidolon Engine project. All infrastructure code must follow these style guidelines for consistency and maintainability.

## Core Principles

### 1. Lambda Function Architecture Standards

**REQUIREMENT**: Lambda functions must NOT directly invoke other Lambda functions. Use intermediary messaging services:

- **SQS** for reliable message queuing
- **EventBridge** for scheduled tasks
- **SNS** for pub/sub patterns
- **Step Functions** for complex orchestration

### 2. File Format Standards

**REQUIREMENT**: YAML is the preferred format for all configuration files.

#### Format Rules

- CloudFormation templates: YAML only (`.yml` extension)
- CDK configuration: JSON allowed only for `cdk.json`
- Infrastructure definitions: YAML
- Project configuration: YAML

### 3. Resource Naming Conventions

#### Naming Standards

**External/Shared Resources**: `{project}-{component}`

- API Gateway: `eidolon-api`
- Lambda Layer: `eidolon-dependencies`
- IAM Roles: `eidolon-lambda-execution-role`

**Internal/Isolated Resources**: `{component}` (no project prefix)

- Lambda Functions: `api-segment-history`, `ops-segment-poller`, `cognito-player-new`
- SQS Queues: `processing`, `advancement`
- DynamoDB Tables: `players`, `characters`, `rooms`
- EventBridge Rules: `eidolon-story-poller`

Since each environment uses separate AWS accounts, prefixes are only needed for resources that could have naming conflicts or are externally referenced.

#### Lambda Function Naming

**Source File Names** use underscores with specific prefixes:

- **`api_`** - Functions accessible via API Gateway (e.g., `api_segment_history.py`)
- **`cognito_`** - Functions triggered by Cognito events (e.g., `cognito_player_new.py`)
- **`ops_`** - Backend operational functions (e.g., `ops_segment_poller.py`)

**Deployed Function Names** use dashes with no project prefix:

- API Functions: `api-segment-history`, `api-story-start`
- Cognito Functions: `cognito-player-new`, `cognito-player-delete`
- Ops Functions: `ops-segment-poller`, `ops-story-advance`

### 4. CDK Code Style Standards

#### Module Organization Rules

- **Maximum Size**: 1000 lines (300 lines preferred)
- **Single Responsibility**: Each stack focuses on one service area
- **Fixed Logical IDs**: Use consistent identifiers for persistent resources
- **No AWS Calls**: CDK stack classes must not contain boto3 client instantiations

#### Resource Management Style

- Use `RemovalPolicy.RETAIN` for persistent data resources
- Pass region as explicit parameter, not CDK token
- Use CDK context for parameters, not argparse
- Separate app file for each stack

### 5. Resource Management Standards

#### Data Resource Protection

- Use `RemovalPolicy.RETAIN` for all persistent data resources (S3, DynamoDB)
- Implement both CloudFormation deletion policies for DynamoDB tables
- Apply fixed logical IDs to prevent resource recreation during updates

#### Import Patterns

- Check for existing resources in deployment layer, not CDK stacks
- Pass existence status via CDK context to stack constructors
- Use `from_bucket_name()` and similar methods for existing resources

#### S3 Bucket Management

For imported S3 buckets, set permissions post-deployment:

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

### 6. Cost Optimization Standards

#### DynamoDB Configuration

- Use on-demand billing for development and testing environments
- Implement auto-scaling for production workloads
- Enable point-in-time recovery selectively based on data criticality

#### Lambda Resource Sizing

- Right-size memory allocations based on actual usage patterns
- Use ARM-based Graviton2 processors where compatible
- Implement appropriate timeout values to prevent runaway costs

### 8. Security Standards

#### Data Handling Style

- No hardcoded passwords, secrets, or API keys in code
- Use SSM Parameter Store for configuration values
- Environment variables for non-sensitive configuration
- Implement least-privilege IAM with managed policies

### 9. Resource Tagging Standards

All resources must include:

```yaml
Tags:
  - Key: Project
    Value: eidolon
```

### 10. Code Quality Standards

#### General Guidelines

- Use descriptive variable names that explain purpose
- Follow consistent error handling patterns
- Implement proper logging for operational visibility
- Use safe dictionary access with `.get()` method

#### Infrastructure Code

- Use managed policies over inline policies
- Document custom policy requirements
- Implement consistent timeout and memory configurations
- Use on-demand billing for development environments

## Style Compliance Checklist

Before committing infrastructure code changes:

#### Code Style

- [ ] Uses fixed logical IDs for all persistent resources
- [ ] No boto3 calls in CDK stack classes
- [ ] Passes region as explicit parameter, not CDK token
- [ ] Uses CDK context for parameters, not argparse
- [ ] Each module under 1000 lines (300 preferred)
- [ ] Separate app file for each stack

#### Naming Conventions

- [ ] Follows naming conventions (external: eidolon-{component}, internal: {component})
- [ ] Lambda files use underscore prefixes (api*, cognito*, ops\_)
- [ ] Deployed Lambda names use dash format
- [ ] Uses YAML for CloudFormation templates

#### Resource Standards

- [ ] S3 buckets have RemovalPolicy.RETAIN
- [ ] DynamoDB tables have retention policies
- [ ] Uses import patterns for existing resources
- [ ] Implements post-deployment permission updates
- [ ] Includes required tags (Project: eidolon)
- [ ] Implements least-privilege IAM with managed policies
- [ ] No sensitive data storage in code
- [ ] Has CloudWatch logs configured

#### Cost Optimization

- [ ] Uses on-demand billing for development
- [ ] Right-sized Lambda memory allocations
- [ ] Appropriate timeout values configured

## References

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS CDK Best Practices](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html)

For implementation details, deployment procedures, and architectural patterns, see:

- `deployment.md` - Deployment procedures and system architecture
- `cloudformation.md` - CloudFormation template documentation
- `lambda-functions.md` - Lambda function implementation details
