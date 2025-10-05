# Eidolon Engine Character Mode Workflow

## Overview

This document describes how characters transition between Incremental and MUD game modes in the production Eidolon Engine system. The workflow assumes the shared infrastructure described in [Deployment Guide](deployment.md#system-architecture) and relies on the GameMode field to ensure characters can only be active in one mode at a time.

## Infrastructure Context

For deployment-mode specifics, refer to [Deployment Modes](deployment-modes.md); this workflow focuses solely on how characters move between modes, independent of backend stack selection.

## Workflow Steps

### 1. Account Creation

- Player creates account via Incremental UI (deployed at `portal.{domain}`)
- Cognito User Pool (`eidolon-users`) handles authentication
- `cognito-player-new` Lambda (PostConfirmation trigger) creates player record
- Player record stored in `players` DynamoDB table
- Lambda permission for Cognito trigger managed post-deployment for imported pools

### 2. Character Creation

**Lambda Function**: `api-character-add` (POST /character)

- Player provides character name and optional archetype selection
- Name format validated (length, allowed characters, etc.)
- Restricted names checked against loaded bloom filter
- Name uniqueness verified using CharacterNameIndex GSI query
- Player's character count checked against limit (from `MAX_CHARACTERS_PER_PLAYER` env var)
- Archetype data loaded from `archetypes` table (defaults used if invalid/missing)
- Starting items created from archetype's prototype list
- Character created with `GameMode: "None"` (allows player to choose initial mode)
- Character record stored in shared `characters` table
- Player's CharacterList updated with new character entry
- AvailableStories list populated from archetype configuration
- Response uses PascalCase field names matching DynamoDB schema

### 3. Character Customization (Rapid Inactive)

- Player goes through story-based tutorial
- Character gains XP and equipment
- Skills are dynamically added as used
- Progress tracked in character record

### 4. Mode Transition

Characters can transition between modes with these safeguards:

**None to Incremental:**

**Lambda Function**: `api-story-start` (POST /story/start)

- Character must have GameMode "None" (not in any active mode)
- Player selects a story from AvailableStories list
- GameMode updated to "Incremental"
- ActiveStoryID and ActiveSegmentID set
- First segment created in `active_segments` table
- For mechanical segments, message sent to `eidolon-processing-queue`
- `ops-segment-process` Lambda triggered by SQS to process segment
- SSM parameter `/eidolon/story/config` checked, EventBridge rule enabled if needed

**Incremental to None:**

**Lambda Functions**: `ops-story-advance` (SQS) or `api-story-abandon` (POST /story/abandon)

- Occurs automatically when story completes (via `ops-story-advance`)
- Can be triggered manually via abandon story API
- All ActiveSegments for character deleted
- GameMode reset to "None"
- ActiveStoryID and ActiveSegmentID cleared
- Story moved to CompletedStories or AbandonedStories list
- Records written to `story_history` and `segment_history` tables

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

Character state persists across mode transitions in the 14 DynamoDB tables (all with RemovalPolicy.RETAIN):

**Health and Wounds:**

- Health is calculated dynamically as `Health = MaxHealth - len(wounds)`
- Each wound is a map in the wounds list containing DamageType and HealAt fields
- Wounds received in either mode persist when switching:
  - Bashing wounds heal in 15 minutes (bruises, stunning)
  - Lethal wounds require 6 hours to heal (serious injuries)
  - Aggravated wounds need 7 days of recovery (grievous wounds)
- Character entering Incremental mode wounded starts at disadvantage
- Wounds heal automatically when their HealAt timestamp expires
- Character states persist across modes:
  - Standing: Normal state with health > 0
  - Unconscious: Health = 0 with at least one bashing wound
  - Dead: Health = 0 with only lethal/aggravated wounds
- Death in either mode requires resurrection before continuing

**Skill Progression:**

- All XP gained through ResolveStaticCheckWithXP/ResolveOpposedCheckWithXP persists
- Skills improved in Incremental stories benefit MUD gameplay
- Combat experience from MUD enhances Incremental mechanical segments
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

**Combat Mechanics:**

- Mechanical segments with combat use the full MUD damage system
- Each point of damage creates a wound map in the wounds list
- Damage types determine wound severity and healing time
- Unconscious characters face special damage rules:
  - New bashing damage converts to lethal
  - Lethal/aggravated damage replaces existing bashing wounds first
- Combat outcomes classified by wounds sustained:
  - Exceptional: Victory without wounds
  - Normal: Victory with 1-2 wounds
  - Minimal: Victory with 3+ wounds
  - Death: Health reduced to 0

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

**Polling System (Story Stack - Incremental/Hybrid Only):**

- EventBridge rule `eidolon-story-poller` (1-minute schedule)
- Triggers `ops-segment-poller` Lambda function
- SSM parameter `/eidolon/story/config` controls polling state
- Queries EndTimeIndex on `active_segments` table
- Sends completed segments to `eidolon-advancement-queue`
- `ops-story-advance` Lambda processes queue messages
- Automatic enable when stories start, disable when none active
- Stuck segment recovery after 15 minutes

## Healing System Integration

The wound healing system operates continuously across both game modes:

**Natural Healing:**

- Healing is automatic and requires no player intervention
- Each wound has a precise HealAt timestamp in ISO 8601 format
- System periodically checks and removes expired wounds
- Multiple wounds can heal simultaneously
- Healing continues in real-time regardless of active game mode

**Health Recalculation:**

- When wounds expire, they are removed from the wounds list
- Health automatically increases as wounds heal
- Unconscious characters regain consciousness when health > 0
- Players receive notifications when wounds heal

**Cross-Mode Implications:**

- A character wounded in MUD combat enters Incremental stories injured
- Combat wounds from Incremental persist when returning to MUD
- Strategic timing of mode switches can optimize healing downtime
- Severely wounded characters may need to wait before engaging difficult content

## Security Considerations

- GameMode field is only modifiable through authorized Lambda functions
- All Lambda functions use shared execution role: `eidolon-lambda-execution-role`
- DynamoDB access via managed policy: `eidolon-dynamodb-policy` (includes DescribeTable)
- Mode transitions require validation of game state
- API Gateway at `api.{domain}` with Cognito authorizer
- CORS validation at Lambda level using environment variables
- ProcessingStatus state transitions prevent concurrent segment processing
- Conditional updates prevent race conditions
- Fixed logical IDs prevent resource recreation on stack updates

## Performance Optimization

- Character lookups use DynamoDB's pay-per-request pricing
- GameMode checks are simple string comparisons
- Lambda functions cache archetype data at cold start
- Lambda layer contains shared `eidolon` library (updated post-deployment)
- Conditional writes prevent race conditions
- Front-loaded segment processing eliminates runtime calculations
- GSI queries (EndTimeIndex) enable efficient polling
- SQS queues (`eidolon-processing-queue`, `eidolon-advancement-queue`) batch processing
- Auto-disable polling when no active stories
- Post-deployment Lambda updates from S3 artifacts ensure latest code
- Layer version cleanup prevents accumulation

## Deployment Considerations

### Mode-Specific Stack Deployment

**MUD Mode (8 Stacks):**

- Excludes Story Stack (no SQS/EventBridge)
- Includes S3 Scripts and CloudWatch for Lua support
- Portal frontend via `buildspec/portal.yml`

**Incremental Mode (7 Stacks):**

- Includes Story Stack for segment processing
- Excludes S3 Scripts and CloudWatch stacks
- Incremental frontend via `buildspec/incremental.yml`

**Hybrid Mode (9 Stacks - Default):**

- Includes all stacks for complete functionality
- Supports both MUD and Incremental gameplay
- Incremental frontend with mode selection
