# Incremental to MUD Character Workflow

## Overview

This document describes how characters transition between Incremental and MUD game modes using the shared backend infrastructure. The GameMode field on each character ensures they can only be active in one mode at a time, preventing concurrent access issues.

## Workflow Steps

### 1. Account Creation

- Player creates account via Incremental UI
- Cognito handles authentication
- Player record created in DynamoDB

### 2. Character Creation

- Player provides character name and optional archetype selection
- Name format validated (length, allowed characters, etc.)
- Restricted names checked against loaded bloom filter
- Name uniqueness verified using CharacterNameIndex GSI query
- Player's character count checked against limit (max 10 per player)
- Archetype data loaded from archetypes table (defaults used if invalid/missing)
- Starting items created from archetype's prototype list
- Character created with `GameMode: "Incremental"`
- Character record stored in shared characters table
- Player's CharacterList updated with new character entry

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

- Character must be logged out of MUD
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

1. **Creation Request**: Player submits character name via API
2. **Format Validation**:
   - Character name must meet length and character requirements
   - Validated using validate_character_name function
3. **Bloom Filter Check**:
   - Name checked against pre-loaded bloom filter for restricted names
   - Filter loaded from character_name_filter.pkl at Lambda startup
4. **Uniqueness Check**:
   - Query CharacterNameIndex GSI to check if name already exists
   - Uses query_by_gsi function for efficient lookup
5. **Character Creation**:
   - If all checks pass, character record created in characters table
   - No conditional expressions needed as uniqueness already verified
6. **Error Handling**:
   - Returns 400 for validation failures
   - Returns 409 for duplicate names
   - Clear error messages guide player to choose different name

### Bloom Filter Implementation

The system currently uses a bloom filter for restricted name checking:

- Pre-computed filter stored as character_name_filter.pkl
- Loaded into Lambda memory at function startup
- Provides fast O(1) checks for restricted/inappropriate names
- Prevents offensive or reserved names from being used
- Separate from uniqueness checking (handled by GSI query)

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
