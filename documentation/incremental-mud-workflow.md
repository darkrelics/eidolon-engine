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
- Character created with `GameMode: "None"` (allows player to choose initial mode)
- Character record stored in shared characters table
- Player's CharacterList updated with new character entry
- AvailableStories list populated from archetype configuration

### 3. Character Customization (Rapid Inactive)

- Player goes through story-based tutorial
- Character gains XP and equipment
- Skills are dynamically added as used
- Progress tracked in character record

### 4. Mode Transition

Characters can transition between modes with these safeguards:

**None to Incremental:**

- Character must have GameMode "None" (not in any active mode)
- Player selects a story from AvailableStories list
- GameMode updated to "Incremental"
- ActiveStoryID and ActiveSegmentID set
- First segment created and processed immediately
- SSM parameter checked, polling enabled if needed

**Incremental to None:**

- Occurs automatically when story completes (success or failure)
- Can be triggered manually via abandon story API
- All ActiveSegments for character deleted
- GameMode reset to "None"
- ActiveStoryID and ActiveSegmentID cleared
- Story moved to CompletedStories or AbandonedStories list

**None to MUD:**

- Character must have GameMode "None"
- GameMode updated to "MUD"
- Character placed in appropriate room
- Full MUD gameplay becomes available

**MUD to None:**

- Character must be logged out of MUD
- GameMode updated to "None"
- Character position preserved for return
- Character ready to start new Incremental story or re-enter MUD

### 5. Persistent State Between Modes

Character state persists across mode transitions, creating meaningful consequences:

**Health and Wounds:**
- Wounds received in either mode persist when switching
- Bashing wounds heal in 15 minutes regardless of mode
- Lethal wounds require 6 hours to heal
- Aggravated wounds need 7 days of recovery
- Character entering Incremental mode wounded starts at disadvantage
- Death in either mode requires resurrection before continuing

**Skill Progression:**
- All XP gained through ResolveStaticCheckWithXP/ResolveOpposedCheckWithXP persists
- Skills improved in Incremental stories benefit MUD gameplay
- Combat experience from MUD enhances Incremental combat segments
- Attribute XP (10% of skill XP) accumulates across both modes

**Inventory and Equipment:**
- Items gained in Incremental stories appear in MUD inventory
- Equipment worn affects combat stats in both modes
- Lost or destroyed items affect both game modes
- Currency (gold, resources) shared between modes

**Location:**
- Story outcomes can change character's room location
- Death may transport character to death realm
- Location changes persist when switching to MUD mode

### 6. Concurrent Access Prevention

- Lambda functions check GameMode before any character operation
- Attempts to use character in wrong mode are rejected
- Clear error messages guide players to switch modes properly
- Timestamp tracking allows timeout recovery for stuck states

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

## Story State Management

The Incremental mode maintains sophisticated state tracking:

**Active Story Tracking:**
- ActiveStoryID and ActiveSegmentID on character record
- ActiveSegments table holds runtime segment state
- Front-loaded processing calculates all outcomes at segment start
- ClientEvents array contains complete narrative sequence

**Story Progression Lists:**
- AvailableStories: Stories the character can start
- CompletedStories: Successfully finished stories
- AbandonedStories: Stories started but not completed
- Story types (one-time, daily, repeatable) control re-availability

**Polling System:**
- 30-second EventBridge polling for segment completion
- SSM parameter `/eidolon/segment-poller-state` controls polling
- Automatic enable when stories start, disable when none active
- Stuck segment recovery after 15 minutes

## Security Considerations

- GameMode field is only modifiable through authorized Lambda functions
- Mode transitions require validation of game state
- IAM roles restrict direct database access
- API Gateway authentication required for all operations
- RunningFlag prevents concurrent segment processing
- Conditional updates prevent race conditions

## Performance Optimization

- Character lookups use DynamoDB's consistent performance
- GameMode checks are simple string comparisons
- Lambda functions cache archetype data
- Conditional writes prevent race conditions
- Front-loaded segment processing eliminates runtime calculations
- GSI queries (EndTimeIndex) enable efficient polling
- SQS batching reduces API calls
- Auto-disable polling when no active stories
