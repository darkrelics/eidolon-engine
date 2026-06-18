# Documentation Index

A map of which documents describe the present system and which are historical
records. Current references are kept accurate as the code changes; historical
records are dated snapshots and are not updated.

## Current Status and Plans

- [incremental-remediation-plan.md](incremental-remediation-plan.md) - current findings, decisions, and remaining work (the authoritative status source)
- [backend-remediation-plan.md](backend-remediation-plan.md) - completed backend remediation (kept as the record of those changes)

## Incremental Game (current references)

- [incremental.md](incremental.md) - system overview and entry point
- [incremental-requirements.md](incremental-requirements.md) - functional and non-functional requirements
- [incremental-design.md](incremental-design.md) - architecture and design decisions
- [incremental-api.md](incremental-api.md) - REST endpoint reference (machine-readable spec: [incremental-openapi.yml](incremental-openapi.yml))
- [incremental-story.md](incremental-story.md) - story/segment state machines, polling, and error recovery
- [incremental-mud-workflow.md](incremental-mud-workflow.md) - character mode transitions
- [incremental-implementation.md](incremental-implementation.md) - implementation guide
- [incremental-architecture-diagrams.md](incremental-architecture-diagrams.md) - diagrams

## Game Systems (current references)

- [mechanics.md](mechanics.md) - core mechanics (checks, XP, sigma outcomes)
- [item-system.md](item-system.md) - items, prototypes, stacking, equipment
- [currency.md](currency.md) - coins as stackable items (top section is authoritative; the rest is design rationale)
- [schema.md](schema.md) - database schema
- [health.md](health.md), [concurrency.md](concurrency.md), [stealth.md](stealth.md), [ordinal.md](ordinal.md), [scripting.md](scripting.md) - subsystem specifications
- [inventory-complexity-analysis.md](inventory-complexity-analysis.md) - client inventory design analysis

## Infrastructure and Operations (current references)

- [deployment.md](deployment.md) - how deployment actually works (CloudFormation via `scripts/eidolon_deployment.py`)
- [deployment-modes.md](deployment-modes.md) - mud / incremental / hybrid mode behavior
- [cloudformation.md](cloudformation.md) - template conventions, data protection, pipeline reliability decisions
- [lambda-functions.md](lambda-functions.md) - Lambda function reference
- [eidolon-library.md](eidolon-library.md) - `eidolon/` module reference
- [cors-configuration.md](cors-configuration.md) - CORS configuration
- [architecture.md](architecture.md) - overall system architecture
- [validation-strategy.md](validation-strategy.md) - validation approach

## Style Guides

- [style-guide.md](style-guide.md) - general standards
- [python-style.md](python-style.md), [flutter-style.md](flutter-style.md), [aws-style.md](aws-style.md) - language/platform standards
- [figma-design-system-rules.md](figma-design-system-rules.md) - design system

## Historical Records (dated snapshots - do not treat as current)

- [release-minus-one-report.md](release-minus-one-report.md) through [release-five-report.md](release-five-report.md) - release reports
- [project-plan-01.md](project-plan-01.md) - project plan record (last revised 2025-11-07)
- [issues.md](issues.md) - GitHub issue audit snapshot from 2025-10-19 (issue states have changed since)
- [deployment-design.md](deployment-design.md) - superseded CDK deployment design (banner inside)
