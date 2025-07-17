# Incremental to MUD Character Workflow

## Overview

This document describes how characters transition between Incremental and MUD game modes using the shared backend infrastructure. The GameMode field on each character ensures they can only be active in one mode at a time, preventing concurrent access issues.

## Workflow Steps

### 1. Account Creation

- Player creates account via Incremental UI
- Cognito handles authentication
- Player record created in DynamoDB

### 2. Character Creation

- Player provides character name
- Name validated for uniqueness (bloom filter for efficiency)
- Player selects archetype from shared archetypes table
- Character created with `GameMode: "Incremental"`
- Character stored in shared characters table

### 3. Character Customization (Rapid Inactive)

- Player goes through story-based tutorial
- Character gains XP and equipment
- Skills are dynamically added as used
- Progress tracked in character record

### 4. Mode Transition

Characters can transition between modes with these safeguards:

**Incremental to MUD:**
- Character must not have active story segments
- GameMode updated from "Incremental" to "MUD"
- Character placed in appropriate room
- Full MUD gameplay becomes available

**MUD to Incremental:**
- Character must be in a safe room (not in combat)
- GameMode updated from "MUD" to "Incremental"
- Character position preserved for return
- Incremental story progression resumes

### 5. Concurrent Access Prevention

- Lambda functions check GameMode before any character operation
- Attempts to use character in wrong mode are rejected
- Clear error messages guide players to switch modes properly

## Character Name Management

Since all characters exist in the shared characters table, name uniqueness is enforced at the database level:

### Name Validation Process

1. **Creation Request**: Player submits character name
2. **Lambda Validation**: 
   - Check characters table for existing name
   - Validate name format and content
   - Use conditional write to ensure uniqueness
3. **Database Enforcement**: DynamoDB prevents duplicate names
4. **Error Handling**: Clear message if name already taken

### Bloom Filter Optimization (Future Enhancement)

For performance at scale, a bloom filter could be implemented:
- Fast negative checks (name definitely available)
- Reduce database queries for popular names
- Periodic rebuild from characters table
- Stored in Lambda memory or S3

## Security Considerations

- GameMode field is only modifiable through authorized Lambda functions
- Mode transitions require validation of game state
- IAM roles restrict direct database access
- API Gateway authentication required for all operations

## Performance Optimization

- Character lookups use DynamoDB's consistent performance
- GameMode checks are simple string comparisons
- Lambda functions cache archetype data
- Conditional writes prevent race conditions
