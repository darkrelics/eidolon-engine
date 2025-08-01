# Data Validation Strategy

This document outlines the data validation strategy for consistent communication between the Flutter frontend and Python backend in the Eidolon Engine incremental game.

## Overview

The system uses a standardized approach to ensure data consistency:

1. **PascalCase** for all API field names
2. **Strict validation** on both frontend and backend
3. **Shared schemas** for common data structures
4. **Type safety** enforced at both ends

## Field Naming Convention

### API Communication

- All API requests and responses use **PascalCase** field names
- Examples: `CharacterID`, `StoryName`, `TimeRemaining`
- This matches AWS DynamoDB field naming conventions

### Internal Storage

- Frontend may use camelCase internally for Flutter conventions
- Backend uses PascalCase consistently
- Conversion happens at API boundaries

## Validation Layers

### Frontend Validation

Located in `incremental/lib/utils/`:

- `api_validation.dart` - Core validation utilities
- `api_parser.dart` - Standardized response parsing

Features:

- Required field validation
- Type checking
- UUID format validation
- Schema-based validation

### Backend Validation

Located in `eidolon/requests.py`:

- Strict field validation functions
- Type checking
- Required/optional field handling
- Consistent error messages

## Common Schemas

### Character Response

```json
{
  "Character": {
    "CharacterID": "uuid",
    "CharacterName": "string",
    "PlayerID": "uuid",
    "Health": "number",
    "MaxHealth": "number",
    "Attributes": "map",
    "Skills": "map"
  }
}
```

### Story Response

```json
{
  "Stories": [
    {
      "StoryID": "uuid",
      "Title": "string",
      "Description": "string",
      "Type": "string",
      "Available": "boolean",
      "CooldownRemaining": "number",
      "EstimatedDuration": "number"
    }
  ]
}
```

### Segment Response

```json
{
  "Segment": {
    "SegmentID": "uuid",
    "StoryID": "uuid",
    "Type": "string",
    "TimeRemaining": "number"
  }
}
```

## Error Handling

### Frontend

- Catches `ValidationException` for field/type errors
- Provides user-friendly error messages
- Logs validation failures for debugging

### Backend

- Returns standardized error format: `{"Error": "message"}`
- HTTP status codes indicate error type
- Detailed error logging for troubleshooting

## Migration Guide

### Updating Frontend Code

1. Replace `JsonUtils.getFlexible()` with `ApiParser` methods
2. Add try-catch blocks for `ValidationException`
3. Ensure all API calls use PascalCase field names

### Updating Backend Code

1. Use strict validation functions from `requests.py`
2. Remove flexible field parsing
3. Ensure all responses use PascalCase

## Best Practices

1. **Always validate** API responses before use
2. **Log validation errors** with context
3. **Test edge cases** like missing/null fields
4. **Document schemas** for new endpoints
5. **Keep validation logic centralized**
