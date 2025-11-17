# Eidolon Shared Python Library

The eidolon directory contains the shared Python library used by all Lambda functions. This library provides business logic, AWS service abstractions, and utilities separated from Lambda handler concerns.

## Overview

**Module Count:** 45 Python files
**Total Lines:** ~9,640 lines
**Purpose:** Centralized business logic and AWS service wrappers
**Usage:** All 17 deployed Lambda functions import from eidolon

## Architecture Principle

Lambda functions handle AWS-specific concerns only (authentication, HTTP, CORS). All business logic resides in eidolon library functions.

**Pattern:**

```python
# lambda/api_character_get.py
from eidolon.character_data import character_get
from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler

def lambda_handler(event, context):
    # Lambda handles AWS concerns
    player_id = extract_player_id(event)  # JWT extraction
    preflight = cors_handler.handle_preflight(event)  # CORS
    if preflight:
        return preflight

    # Business logic in eidolon
    character = character_get(character_id, player_id)

    # Lambda returns HTTP response
    return lambda_response(200, {"Character": character}, event)
```

## Module Categories

### AWS Service Wrappers

**dynamo.py** - DynamoDB operations

- Centralized DynamoDB client with table name management
- CRUD operations with error handling
- Batch operations with retries
- Decimal to float conversion

**s3.py** - S3 operations

- Bucket operations
- Object upload/download

**sqs.py** - SQS message operations

- Message sending with error handling
- Batch message operations

**ssm.py** - Systems Manager Parameter Store

- Parameter read/write
- Polling state management

**cognito.py** - Cognito user operations

- JWT token extraction
- Player ID validation
- Token claims parsing

### Character Management

**character_data.py** - Character CRUD operations

- create_character() - Creates new character with starting items
- character_get() - Retrieves character with ownership validation
- get_character() - Gets character without ownership check
- apply_character_updates() - Applies segment updates (XP, wounds, room changes)

**character_segment.py** - Character-segment relationships

- update_character_active_segment() - Sets active segment ID
- character_get_active_segment() - Gets current segment

**character_story.py** - Character-story relationships

- get_active_story_and_segment() - Retrieves both with broken chain handling
- get_stories_with_character() - Gets available stories with prerequisites

### Story and Segment Processing

**story_active.py** - Active story management

- get_active_story_segment() - Gets current active segment
- mark_segment_as_abandoned() - Marks segment abandoned
- story_update_character() - Updates character with story/segment IDs

**story_completion.py** - Story completion handling

- complete_story() - Completes story and applies rewards
- complete_story_for_character() - Clears character state

**story_decision.py** - Decision segment processing

- submit_decision_for_character() - Records player decision

**story_history.py** - Story history tracking

- create_story_history_entry() - Creates StoryHistory record
- add_segment_to_history() - Adds segment to SegmentHistory array
- update_story_history_xp() - Updates XP totals

**story_retrieval.py** - Story data access

- get_story() - Gets story definition
- get_story_and_first_segment() - Gets story with first segment
- get_story_segment() - Gets segment definition

**story_rewards.py** - Reward calculation and application

- calculate_story_rewards() - Calculates rewards from story metadata
- apply_story_rewards() - Applies currency and item rewards to character
- create_reward_item() - Creates item structure for rewards
- apply_combat_rewards() - EMPTY FUNCTION (not implemented)

**story_segment.py** - Segment creation

- create_active_segment() - Creates ActiveSegment record with processing

**story_validation.py** - Story eligibility

- story_eligibility() - Checks if character can start story (now checks CharState)
- validate_story_available() - Validates story in AvailableStories
- check_story_prerequisites() - Validates skill/item requirements

### Segment Processing

**segment_core.py** - Core segment utilities

- get_active_segment() - Retrieves ActiveSegment record
- get_segment_definition() - Gets segment from Segments table
- validate_segment_outcome_results() - Validates outcome data
- is_simple_segment() - Checks if decision segment

**segment_challenges.py** - Challenge processing

- process_challenges() - Processes skill/attribute challenges
- Calculates outcomes from challenge results

**segment_combat.py** - Combat processing

- process_combat_segment() - Executes combat rounds
- get_character_best_offensive_action() - Determines attack
- get_character_defensive_action() - Determines defense
- Applies wounds to both combatants

**segment_processing.py** - Segment orchestration

- route_segment_processing() - Routes to challenge or combat processor
- process_decision_segment() - Handles decision timeouts
- determine_next_segment() - Weighted branching logic

**segment_state.py** - Segment state management

- create_next_active_segment() - Creates next segment
- update_active_segment_outcome() - Stores processing results
- mark_segment_as_completed() - Atomic status transition
- update_segment_processing_status() - Updates processing state

**segment_polling.py** - Segment polling operations

- get_segments_approaching_expiry() - Finds segments to advance
- get_stuck_mechanical_segments() - Finds segments to retry
- check_active_segments_exist() - Checks if any active
- delete_active_segment() - Removes segment record

**segment_history.py** - Segment history tracking

- record_segment_history() - Archives completed segment
- record_abandoned_segment_history() - Records abandonment

**segment_response.py** - Segment response formatting

- new_segment_response() - Formats segment data for API

### Game Mechanics

**mechanics.py** - Core game mechanics

- calculate_skill_increase() - XP calculation with exponential scaling
- calculate_heal_time() - Wound healing timestamps
- determine_character_state_from_wounds() - Standing/unconscious/dead
- apply_death_or_unconscious_outcome() - Applies character state
- resolve_opposed_check() - MUD opposed check mechanics
- resolve_opposed_check_with_xp() - Opposed check with XP tracking

**branching.py** - Weighted random branching

- evaluate_branches() - Selects branch based on weights and prerequisites

**constants.py** - Game constants

- BASE_XP, SIGMA thresholds, combat constants
- CharState enum (standing/unconscious/dead)
- Wound healing durations
- Segment polling constants

### Items and Inventory

**items.py** - Item management

- get_item_brief() - Returns ItemID + PrototypeID only
- get_item_prototype_full() - Returns complete prototype
- get_inventory() - Enriches inventory with item details
- create_item_from_prototype() - Creates item instance
- add_items_to_inventory() - Adds items to character
- create_items_from_prototypes() - Batch item creation
- process_items_with_probability() - Handles item drop chances
- merge_stacks() - Merges two stackable items, oldest wins
- find_matching_stack() - Finds existing stack for prototype
- create_coins_from_value() - Converts FU value to coin items

**archetypes.py** - Archetype management

- get_archetypes() - Returns player-available archetypes
- get_archetype() - Gets specific archetype data

### Player Management

**player.py** - Player operations

- create_player_record() - Creates player in Players table
- delete_player_data() - GDPR-compliant deletion
- get_character_list() - Gets player's characters
- validate_player() - Validates player exists
- verify_character_ownership() - Checks character ownership

**player_character.py** - Player-character relationships

- add_character_to_player_list() - Adds to CharacterList
- delete_character() - Deletes character and all data
- remove_character_from_player_list() - Removes from CharacterList

### Polling Infrastructure

**polling.py** - Polling state management

- get_polling_state() - Gets SSM parameter state
- update_polling_state() - Sets run/stop state
- manage_eventbridge_rule() - Enables/disables rule
- ensure_polling_enabled() - Ensures polling active

### Utilities

**logger.py** - Logging configuration

- Centralized logger with CloudWatch integration
- log_lambda_statistics() - Logs invocation metrics
- Structured logging with correlation IDs

**environment.py** - Environment variable management

- Validates and exposes all environment variables
- Provides defaults for missing values
- Type conversion and validation

**validation.py** - Input validation

- validate_uuid() - UUID format validation
- validate_character_name() - Name format rules

**validation_messages.py** - Error message templates

- Centralized error messages for consistency

**requests.py** - Request parsing

- parse_event_body() - Parses JSON body
- get_query_parameter() - Extracts query params

**responses.py** - Response formatting

- lambda_response() - Formats response with CORS headers
- lambda_error() - Formats error response
- create_response() - Generic response builder
- decimal_to_json_serializable() - Handles DynamoDB Decimals

**time_utils.py** - Time utilities

- now_iso() - Current time as ISO string
- from_unix() - Unix timestamp to ISO
- Unix/ISO conversion helpers

**bloom.py** - Bloom filter for obscenity checking

- character_name_filter - Checks character names against obscenity list

**state.py, state_machines.py** - State management utilities

- State transition helpers
- State machine validation

## Lambda Layer

All eidolon modules are packaged in the `eidolon-dependencies` Lambda layer:

**Deployment:**

1. CodeBuild packages eidolon/ directory
2. Creates layer zip with dependencies
3. Publishes to Lambda layer
4. All Lambda functions reference this layer

**Benefits:**

- Single source of truth for business logic
- Reduced package size per function
- Consistent behavior across functions
- Easy updates (update layer, all functions get new code)

## Known Issues

### Empty Functions

**story_rewards.py**:

**apply_story_rewards():**

- [OK] NOW fully implemented
- [OK] Creates coins from currency values
- [OK] Adds coins to inventory with proper stacking
- [OK] Updates Resources.Value field
- [OK] Fixed: Currency and story rewards properly applied

**apply_combat_rewards() (lines 72-95):**

- Function exists but does nothing
- Comment says "segment/story data must trigger distribution"
- May be intentionally empty
- **Impact:** Combat rewards not applied

### Death Check

**story_validation.py:story_eligibility() (lines 56-84):**

- [OK] Now checks both GameMode AND CharState
- [OK] Dead characters blocked from starting stories
- **Impact:** Death now has proper consequences

### Inventory Enrichment

**items.py:get_inventory() (lines 383-462):**

- Batch fetches items from Items table
- Returns enriched inventory with Name, Description, etc.
- **Potential issue:** May be returning empty if Items table doesn't have Name field
- Called by api_character_get.py but players see UUIDs

## Module Dependencies

**Core modules (no dependencies on other eidolon modules):**

- constants.py
- logger.py
- environment.py

**Infrastructure modules (depend on core):**

- dynamo.py → constants, logger, environment
- s3.py → logger
- sqs.py → logger
- ssm.py → logger

**Business logic modules (depend on infrastructure):**

- All character*\*, story*\_, segment\_\_ modules depend on dynamo, logger

## Testing

Per project policy (see unit-tests.md), eidolon library focuses on:

- Simple, inspectable code over unit tests
- Integration testing via Lambda functions
- Manual verification of business logic

## Best Practices

When adding modules to eidolon:

1. **Separation:** Keep Lambda concerns separate from business logic
2. **Error Handling:** Raise errors in library, convert to HTTP in Lambda
3. **Single Responsibility:** One module per functional area
4. **Safe Access:** Use .get() for dictionaries
5. **Type Hints:** Use basic types only (str, int, bool, dict, list)
6. **Max Size:** 300 lines preferred, 1000 maximum
7. **Naming:** snake_case for functions, PascalCase for classes

## Module Size Distribution

All modules comply with 1000-line maximum:

- Largest: items.py, character_data.py, segment_combat.py
- All under 500 lines
- 94% under 300 lines

## References

For Lambda function usage patterns, see:

- lambda-functions.md - Lambda function specifications
- python-style.md - Python coding standards
