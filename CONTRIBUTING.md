# Contributing to Eidolon Engine

Thank you for your interest in contributing to Eidolon Engine. This document provides guidelines and standards for contributing to the project.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a feature branch from `develop`
4. Make your changes following the guidelines below
5. Submit a pull request to the `develop` branch

## Code Style Guidelines

### General Principles

- **Simplicity is strongly preferred** - choose the simplest solution that works
- **Follow existing code patterns** - consistency is more important than personal preference
- **Keep functions focused** - each function should have a single responsibility
- **Use descriptive names** - code should be self-documenting
- **Minimal comments** - good code needs few comments; prefer clear naming
- **No emojis** - keep code professional and accessible

### Language-Specific Guidelines

#### Python

- **Python 3.10+ native type hints only**
  - Never import from `typing` module
  - Never use `Any` type
  - Never use Union types
  - Use simple types: `list` not `list[str]`
- **Prefer functions over classes**
- **Exception handling**: catch as `err` not `e`
- **No private functions** - no leading underscores
- **Line length**: 132 characters maximum
- **AWS API responses** should not be cached

Example:

```python
def process_character(character_data: dict) -> dict:
    """Process character data from DynamoDB."""
    try:
        # Implementation here
        return processed_data
    except Exception as err:
        logger.error(f"Failed to process character: {err}")
        raise
```

#### Go

- **Go 1.24+** required
- **Standard Go formatting** - use `go fmt`
- **Error handling** - check all errors explicitly
- **Goroutine safety** - use channels and context for coordination
- **No Hungarian notation** - use Go naming conventions

Example:

```go
func ProcessCharacter(ctx context.Context, data CharacterData) error {
    if err := validateData(data); err != nil {
        return fmt.Errorf("validation failed: %w", err)
    }
    // Implementation
    return nil
}
```

#### Flutter/Dart

- **Flutter 3.29+** required
- **Follow Flutter style guide**
- **Use `flutter analyze` before committing**
- **Null safety** required
- **Widget tests** for UI components

#### Lua

- **Game scripts** should be self-contained
- **Use local variables** to avoid global namespace pollution
- **Follow existing script patterns**

## Testing Requirements

### Before Committing

Always run tests for the code you've modified:

```bash
# Go tests
cd server
go test ./...

# Python linting
black -l 132 --check .

# Flutter tests
cd incremental  # or portal
flutter test
flutter analyze

# Go formatting
go fmt ./...
```

### Test Coverage

- **Unit tests** for pure functions
- **Integration tests** for AWS service interactions are optional
- **Manual testing** for gameplay features
- **Flutter widget tests** for UI components

## Project Structure

Understand where your code belongs:

- `/deployment` - AWS CDK infrastructure code (Python)
- `/lambda` - Lambda function implementations (Python)
- `/eidolon` - Shared Python utilities
- `/scripts_lua` - Lua game scripts
- `/server` - MUD server implementation (Go)
- `/portal` - MUD web frontend (Flutter)
- `/incremental` - Incremental game UI (Flutter)
- `/documentation` - Project documentation

## Pull Request Process

1. **Branch Naming**
   - Feature: `feature/description`
   - Bugfix: `bugfix/issue-number`
   - Hotfix: `hotfix/description`

2. **Commit Messages**
   - Use clear, descriptive messages
   - Reference issue numbers when applicable
   - Example: `Add character inventory management (#123)`

3. **Pull Request Description**
   - Describe what changes you've made
   - Explain why the changes are needed
   - List any breaking changes
   - Include testing steps

4. **Review Process**
   - All PRs require at least one review
   - Address reviewer feedback promptly
   - Keep PRs focused and reasonably sized

## Development Setup

### Prerequisites

- Python 3.12+
- Go 1.24+
- Flutter 3.29+
- AWS CLI configured
- AWS CDK 2.x

### Local Development

1. **Python Dependencies**

   ```bash
   pip install -r requirements/dev-requirements.txt
   pip install -r requirements/lambda-requirements.txt
   ```

2. **Go Dependencies**

   ```bash
   cd server
   go mod download
   ```

3. **Flutter Dependencies**
   ```bash
   cd incremental  # or portal
   flutter pub get
   ```

## Deployment Guidelines

### Infrastructure Changes

- Changes to `/deployment` require careful testing
- Always run `--analyze-only` first
- Configuration drift is detected, not auto-fixed
- No rollback mechanisms - fix forward

### Lambda Functions

- Keep functions small and focused
- Use environment variables for configuration
- Follow the shared module pattern in `/eidolon`
- Test locally before deployment

## Common Patterns

### Error Handling

Python:

```python
try:
    result = aws_operation()
except ClientError as err:
    logger.error(f"AWS operation failed: {err}")
    return error_response(err)
```

Go:

```go
if err := operation(); err != nil {
    return fmt.Errorf("operation failed: %w", err)
}
```

### AWS Service Usage

- Use boto3 for Python AWS operations
- Don't cache AWS API responses
- Handle throttling with exponential backoff
- Use structured logging for CloudWatch

## Questions and Support

- Create an issue for bugs or feature requests
- Join discussions in GitHub Discussions
- Email: contact@darkrelics.net

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
