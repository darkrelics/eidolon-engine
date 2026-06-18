# Eidolon Engine CloudFormation Templates

The live CloudFormation templates are the `eidolon-*.yml` files in `cf/`. They
are deployed in dependency order by `scripts/eidolon_deployment.py` according
to the deployment mode; see [Deployment Guide](deployment.md#system-architecture)
for the stack inventory, deployment order, and mode matrix. There is no master
template and no CDK - the script is the orchestrator.

> Historical note: an earlier `cloudformation/` directory (iam.yml, master.yml,
> lambda.yml, ...) mirrored a since-removed CDK deployment. That tree was
> deleted; only `cf/` is real.

## Conventions

- **One template per stack**, named `eidolon-<stack>.yml`, deployed as the
  stack of the same name.
- **Parameters over hardcoding**: cross-stack values (role ARNs, layer ARNs,
  bucket names, allowed origins) are passed as parameters by the deployment
  script, which reads them from prior stacks' outputs. Optional parameters
  carry a `Default` so the script does not need to pass them.
- **Fixed resource names**: tables, functions, queues, and rules use fixed
  names (`characters`, `ops-segment-poller`, `eidolon-processing-queue`) so
  application code and operational tooling can reference them directly.
- **Outputs feed config**: stack outputs are written back into `config.yml`
  by the deployment script (queue URLs, Cognito IDs, distribution IDs).
- **Linting**: all templates must pass `cfn-lint` - the
  `cloudformation-analysis` GitHub workflow gates changes to `cf/*.yml`.

## Data Protection

All tables use `PAY_PER_REQUEST` billing and `DeletionProtectionEnabled: true`.
Point-in-time recovery is deliberately **not** enabled (a cost decision); the
static game-data tables (`rooms`, `exits`, `prototypes`, `archetypes`, `motd`,
`story`, `segments`, `opponents`) are reloadable from the repository via
`database/data_loader.py`.

## Pipeline Reliability (eidolon-lambda-story.yml)

- There are deliberately **no dead-letter queues** and **no CloudWatch
  alarms** (cost decisions): the database is the authoritative state, SQS
  messages are disposable nudges the poller regenerates from table state, and
  observability is logs-based. Queue retention is 24 hours to match the
  longest segment cycle.
- Queue visibility timeout is 180s - 6x the consumer Lambda timeout, per AWS
  guidance for SQS event source mappings.
- Both event source mappings enable `ReportBatchItemFailures`, so a failing
  record retries alone rather than failing its whole batch.

## Story Timing

Story timing uses a single static EventBridge rule (`eidolon-story-poller`,
1-minute rate, deployed disabled) that is enabled when a story starts and
disabled by the poller when no active segments remain. The lifecycle and the
segment recovery behavior are documented in
[incremental-story.md](incremental-story.md#polling-infrastructure).

## Related Documentation

- [Deployment Guide](deployment.md) - stack inventory, order, and modes
- [Database Schema](schema.md) - table contents
- [Incremental Story System](incremental-story.md) - polling and recovery
