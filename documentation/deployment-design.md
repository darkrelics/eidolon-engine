# Incremental Deployment System Design

## Overview
This system enables incremental infrastructure updates by:
1. Reading existing `server/config.yml` if present
2. Validating current AWS resource states
3. Deploying only changed or missing resources
4. Updating configuration incrementally

## Architecture Components

### 1. State Manager (`deployment/state_manager.py`)
- Reads and writes infrastructure state to local cache
- Tracks deployed resources and their configurations
- Detects configuration drift

### 2. CDK Stack Manager (`deployment/cdk_manager.py`)
- Defines infrastructure using AWS CDK constructs
- Synthesizes CloudFormation from CDK code
- Manages CDK app lifecycle and deployments

### 3. Resource Validator (`deployment/resource_validator.py`)
- Validates individual AWS resources
- Checks resource configurations against desired state
- Handles resource-specific validation logic

### 4. Parameter Manager (`deployment/parameter_manager.py`)
- Manages deployment parameters
- Merges existing config with new requirements
- Prompts only for missing/changed parameters

### 5. Dependency Resolver (`deployment/dependency_resolver.py`)
- Builds dependency graph of resources
- Determines deployment order
- Handles circular dependencies

### 6. Deployment Orchestrator (`deployment/incremental_deploy.py`)
- Main entry point
- Coordinates all components
- Handles rollback on failure

## Deployment Flow

1. **Initialization**
   - Load `server/config.yml` if exists
   - Initialize state manager
   - Load cached deployment state

2. **Discovery Phase**
   - Query existing CloudFormation stacks (deployed by CDK)
   - Validate individual resources
   - Build current state inventory
   - Compare with CDK-defined desired state

3. **Planning Phase**
   - Compare desired vs actual state
   - Identify required changes
   - Build deployment plan

4. **Execution Phase**
   - Deploy/update resources in dependency order
   - Update configuration incrementally
   - Handle errors with rollback capability

5. **Finalization**
   - Update `server/config.yml`
   - Save deployment state
   - Report deployment summary

## Key Benefits
- No complete redeployment for minor changes
- Faster deployment times
- Better error handling and rollback
- Configuration drift detection
- Minimal user input required
- Infrastructure as code with type safety
- Built-in CDK diff capabilities
- Automatic dependency resolution by CDK