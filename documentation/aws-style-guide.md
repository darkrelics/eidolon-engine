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

### 5. Security Standards

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

### 6. Monitoring and Observability

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

### 8. Compliance Checklist

Before deploying any infrastructure changes:

- [ ] Uses YAML for CloudFormation templates
- [ ] No direct Lambda-to-Lambda invocations
- [ ] Follows naming conventions
- [ ] Includes required tags
- [ ] Has CloudWatch logs configured
- [ ] Implements least-privilege IAM
- [ ] No sensitive data storage introduced
- [ ] CDK code synthesizes successfully
- [ ] CloudFormation templates are updated
- [ ] Cost implications documented
- [ ] Monitoring/alarms configured

## References

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS CDK Best Practices](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html)
- [Serverless Application Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)
