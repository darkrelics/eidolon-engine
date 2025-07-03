# CDK Python API Integration

This document describes the migration from subprocess-based CDK execution to a more robust Python API integration.

## Changes Made

### 1. New Module: `cdk_api_integration.py`

- Created a new module that provides a clean Python API for CDK operations
- Replaces direct subprocess calls with a structured interface
- Provides better error handling and progress monitoring

### 2. Key Features

#### Enhanced Error Handling

- Custom `CDKDeploymentError` exception with detailed error information
- Proper error propagation and context
- Better debugging information for failed deployments

#### Progress Monitoring

- Real-time progress reporting during deployment
- `CDKProgressReporter` class for structured progress events
- Parse and display CloudFormation events as they occur

#### Improved Security

- Proper AWS session and credential management
- Environment variable handling for AWS profiles and regions
- No credential leakage in error messages

### 3. API Methods

- `list_stacks()` - List all CDK stacks
- `synth()` - Synthesize CDK app to CloudFormation
- `deploy()` - Deploy stacks with progress monitoring
- `diff()` - Show differences between local and deployed
- `destroy()` - Destroy stacks
- `bootstrap()` - Bootstrap CDK environment
- `get_stack_outputs()` - Retrieve stack outputs

### 4. Integration with deploy.py

The main deployment orchestrator now uses the CDK API instead of subprocess:

```python
# Before
result = subprocess.run(cdk_command, cwd=self.cdk_dir, env=env, check=True)

# After
result = self.cdk_api.deploy(
    stacks=None,
    context=context,
    require_approval="never" if auto_approve else "broadening",
    progress_callback=progress_reporter
)
```

### 5. Benefits

1. **Better Error Handling**: Structured exceptions with detailed error information
2. **Progress Visibility**: Real-time deployment progress with parsed events
3. **Cleaner Code**: No more subprocess command building and environment manipulation
4. **Type Safety**: Proper type hints and structured return values
5. **Testability**: Easier to mock and test CDK operations
6. **Future-Proof**: Ready for migration to AWS CDK v2 Python API when stable

### 6. Testing

Run the test script to verify the integration:

```bash
cd deployment
python test_cdk_api.py
```

This will test:

- CDK CLI availability
- Stack listing
- Synthesis
- Diff operations

### 7. Notes

- The implementation still uses CDK CLI under the hood for stability
- The AWS CDK Python API (cli_lib_alpha) is not used due to its alpha status
- This provides a migration path for future native Python API adoption
