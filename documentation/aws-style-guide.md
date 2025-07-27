# AWS Style Guide for Eidolon Engine

## Overview

This document defines AWS infrastructure patterns and standards for the Eidolon Engine project. All infrastructure code must follow these guidelines to ensure consistency, maintainability, and architectural best practices.

## Core Principles

### 1. Lambda Function Decoupling

**REQUIREMENT**: Lambda functions must NOT directly invoke other Lambda functions. All inter-service communication must use intermediary messaging services.

#### Current State (To Be Refactored)
```python
# INCORRECT - Direct Lambda invocation
lambda_client.invoke(
    FunctionName=function_name,
    InvocationType="Event",
    Payload=json.dumps(payload)
)
```

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
    QueueName: !Sub "${GameName}-process-segment-queue"
    MessageRetentionPeriod: 1209600  # 14 days
    VisibilityTimeout: 180           # 3x Lambda timeout
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
`{project}-{environment}-{component}-{resource-type}`

Examples:
- `eidolon-prod-api-lambda`
- `eidolon-dev-segments-queue`
- `eidolon-prod-story-table`

#### Tag Requirements
All resources must include:
```yaml
Tags:
  - Key: Project
    Value: eidolon
  - Key: Environment
    Value: !Ref Environment
  - Key: ManagedBy
    Value: CDK  # or CloudFormation
  - Key: CostCenter
    Value: gaming
```

### 5. Security Standards

#### IAM Policies
- Follow least privilege principle
- Use managed policies where available
- Document custom policy requirements

```python
# Example: Minimal Lambda execution role
lambda_role = iam.Role(
    self, "lambda-execution-role",
    assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name(
            "service-role/AWSLambdaBasicExecutionRole"
        )
    ]
)
```

#### Secrets Management
- Use AWS Secrets Manager for sensitive data
- Never hardcode credentials
- Rotate secrets regularly

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

### 7. Deployment Patterns

#### Environment Separation
```
deployment/
├── environments/
│   ├── dev.yml
│   ├── staging.yml
│   └── prod.yml
```

#### Blue-Green Deployments
- Use Lambda aliases and weighted routing
- Implement canary deployments for critical functions
- Automate rollback on metric alarms

### 8. Cost Optimization

#### DynamoDB
- Use on-demand billing for dev/test
- Implement auto-scaling for production
- Enable point-in-time recovery selectively

#### Lambda
- Right-size memory allocations
- Use ARM-based Graviton2 where compatible
- Implement proper timeout values

### 9. Refactoring Priorities

Based on current implementation review:

1. **Immediate** (P0):
   - Replace direct Lambda invocations with SQS queues
   - Implement DLQ for all queues

2. **Short-term** (P1):
   - Migrate segment polling from EventBridge direct invocation to SQS
   - Add Circuit Breaker pattern for external calls

3. **Long-term** (P2):
   - Implement Step Functions for complex workflows
   - Add distributed tracing with X-Ray

### 10. Migration Path

#### Phase 1: Messaging Infrastructure
```python
# Add to CDK stack
self.segment_queue = sqs.Queue(
    self, "segment-processing-queue",
    queue_name=f"{prefix}-segment-queue",
    visibility_timeout=cdk.Duration.seconds(180),
    dead_letter_queue=sqs.DeadLetterQueue(
        max_receive_count=3,
        queue=sqs.Queue(self, "segment-dlq")
    )
)
```

#### Phase 2: Lambda Updates
- Modify Lambda functions to publish to queues
- Add SQS event source mappings
- Remove direct invocation code

#### Phase 3: Monitoring
- Add queue depth alarms
- Implement message age monitoring
- Create operational dashboards

## Compliance Checklist

Before deploying any infrastructure changes:

- [ ] Uses YAML for CloudFormation templates
- [ ] No direct Lambda-to-Lambda invocations
- [ ] Follows naming conventions
- [ ] Includes required tags
- [ ] Has CloudWatch logs configured
- [ ] Implements least-privilege IAM
- [ ] CDK code synthesizes successfully
- [ ] CloudFormation templates are updated
- [ ] Cost implications documented
- [ ] Monitoring/alarms configured

## References

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS CDK Best Practices](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html)
- [Serverless Application Lens](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html)