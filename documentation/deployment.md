# Eidolon Engine Deployment Guide

The Eidolon Engine deploys with plain CloudFormation: the templates in `cf/`
(`eidolon-*.yml`) are orchestrated by `scripts/eidolon_deployment.py`, which
deploys the stacks in order, builds and publishes the Lambda code, triggers the
client build, and writes the resulting resource identifiers back to
`config.yml`. There is no CDK involved.

## Prerequisites

- Python 3.12 or later (always use `python3`)
- AWS CLI configured with credentials that can manage CloudFormation, IAM,
  S3, Lambda, DynamoDB, Cognito, API Gateway, CloudFront, ACM, EventBridge,
  SQS, SSM, and Route53
- Required Python packages: `pip3 install -r requirements/scripts-requirements.txt`
- A Route53 hosted zone for your domain
- An S3 artifacts bucket for Lambda builds (the script validates access)
- A `config.yml` created from `config.template.yml` (the script prompts for
  any missing values and shows current values as defaults)

## Quick Start

```bash
python3 scripts/eidolon_deployment.py
```

The script is interactive: it loads `config.yml`, prompts for each parameter
with the current value as the default (press Enter to keep it), prints the
deployment plan (which stacks the selected mode will deploy), and then runs
the full sequence:

1. Validate configuration, environment, and AWS resources
2. Deploy IAM roles, DynamoDB tables, and ACM certificates
3. Deploy the CodeBuild projects, then build and publish the Lambda layer and
   function packages
4. Deploy the Cognito Lambda functions, the Cognito user pool, the character
   Lambda functions, and (in incremental/hybrid modes) the story Lambda
   functions
5. Deploy the API Gateway, the client CloudFront distribution, and the client
   CodeBuild project, then trigger the client build
6. Upload Lua scripts (MUD mode), deploy CloudWatch dashboards (MUD/hybrid),
   update `config.yml` with stack outputs, and verify CloudFront

Re-running the script is safe: existing stacks are updated in place, and the
prompts default to the previously used values.

## Deployment Modes

| Mode | Game systems | Client app built | Notes |
| --- | --- | --- | --- |
| `mud` | MUD only | `portal/` (`buildspec/portal.yml`) | Lua scripts uploaded; CloudWatch deployed |
| `incremental` | Incremental only | `incremental/` (`buildspec/incremental.yml`) | Story stack deployed |
| `hybrid` | Both | `incremental/` (`buildspec/incremental.yml`) | Story stack and CloudWatch deployed |

Exactly one client app is built and served per deployment; the mode selects
the buildspec. The story infrastructure (SQS queues, EventBridge poller, story
Lambda functions) deploys only in incremental and hybrid modes.

## System Architecture

This section is the canonical infrastructure overview referenced by other
documentation. The infrastructure is twelve CloudFormation stacks, deployed
from `cf/` in this order:

| Stack | Template | Modes | Contents |
| --- | --- | --- | --- |
| `eidolon-roles` | `cf/eidolon-roles.yml` | all | Lambda execution and service IAM roles |
| `eidolon-dynamo` | `cf/eidolon-dynamo.yml` | all | All DynamoDB tables |
| `eidolon-certificate` | `cf/eidolon-certificate.yml` | all | ACM certificates for the API and client domains |
| `eidolon-codebuild` | `cf/eidolon-codebuild.yml` | all | CodeBuild projects that build the Lambda layer and functions |
| `eidolon-lambda-cognito` | `cf/eidolon-lambda-cognito.yml` | all | Cognito trigger Lambda functions |
| `eidolon-cognito` | `cf/eidolon-cognito.yml` | all | Cognito user pool and client |
| `eidolon-lambda-character` | `cf/eidolon-lambda-character.yml` | all | Character, archetype, item, and store API functions |
| `eidolon-lambda-story` | `cf/eidolon-lambda-story.yml` | incremental, hybrid | Story/segment API and ops functions, SQS queues, EventBridge poller rule, SSM poller state |
| `eidolon-api-gateway` | `cf/eidolon-api-gateway.yml` | all | REST API, routes, Cognito authorizer, WAF associations |
| `eidolon-portal-cloudfront` | `cf/eidolon-portal-cloudfront.yml` | all | CloudFront distribution and S3 bucket for the client app |
| `eidolon-codebuild-portal` | `cf/eidolon-codebuild-portal.yml` | all | CodeBuild project that builds the Flutter client (buildspec per mode) |
| `eidolon-cloudwatch` | `cf/eidolon-cloudwatch.yml` | mud, hybrid | CloudWatch dashboards |

A thirteenth template, `cf/eidolon-s3-scripts.yml`, provisions the Lua scripts
bucket used by the MUD-mode script upload step.

Lambda code is packaged by CodeBuild (a shared layer containing `eidolon/`
plus one zip per handler in `lambda/`), uploaded to the artifacts bucket, and
the script then updates each deployed function's code from S3. The lists of
functions to update live in `scripts/eidolon_deployment.py` alongside the
stack templates that define them.

Story processing in incremental/hybrid modes is event-driven: the EventBridge
rule (deployed disabled) is enabled by `api-story-start` when a story begins,
the poller routes expiring and stuck segments onto the SQS queues, and the
worker functions process and advance them. The poller disables the rule again
when no active segments remain.

## Configuration

`config.yml` (created from `config.template.yml`) is the single configuration
source: deployment mode, region, domain and subdomains, GitHub
owner/repo/branch for CodeBuild, and the S3 bucket names. After each
deployment the script writes the generated identifiers (Cognito pool/client
IDs, queue URLs, distribution IDs, bucket names) back into `config.yml`, so
subsequent runs and operational scripts can use them.

## Operations

- **Queue recovery**: there are deliberately no dead-letter queues. The
  database is the authoritative state and SQS messages are disposable nudges
  the poller regenerates from table state, so lost or expired messages cost
  nothing; queue retention is 24 hours to match the longest segment cycle.
- **Observability is logs-based by design** (a cost decision - no CloudWatch
  alarms, SNS topics, or DynamoDB point-in-time recovery are provisioned).
  Investigate pipeline issues through the Lambda log groups; static game-data
  tables are reloadable from the repository via `database/data_loader.py`.

## Verification and Troubleshooting

- **ACM validation**: first-time certificate creation waits for DNS
  validation; ensure the Route53 hosted zone serves the domain you entered.
- **CloudFront propagation**: the final verification step may report the
  distribution as not yet operational; propagation can take several minutes
  after the script finishes.
- **Client rebuilds**: to redeploy only the client, trigger the
  `eidolon-portal-build` CodeBuild project (the buildspec syncs the build to
  S3 and invalidates CloudFront).
- **Lambda-only updates**: re-running the script updates function code from
  the latest S3 artifacts after the build steps complete.

## Related Documentation

- `documentation/deployment-modes.md` - mode behavior details
- `documentation/cloudformation.md` - template conventions
- `documentation/incremental-design.md` - incremental game architecture
- `config.template.yml` - configuration schema
