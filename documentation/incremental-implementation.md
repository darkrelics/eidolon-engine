# Eidolon Engine Incremental Game Implementation Guide

This guide provides detailed technical information, code examples, and specific configurations for the production-deployed Incremental Game system. Based on the 9-stack CDK deployment architecture with 16 Lambda functions and 14 DynamoDB tables, this guide reflects the actual implementation deployed to AWS.

## Table of Contents

1. [Database Implementation](#1-database-implementation)
2. [Lambda Function Implementation](#2-lambda-function-implementation)
3. [Game Mechanics Implementation](#3-game-mechanics-implementation)
4. [Combat System Details](#4-combat-system-details)
5. [Processing Flow Implementation](#5-processing-flow-implementation)
6. [Client Implementation](#6-client-implementation)
7. [Infrastructure Configuration](#7-infrastructure-configuration)
8. [Error Handling Patterns](#8-error-handling-patterns)
9. [Testing Guidelines](#9-testing-guidelines)
10. [Performance Optimization](#10-performance-optimization)

## 1. Database Implementation

### 1.1 Complete Table Examples

These examples show the complete JSON structure of database records as they appear in DynamoDB. The ActiveSegments record demonstrates how all segment processing results are stored together, including pre-calculated outcomes, client events for display, and character updates to be applied when the segment completes.

#### ActiveSegments Record Example

This complete example shows how segment processing results are stored, including pre-calculated outcomes, client events for progressive display, and character updates that will be applied when the segment completes.

**Important**: ActiveSegmentID must be generated using UUIDv7 to ensure proper time-based ordering and efficient querying. In Python 3.12, use the repo's uuid helper (uuid_extension.uuid7); native uuidv7 will be adopted when upgrading to Python 3.14.

```json
{
  "ActiveSegmentID": "550e8400-e29b-41d4-a716-446655440000", // UUIDv7 format required
  "CharacterID": "7d793dc0-5e27-4a68-b40e-8f52ae06ad8e",
  "PlayerID": "a4b5c6d7-e8f9-0a1b-2c3d-4e5f6a7b8c9d",
  "StoryID": "forest-adventure-001",
  "StoryTitle": "The Whispering Woods",
  "SegmentID": "seg-forest-002a",
  "SegmentType": "mechanical",
  "DefaultStatus": "Walking through the dark forest",
  "StartTime": 1737000300,
  "EndTime": 1737003900,
  "ProcessedAt": 1737000305,
  "ProcessingStatus": "processed",
  "NextSegmentID": "seg-forest-003",
  "Outcome": "minimal",
  "ClientEvents": [
    {
      "eventType": "narrative",
      "title": "Into the Woods",
      "description": "The morning mist clings to the forest floor...",
      "data": {}
    },
    {
      "eventType": "skillCheck",
      "title": "Perception Challenge",
      "description": "You scan the forest for hidden dangers...",
      "data": {
        "skill": "perception",
        "attribute": "agility",
        "effectiveScore": 12,
        "difficulty": 8,
        "sigma": 0.82,
        "success": true,
        "skillXPAwarded": 0.25,
        "attributeXPAwarded": 0.025
      }
    }
  ],
  "CharacterUpdates": {
    "Wounds": [
      {
        "DamageType": "bashing",
        "HealAt": "2025-01-15T14:30:00Z"
      }
    ],
    "SkillXP": {
      "perception": 0.375,
      "survival": 0.75
    },
    "AttributeXP": {
      "agility": 0.0375,
      "strength": 0.075
    }
  },
  "ChallengeResults": [
    { "skill": "perception", "success": true, "sigma": 0.82 },
    { "skill": "perception", "success": false, "sigma": -0.45 }
  ]
}
```

#### Mechanical Segment Definition Example

Mechanical segments can contain both skill challenges and combat encounters. This structure shows how mechanical segments support both types of challenges, with combat configuration linking to the Opponents table and specifying different narrative results based on performance.

```json
{
  "StoryID": "forest-adventure-001",
  "SegmentID": "seg-combat-goblin-001",
  "SegmentType": "mechanical",
  "ShortStatus": "Fighting the goblin scout",
  "DefaultStatus": "Engaged in combat",
  "SegmentDuration": 120,
  "NextSegmentID": "seg-forest-004",
  "Combat": {
    "OpponentID": "a7b8c9d0-1e2f-3a4b-5c6d-7e8f9a0b1c2d",
    "maxRounds": 15,
    "environment": {
      "lighting": "dim",
      "terrain": "muddy"
    }
  },
  "Results": {
    "death": {
      "narrative": "The goblin's blade finds your heart...",
      "effects": { "room": 0 }
    },
    "failure": {
      "narrative": "Exhausted, you retreat from battle...",
      "effects": { "room": 5 }
    },
    "minimal": {
      "narrative": "You defeat the goblin but suffer grievous wounds...",
      "effects": { "room": 7, "items": ["goblin-pouch-001"] }
    },
    "normal": {
      "narrative": "Your combat training prevails...",
      "effects": { "room": 7, "items": ["goblin-pouch-001", "rusty-blade-001"] }
    },
    "exceptional": {
      "narrative": "You dispatch the goblin without a scratch!",
      "effects": {
        "room": 7,
        "items": ["goblin-pouch-001", "rusty-blade-001", "goblin-ear-001"]
      }
    }
  }
}
```

### 1.2 Index Specifications

DynamoDB Global Secondary Indexes (GSIs) enable efficient queries on non-primary key attributes. These indexes are critical for the polling system to find expired segments and for ensuring character name uniqueness across all players.

#### Global Secondary Indexes

These index definitions enable efficient queries for finding segments by character, discovering expired segments for processing, and enforcing character name uniqueness across the entire player base.

```yaml
CharacterID-index:
  PartitionKey: CharacterID
  ProjectionType: ALL
  Purpose: Query all active segments for a character

EndTimeIndex:
  PartitionKey: EndTime
  ProjectionType: ALL
  Purpose: Find segments ready for processing
  QueryPattern: EndTime <= currentTime + 15

CharacterNameIndex:
  PartitionKey: CharacterName
  ProjectionType: KEYS_ONLY
  Purpose: Ensure character name uniqueness
```

### 1.3 DynamoDB Update Examples

The story start process uses sequential operations with eventual consistency. If a failure occurs after creating the active segment but before updating the character, the ops-segment-poller will detect and clean up orphaned segments.

#### Story Start Process

The story start creates the active segment first, then updates the character state. Any orphaned segments from failures are handled by the background poller, avoiding complex rollback logic.

```python
from uuid_extension import uuid7  # Repo-provided helper for UUIDv7 IDs

def start_story(character_id, story_id, segment_data):
    # Generate UUIDv7 for the active segment
    segment_data['ActiveSegmentID'] = str(uuid7())
    
    # 1. Create active segment first
    dynamodb.put_item(
        TableName=ACTIVE_SEGMENTS_TABLE,
        Item=segment_data,
        ConditionExpression='attribute_not_exists(ActiveSegmentID)'
    )
    
    # 2. Update character state
    # If this fails, ops-segment-poller will clean up the orphaned segment
    dynamodb.update_item(
        TableName=CHARACTER_TABLE,
        Key={'CharacterID': {'S': character_id}},
        UpdateExpression='SET GameMode = :mode, ActiveStoryID = :story, ActiveSegmentID = :segment',
        ExpressionAttributeValues={
            ':mode': {'S': 'Incremental'},
            ':story': {'S': story_id},
            ':segment': {'S': segment_data['ActiveSegmentID']}
        },
        ConditionExpression='GameMode = :none OR (GameMode = :incremental AND attribute_not_exists(ActiveStoryID))',
        ExpressionAttributeValues={
            ':none': {'S': 'None'},
            ':incremental': {'S': 'Incremental'}
        }
    )
    
    # 3. Queue mechanical segments (send only ActiveSegmentID)
    if segment_data['SegmentType'] == 'mechanical':
        sqs.send_message(
            QueueUrl=SEGMENT_QUEUE_URL,
            MessageBody=segment_data['ActiveSegmentID']  # Plain string, not JSON
        )
```

## 2. Lambda Function Implementation

### 2.1 Lambda Handler Pattern

All 16 Lambda functions follow this standardized pattern with shared execution role and environment variables. Functions are deployed with fixed logical IDs to prevent recreation and are updated from S3 artifacts post-deployment.

```python
import json
import logging
from decimal import Decimal
from eidolon.logger import logger  # Uses validated LOG_LEVEL from environment
from eidolon.responses import create_response, not_found_response
from eidolon.environment import *  # Table names and configuration

def lambda_handler(event, context):
    """Standard Lambda handler pattern for all functions."""

    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})

    try:
        # Extract player ID from authorizer
        player_id = event['requestContext']['authorizer']['claims']['sub']

        # Parse request body if POST
        body = {}
        if event.get('body'):
            body = json.loads(event['body'])

        # Extract query parameters if GET
        character_id = None
        if event.get('queryStringParameters'):
            character_id = event['queryStringParameters'].get('characterId')

        # Call business logic
        result = process_story_request(
            player_id=player_id,
            character_id=character_id or body.get('CharacterID'),
            story_id=body.get('StoryID')
        )

        # Return response
        logger.info("Request completed")

        return create_response(
            result['status_code'],
            result['body']
        )

    except Exception as e:
        logger.error("Lambda error", exc_info=True)
        return create_response(500, {"error": "Internal server error"})
```

### 2.2 Common Validation Patterns

These validation functions ensure data integrity and proper authorization throughout the system. They provide reusable patterns for UUID validation, character ownership verification, and game mode checking that prevent common security issues and data corruption.

```python
def validate_uuid(value, field_name):
    """Validate UUID format."""
    import re
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    if not uuid_pattern.match(value):
        raise ValueError(f"Invalid {field_name} format")

def check_game_mode(character, required_mode="None"):
    """Verify character is in correct game mode."""
    current_mode = character.get('GameMode', 'None')
    if current_mode != required_mode:
        return create_response(409, {
            "error": f"Character is in {current_mode} mode, must be in {required_mode} mode"
        })
    return None
```

### 2.3 Segment Processing Implementation

This function handles the core segment processing logic for mechanical segments. It includes safeguards against duplicate processing, proper status tracking, and comprehensive error handling to ensure segments are processed exactly once with reliable outcome storage.

```python
def process_segment(active_segment_id):
    """Process a mechanical segment (which may contain skill challenges and/or combat)."""
    segment = get_active_segment(active_segment_id)
    if not segment:
        logger.error(f"Segment not found: {active_segment_id}")
        return {"success": False, "error": "Segment not found"}

    # Skip if already processed
    if segment.get('ProcessingStatus') == 'processed':
        logger.info(f"Segment already processed: {active_segment_id}")
        return {"success": True, "skipped": True}

    # Mark as processing
    update_processing_status(active_segment_id, 'processing')

    try:
        if segment['SegmentType'] == 'mechanical':
            result = process_mechanical_segment(segment)
        else:
            raise ValueError(f"Unknown segment type: {segment['SegmentType']}")

        # Store results
        update_segment_results(active_segment_id, result)
        update_processing_status(active_segment_id, 'processed')

        return {"success": True, "result": result}

    except Exception as e:
        logger.error(f"Segment processing failed", exc_info=True)
        update_processing_status(active_segment_id, 'failed', str(e))
        return {"success": False, "error": str(e)}
```

### 2.4 Mechanical Segment Processing

The `process_mechanical_segment` function handles both skill challenges and combat encounters within a single segment. This unified approach allows for more dynamic storytelling where challenges and combat can be interwoven based on player performance.

```python
def process_mechanical_segment(segment):
    """Process a mechanical segment containing skill challenges and/or combat."""
    segment_definition = get_segment_definition(
        segment['StoryID'],
        segment['SegmentID']
    )

    character = get_character(segment['CharacterID'])

    # Initialize results
    client_events = []
    character_updates = {
        'SkillXP': {},
        'AttributeXP': {},
        'Wounds': []
    }
    challenge_results = []

    # Process skill challenges if present
    if 'Challenges' in segment_definition:
        for challenge in segment_definition['Challenges']:
            result = resolve_skill_challenge(character, challenge)
            challenge_results.extend(result['results'])

            # Accumulate XP
            for skill, xp in result['totalSkillXP'].items():
                character_updates['SkillXP'][skill] = character_updates['SkillXP'].get(skill, 0) + xp
            for attr, xp in result['totalAttributeXP'].items():
                character_updates['AttributeXP'][attr] = character_updates['AttributeXP'].get(attr, 0) + xp

            # Create client event
            for r in result['results']:
                client_events.append({
                    'eventType': 'skillCheck',
                    'title': challenge.get('title', f"{skill.title()} Challenge"),
                    'description': challenge.get('description', ''),
                    'data': r
                })

    # Process combat if present
    if 'Combat' in segment_definition:
        combat_result = simulate_combat(character, segment_definition['Combat'])

        # Add combat events
        client_events.extend(combat_result['events'])

        # Add wounds from combat
        character_updates['Wounds'].extend(combat_result['wounds'])

        # Include combat results in outcome calculation
        challenge_results.extend(combat_result['challenge_results'])

    # Determine overall outcome based on all challenges
    outcome = calculate_mechanical_outcome(challenge_results)

    # Apply narrative and effects from outcome
    outcome_def = segment_definition['Results'][outcome]

    # Add narrative event
    client_events.insert(0, {
        'eventType': 'narrative',
        'title': segment_definition.get('Title', 'Story Progress'),
        'description': outcome_def['narrative']
    })

    # Apply outcome effects
    if 'room' in outcome_def.get('effects', {}):
        character_updates['Room'] = outcome_def['effects']['room']

    return {
        'Outcome': outcome,
        'ClientEvents': client_events,
        'CharacterUpdates': character_updates,
        'ChallengeResults': challenge_results,
        'NextSegmentID': segment_definition.get('NextSegmentID')
    }
```

## 3. Game Mechanics Implementation

### 3.1 Skill Check Implementation

The skill challenge system integrates with the MUD mechanics to provide consistent difficulty scaling and XP awards. This implementation handles multiple attempts per challenge, accumulates XP across all attempts, and returns detailed results for client display and character progression.

```python
def resolve_skill_challenge(character, challenge_def):
    """Execute a skill challenge using MUD mechanics."""
    skill = challenge_def['skill']
    attribute = challenge_def['attribute']
    difficulty = challenge_def['difficulty']
    attempts = challenge_def.get('attempts', 1)

    results = []
    total_skill_xp = 0
    total_attribute_xp = 0

    for attempt in range(attempts):
        # Calculate effective score
        skill_value = character.get('Skills', {}).get(skill, 0)
        attribute_value = character.get('Attributes', {}).get(attribute, 0)
        effective_score = skill_value + attribute_value

        # Call MUD mechanics
        success, sigma, skill_xp, attribute_xp = ResolveStaticCheckWithXP(
            character, skill, attribute, difficulty
        )

        results.append({
            "attempt": attempt + 1,
            "skill": skill,
            "attribute": attribute,
            "effectiveScore": effective_score,
            "difficulty": difficulty,
            "sigma": round(sigma, 2),
            "success": success,
            "skillXPAwarded": skill_xp,
            "attributeXPAwarded": attribute_xp
        })

        total_skill_xp += skill_xp
        total_attribute_xp += attribute_xp

    return {
        "results": results,
        "totalSkillXP": {skill: total_skill_xp},
        "totalAttributeXP": {attribute: total_attribute_xp}
    }
```

### 3.2 Outcome Calculation

This algorithm determines the final outcome of a mechanical segment by analyzing all challenge results (both skill checks and combat). It uses statistical measures (sigma values) from the MUD mechanics to create a fair outcome distribution, with special handling for catastrophic failures and critical successes that can override average performance.

```python
def calculate_mechanical_outcome(challenge_results):
    """Determine mechanical segment outcome based on all challenge results (skill checks and combat)."""
    if not challenge_results:
        return "normal"

    # Extract sigma values
    sigmas = []
    for challenge in challenge_results:
        for result in challenge.get('results', []):
            sigmas.append(result['sigma'])

    if not sigmas:
        return "normal"

    # Check for catastrophic failure
    if any(sigma <= -3.0 for sigma in sigmas):
        return "death"

    # Calculate average performance
    avg_sigma = sum(sigmas) / len(sigmas)

    # Check for critical overrides
    critical_failures = sum(1 for s in sigmas if s < -2.0)
    critical_successes = sum(1 for s in sigmas if s > 2.0)

    # Determine outcome
    if avg_sigma < -2.0 or critical_failures >= 2:
        return "death"
    elif avg_sigma < -0.5:
        return "failure"
    elif avg_sigma < 0.5:
        return "minimal"
    elif avg_sigma < 1.5:
        return "normal"
    else:
        return "exceptional"
```

### 3.3 XP Application

Character updates are applied atomically using DynamoDB update expressions. This function builds dynamic update statements based on the specific changes needed, handling XP additions, wound applications, and room changes in a single database operation for consistency and performance. These updates are accumulated from both skill challenges and combat encounters within mechanical segments.

**Important XP Multiplier Constraint**: The BaseXPMultiplier field in story metadata must default to 0.5 and must never equal or exceed 1.0. This ensures incremental gameplay provides experience at a slower rate than active MUD play, maintaining game balance between the two modes.

```python
def apply_character_updates(character_id, updates):
    """Apply accumulated XP and other updates to character."""
    update_expressions = []
    expression_values = {}

    # Skills XP
    if updates.get('SkillXP'):
        for skill, xp in updates['SkillXP'].items():
            update_expressions.append(f"Skills.{skill} = Skills.{skill} + :xp_{skill}")
            expression_values[f":xp_{skill}"] = Decimal(str(xp))

    # Attributes XP
    if updates.get('AttributeXP'):
        for attr, xp in updates['AttributeXP'].items():
            update_expressions.append(f"Attributes.{attr} = Attributes.{attr} + :xp_{attr}")
            expression_values[f":xp_{attr}"] = Decimal(str(xp))

    # Wounds
    if updates.get('Wounds'):
        update_expressions.append("Wounds = list_append(Wounds, :new_wounds)")
        expression_values[":new_wounds"] = updates['Wounds']

    # Room change
    if updates.get('Room'):
        update_expressions.append("RoomID = :room")
        expression_values[":room"] = updates['Room']

    # Execute update
    if update_expressions:
        dynamodb.update_item(
            TableName=CHARACTER_TABLE,
            Key={'CharacterID': {'S': character_id}},
            UpdateExpression=f"SET {', '.join(update_expressions)}",
            ExpressionAttributeValues=expression_values
        )
```

## 4. Combat System Details

**Note:** Combat is now handled within mechanical segments, which can contain both skill challenges and combat encounters. The combat system described here is integrated into the mechanical segment processing flow.

### 4.1 Combat Round Processing

Combat simulation executes round-by-round using the MUD's opposed check mechanics. Each round includes attack resolution, damage calculation if successful, and wound application. Environmental factors like dim lighting or difficult terrain apply realistic modifiers to create tactical depth in encounters.

```python
def simulate_combat_round(attacker, defender, round_num, environment):
    """Simulate one round of combat."""
    # Apply environmental modifiers
    attack_modifier = 0
    defense_modifier = 0

    if environment.get('lighting') == 'dim':
        attack_modifier -= 1
    if environment.get('terrain') == 'muddy':
        defense_modifier -= 1

    # Attack roll
    hit_result = ResolveOpposedCheckWithXP(
        attacker, defender,
        "melee", "strength",  # Attacker skills
        "dodge", "agility"    # Defender skills
    )

    round_event = {
        "round": round_num,
        "attackRoll": {
            "attacker": attacker['Name'],
            "sigma": round(hit_result['sigma'], 2),
            "hit": hit_result['success']
        }
    }

    if hit_result['success']:
        # Damage roll - note this uses ResolveOpposedCheck (no XP)
        damage_result = ResolveOpposedCheck(
            attacker, defender,
            "melee", "strength",
            "toughness", "endurance"
        )

        # Calculate wounds
        damage = max(0, int(damage_result['sigma']))
        if damage > 0:
            wounds = []
            weapon_type = attacker.get('WeaponType', 'bashing')

            for _ in range(damage):
                heal_time = calculate_heal_time(weapon_type)
                wounds.append({
                    "DamageType": weapon_type,
                    "HealAt": heal_time
                })

            round_event['damage'] = {
                "amount": damage,
                "type": weapon_type,
                "wounds": wounds
            }

    return round_event

def calculate_heal_time(damage_type):
    """Calculate when a wound will heal."""
    from datetime import datetime, timedelta

    heal_times = {
        'bashing': timedelta(minutes=15),
        'lethal': timedelta(hours=6),
        'aggravated': timedelta(days=7)
    }

    heal_delta = heal_times.get(damage_type, timedelta(hours=6))
    heal_at = datetime.utcnow() + heal_delta
    return heal_at.isoformat() + 'Z'
```

### 4.2 Combat Outcome Determination

The combat outcome function evaluates the final state of battle, considering character health, opponent defeat, and round limits to determine whether the player achieved an exceptional victory, normal success, minimal success, failure, or death.

```python
def determine_combat_outcome(character_wounds, opponent_health, rounds_fought, max_rounds):
    """Determine combat outcome based on final state."""
    # Character death check
    character_health = character['MaxHealth'] - len(character_wounds)
    if character_health <= 0:
        return "death"

    # Victory conditions
    if opponent_health <= 0:
        # Check wounds for victory quality
        wound_count = len(character_wounds)
        if wound_count == 0:
            return "exceptional"
        elif wound_count <= 2:
            return "normal"
        else:
            return "minimal"

    # Timeout failure
    if rounds_fought >= max_rounds:
        return "failure"

    # Should not reach here
    logger.error("Combat ended without clear outcome")
    return "failure"
```

### 4.3 Special Damage Rules

This implementation handles the special damage conversion rules when characters are unconscious, automatically converting bashing damage to lethal and replacing existing bashing wounds with more severe damage types when appropriate.

```python
def apply_unconscious_damage(character, new_damage_type):
    """Handle damage to unconscious characters."""
    wounds = character.get('Wounds', [])

    # Count wound types
    bashing_indices = []
    for i, wound in enumerate(wounds):
        if wound['DamageType'] == 'bashing':
            bashing_indices.append(i)

    # New bashing damage to unconscious converts to lethal
    if new_damage_type == 'bashing':
        new_damage_type = 'lethal'

    # Lethal/aggravated replaces existing bashing first
    if new_damage_type in ['lethal', 'aggravated'] and bashing_indices:
        # Replace oldest bashing wound
        index_to_replace = bashing_indices[0]
        wounds[index_to_replace] = {
            'DamageType': new_damage_type,
            'HealAt': calculate_heal_time(new_damage_type)
        }
        return wounds

    # Otherwise add new wound
    wounds.append({
        'DamageType': new_damage_type,
        'HealAt': calculate_heal_time(new_damage_type)
    })
    return wounds
```

### 4.4 Rest Segments and Healing Mechanics

Rest segments provide pacing in stories and allow characters time to recover. However, healing checks are not limited to rest segments - they occur at the start of EVERY segment.

#### Healing Process

When any new segment is created (mechanical, decision, or rest), the system automatically:

2. Checks if the character is dead - dead characters do not heal
3. Removes wounds that have passed their `HealAt` timestamp (for living characters)
4. Updates the character's Wounds array
5. Logs the healing results

#### Rest Segment Implementation

Rest segments themselves are simple time delays with no challenges or decisions:

#### Segment Definition Example

A rest segment in the Segments table:

```json
{
  "StoryID": "forest-adventure-001",
  "SegmentID": "seg-rest-001",
  "SegmentType": "rest",
  "ShortStatus": "Resting at the campfire",
  "DefaultStatus": "You rest by the warm campfire, tending to your wounds",
  "SegmentDuration": 600, // 10 minutes
  "RestSegment": true,
  "NextSegmentID": "seg-forest-003"
}
```

#### Key Points

- **Healing at story start**: Wounds are also healed when starting a new story (in `start_story()`)
- **Healing on character retrieval**: The `api_get_character` endpoint heals expired wounds before returning character data
- **Dead characters don't heal**: Characters with `CharState` of "dead" skip healing entirely
- **Rest segments are passive**: They provide narrative pacing but have no active mechanics
- **Healing is time-based**: Wounds heal based on their `HealAt` timestamp, not segment type
- **Non-blocking**: Healing failures don't prevent segment creation or character retrieval
- **Consistent outcome**: Rest segments always result in "normal" outcome

This design ensures characters naturally recover over time regardless of segment type, while rest segments provide narrative breathing room in the story flow.

## 5. Processing Flow Implementation

### 5.1 Polling System Implementation

The EventBridge-triggered polling function discovers segments ready for processing and manages the polling state through SSM parameters, automatically starting and stopping based on active segment presence to optimize costs.

```python
def segment_poller_handler(event, context):
    """EventBridge-triggered polling function (runs every minute)."""
    # Check SSM parameter
    ssm = boto3.client('ssm')
    param = ssm.get_parameter(Name='/eidolon/segment-poller-state')
    state = param['Parameter']['Value']

    current_time = int(time.time())
    next_poll_buffer = 90  # 60 seconds to next poll + 30 second buffer

    # Phase 1: Find ALL segments approaching expiry (within 90 seconds)
    # These need advancement (if processed) or recovery (if not processed)
    expiring_segments = get_segments_approaching_expiry(current_time + next_poll_buffer)
    
    advancement_messages = []
    segments_marked_exceptional = 0
    
    for segment in expiring_segments:
        active_segment_id = segment['ActiveSegmentID']
        processing_status = segment.get('ProcessingStatus', 'pending')
        
        if processing_status == 'processed':
            # Normal advancement - segment completed processing
            advancement_messages.append({'body': active_segment_id})
        else:
            # Not processed in time - mark exceptional to protect player
            mark_segment_as_completed_exceptional(active_segment_id)
            advancement_messages.append({'body': active_segment_id})
            segments_marked_exceptional += 1

    # Phase 2: Find stuck mechanical segments with time to retry
    # Criteria: StartTime > 5 minutes ago, EndTime > 90 seconds from now, 
    # ProcessingStatus in (pending, processing), SegmentType = mechanical
    stuck_segments = get_stuck_mechanical_segments(current_time)
    
    processing_messages = []
    for segment in stuck_segments:
        active_segment_id = segment['ActiveSegmentID']
        processing_status = segment.get('ProcessingStatus', 'pending')
        
        # Reset if stuck in processing
        if processing_status == 'processing':
            reset_segment_processing_status(active_segment_id)
        
        processing_messages.append({'body': active_segment_id})

    # Send messages to appropriate queues
    if advancement_messages:
        send_message_batch(STORY_ADVANCEMENT_QUEUE_URL, advancement_messages)
    
    if processing_messages:
        send_message_batch(SEGMENT_QUEUE_URL, processing_messages)

    # Manage polling state transitions
    if state == 'run':
        # Check if there are still active segments
        if not check_active_segments_exist():
            update_polling_state('stop', enable_rule=False)
    else:  # state == 'stop'
        # Check for active segments
        if check_active_segments_exist():
            update_polling_state('run', enable_rule=True)

    return {'statusCode': 200}

def get_segments_approaching_expiry(threshold_time):
    """Get ALL segments that will expire before next poll (90 seconds).
    
    These segments need advancement (if processed) or recovery (if not processed).
    NO ProcessingStatus filter - we need to handle all expiring segments.
    """
    response = dynamodb.query(
        TableName=ACTIVE_SEGMENTS_TABLE,
        IndexName='EndTimeIndex',
        KeyConditionExpression='#status = :status AND EndTime < :threshold',
        ExpressionAttributeNames={'#status': 'Status'},
        ExpressionAttributeValues={
            ':status': {'S': 'active'},
            ':threshold': {'N': str(threshold_time)}
        }
        # NO FilterExpression - get ALL segments approaching expiry
    )
    return response.get('Items', [])

def get_stuck_mechanical_segments(current_time):
    """Get mechanical segments stuck in pending/processing with time to retry.
    
    Criteria:
    - StartTime > 5 minutes ago (stuck threshold)
    - EndTime > 90 seconds from now (enough time to process)
    - ProcessingStatus in (pending, processing)
    - SegmentType = mechanical
    """
    five_minutes_ago = current_time - 300
    ninety_seconds_future = current_time + 90
    
    # Use scan since we need to filter on StartTime which isn't indexed
    response = dynamodb.scan(
        TableName=ACTIVE_SEGMENTS_TABLE,
        FilterExpression='#status = :status AND '
                        'SegmentType = :mechanical AND '
                        'StartTime < :old_time AND '
                        'EndTime > :min_time AND '
                        'ProcessingStatus IN (:pending, :processing)',
        ExpressionAttributeNames={'#status': 'Status'},
        ExpressionAttributeValues={
            ':status': {'S': 'active'},
            ':mechanical': {'S': 'mechanical'},
            ':old_time': {'N': str(five_minutes_ago)},
            ':min_time': {'N': str(ninety_seconds_future)},
            ':pending': {'S': 'pending'},
            ':processing': {'S': 'processing'}
        }
    )
    return response.get('Items', [])
```

### 5.2 SQS Message Processing

The system uses two SQS queues with different processing patterns:

1. **Segment Processing Queue**: Handles mechanical segments that require immediate processing when created
2. **Story Advancement Queue**: Handles all segments when their timers expire, processing simple segments and advancing stories

Both handlers use atomic claiming to prevent duplicate processing, returning failed messages to the queue for retry while tracking successful completions.

```python
def advance_story_handler(event, context):
    """Process segments from SQS queue."""
    successful = []
    failed = []

    for record in event['Records']:
        try:
            # Parse message - now just the ActiveSegmentID as a plain string
            active_segment_id = record['body'].strip()

            # Claim segment
            if not claim_segment_for_processing(active_segment_id):
                logger.warning(f"Could not claim segment: {active_segment_id}")
                failed.append(record['receiptHandle'])
                continue

            # Process segment
            process_segment_completion(active_segment_id)
            successful.append(record['receiptHandle'])

        except Exception as e:
            logger.error(f"Failed to process segment", exc_info=True)
            failed.append(record['receiptHandle'])

    # Return failed messages to queue
    if failed:
        return {
            'batchItemFailures': [
                {'itemIdentifier': receipt} for receipt in failed
            ]
        }

    return {'statusCode': 200}

def claim_segment_for_processing(active_segment_id):
    """Atomically claim a segment for processing using ProcessingStatus state transition."""
    try:
        dynamodb.update_item(
            TableName=ACTIVE_SEGMENTS_TABLE,
            Key={'ActiveSegmentID': {'S': active_segment_id}},
            UpdateExpression='SET ProcessingStatus = :processing',
            ExpressionAttributeValues={
                ':processing': {'S': 'processing'},
                ':pending': {'S': 'pending'}
            },
            ConditionExpression='attribute_exists(ActiveSegmentID) AND ProcessingStatus = :pending'
        )
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return False
        raise
```

## 6. Client Implementation

### 6.1 Server-Authoritative Design

The Flutter client follows a server-authoritative design where all state determination happens on the server. The client maintains a simple polling loop and displays what the server provides without making any state decisions.

#### Key Principles

1. **Server Authority**: The server determines all state transitions. Clients never modify story state.
2. **Simple Polling**: Fixed cadence polling rather than dynamic intervals.
3. **Display-Only History**: Local segment history is maintained purely for UI display.
4. **Completion Detection**: Story completion is detected by checking `activeSegmentID == null`.

### 6.2 Polling Implementation

```dart
class GameScreen extends StatefulWidget {
  // ... widget code
}

class _GameScreenState extends State<GameScreen> {
  Character? _character;
  bool _isPolling = false;
  
  // Segment history for UI display only
  final List<Map<String, dynamic>> _segmentHistory = [];
  
  /// Simple polling loop following the server cadence
  Future<void> _runStoryPolling() async {
    if (_character?.activeSegmentID == null) {
      _isPolling = false;
      return;
    }
    
    debugPrint('Starting story polling loop');
    
    // Wait 60 seconds for initial processing
    await Future.delayed(const Duration(seconds: 60));
    
    while (_isPolling && _character?.activeSegmentID != null) {
      try {
        // Get segment status
        final status = await retryWithBackoff(
          () => _apiService.getSegmentStatus(
            characterId: _character!.id,
          ),
        );
        
        // Add to display history if processed
        if (status['ProcessingStatus'] == 'processed') {
          _addSegmentToHistory(status);
        }
        
        // Wait for segment to complete
        final timeRemaining = status['TimeRemaining'] as int? ?? 0;
        if (timeRemaining > 0) {
          await Future.delayed(Duration(seconds: timeRemaining));
        }
        
        // Get updated character
        await _loadCharacterData();
        
        // If story continues, wait for next segment processing
        if (_character?.activeSegmentID != null) {
          await Future.delayed(const Duration(seconds: 60));
        }
      } catch (e) {
        debugPrint('Error in polling loop: $e');
        // Continue polling after a delay
        await Future.delayed(const Duration(seconds: 5));
      }
    }
    
    debugPrint('Story polling loop ended');
    _isPolling = false;
  }
  
  /// Retry helper with exponential backoff
  Future<T> retryWithBackoff<T>(Future<T> Function() operation) async {
    for (int i = 0; i < 3; i++) {
      try {
        return await operation();
      } catch (e) {
        if (i == 2) rethrow;
        await Future.delayed(Duration(seconds: math.pow(2, i).toInt()));
      }
    }
    throw Exception('Unreachable');
  }
}
```

### 6.3 Progressive Event Display

This widget progressively reveals story events over the segment duration, creating an engaging narrative experience by timing event display to match the segment's progress rather than showing all events immediately.

```dart
class StoryEventDisplay extends StatefulWidget {
  final List<ClientEvent> events;
  final Duration segmentDuration;

  @override
  _StoryEventDisplayState createState() => _StoryEventDisplayState();
}

class _StoryEventDisplayState extends State<StoryEventDisplay> {
  int _currentEventIndex = 0;
  Timer? _eventTimer;

  @override
  void initState() {
    super.initState();
    _scheduleEventDisplay();
  }

  void _scheduleEventDisplay() {
    if (widget.events.isEmpty) return;

    // Calculate time per event
    final eventCount = widget.events.length;
    final msPerEvent = widget.segmentDuration.inMilliseconds ~/ eventCount;

    _eventTimer = Timer.periodic(
      Duration(milliseconds: msPerEvent),
      (timer) {
        setState(() {
          _currentEventIndex++;
        });

        if (_currentEventIndex >= eventCount) {
          timer.cancel();
        }
      }
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: _currentEventIndex + 1,
      itemBuilder: (context, index) {
        return EventCard(event: widget.events[index]);
      },
    );
  }
}
```

### 6.4 Character Model Updates

The Flutter Character model now includes direct properties for story state, eliminating the need for complex state determination logic:

```dart
class Character {
  final String id;
  final String name;
  final String? activeStoryID;    // Currently active story ID
  final String? activeSegmentID;  // Currently active segment ID
  Map<String, dynamic>? storyState; // Detailed segment data for display
  // ... other fields
  
  /// Story completion is determined by server state
  bool get hasActiveStory => activeStoryID != null;
  bool get isStoryComplete => activeStoryID != null && activeSegmentID == null;
  
  factory Character.fromJson(Map<String, dynamic> json) {
    return Character(
      id: json['CharacterID'],
      name: json['CharacterName'],
      activeStoryID: json['ActiveStoryID'] as String?,
      activeSegmentID: json['ActiveSegmentID'] as String?,
      storyState: json['StoryState'] as Map<String, dynamic>?,
      // ... parse other fields
    );
  }
}
```

**Key Changes:**
- Added `activeStoryID` and `activeSegmentID` as direct properties
- Story completion detected via `activeSegmentID == null`
- Server provides these IDs directly in character response
- Client never modifies these values

## 7. Infrastructure Configuration

### 7.1 Production CDK Configuration

The Story Stack (deployed only in Incremental/Hybrid modes) provides SQS queues, EventBridge rule, and SSM parameter. This is part of the 9-stack deployment system.

```python
# From app_story.py - actual production configuration
from aws_cdk import Stack, Duration
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_ssm as ssm
from constructs import Construct

class StoryStack(Stack):
    def __init__(self, scope: Construct, stack_id: str, **kwargs):
        super().__init__(scope, stack_id, **kwargs)

        # SQS Queue for segment processing
        self.processing_queue = sqs.Queue(
            self, "ProcessingQueue",
            queue_name="eidolon-processing-queue",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14)
        )

        # SQS Queue for story advancement
        self.advancement_queue = sqs.Queue(
            self, "AdvancementQueue",
            queue_name="eidolon-advancement-queue",
            visibility_timeout=Duration.seconds(180),
            retention_period=Duration.days(14)
        )

        # SSM Parameter for configuration
        self.config_param = ssm.StringParameter(
            self, "ConfigParameter",
            parameter_name="/eidolon/story/config",
            string_value=json.dumps({"polling_enabled": False}),
            description="Story processing configuration"
        )

        # EventBridge rule (disabled by default)
        self.polling_rule = events.Rule(
            self, "PollingRule",
            rule_name="eidolon-story-poller",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            enabled=False
        )

        # Note: Lambda functions are deployed via Lambda Stack
        # This stack only provides the infrastructure they use

        # Outputs for Lambda Stack
        CfnOutput(self, "ProcessingQueueUrl",
                  value=self.processing_queue.queue_url)
        CfnOutput(self, "AdvancementQueueUrl",
                  value=self.advancement_queue.queue_url)
        CfnOutput(self, "ConfigParameterName",
                  value=self.config_param.parameter_name)
```

### 7.2 Production Environment Variables

From lambda_stack.py, all Lambda functions receive these standardized environment variables:

```python
# Common environment variables for all Lambda functions
env_vars = {
    "APPLICATION_NAME": "eidolon-engine",
    "LOG_LEVEL": "INFO",  # Validated by eidolon/environment.py
    "ALLOWED_ORIGINS": f"https://{client_host}.{domain}",
    "CORS_ALLOW_CREDENTIALS": "true",
    "CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,...",
    "CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS",
    "CORS_MAX_AGE": "86400",

    # DynamoDB table names from stack outputs
    "players_table": "players",
    "characters_table": "characters",
    "archetypes_table": "archetypes",
    "items_table": "items",
    "prototypes_table": "prototypes",
    "story_table": "story",
    "segments_table": "segments",
    "active_segments_table": "active_segments",
    "story_history_table": "story_history",
    "segment_history_table": "segment_history",
    "opponents_table": "opponents",
    "rooms_table": "rooms",
    "exits_table": "exits",
    "motd_table": "motd"
}

# Function-specific additions
if function_name == "ops-segment-process":
    env["SEGMENT_BATCH_SIZE"] = "10"
    env["SEGMENT_QUEUE_URL"] = "https://sqs.{region}.amazonaws.com/{account}/eidolon-processing-queue"

if function_name == "ops-segment-poller":
    env["POLLING_INTERVAL"] = "60"
    env["SSM_POLLER_STATE_PARAMETER"] = "/eidolon/story/config"
    env["STORY_ADVANCEMENT_QUEUE_URL"] = "https://sqs.{region}.amazonaws.com/{account}/eidolon-advancement-queue"
```

## 8. Error Handling Patterns

### 8.1 Lambda Error Handling

The error handling framework provides typed exceptions with appropriate HTTP status codes and a decorator pattern that ensures consistent error responses across all Lambda functions while maintaining detailed logging for debugging.

```python
class IncrementalError(Exception):
    """Base exception for incremental game errors."""
    def __init__(self, message, status_code=500, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}

class ValidationError(IncrementalError):
    """Invalid request data."""
    def __init__(self, message, field=None):
        super().__init__(message, 400, {'field': field})

class NotFoundError(IncrementalError):
    """Resource not found."""
    def __init__(self, resource_type):
        super().__init__(f"{resource_type} not found", 404)

class ConflictError(IncrementalError):
    """Resource state conflict."""
    def __init__(self, message):
        super().__init__(message, 409)

def handle_errors(func):
    """Decorator for consistent error handling."""
    def wrapper(event, context):
        try:
            return func(event, context)
        except IncrementalError as e:
            logger.warning(f"Business error: {err}")
            return create_response(e.status_code, {
                "error": str(e),
                **e.details
            })
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                return not_found_response("Resource")
            elif error_code == 'ConditionalCheckFailedException':
                return create_response(409, {"error": "Conflict detected"})
            else:
                logger.error("AWS error", exc_info=True)
                return create_response(500, {"error": "Internal server error"})
        except Exception as e:
            logger.error("Unexpected error", exc_info=True)
            return create_response(500, {"error": "Internal server error"})
    return wrapper
```

### 8.2 Retry Logic

This exponential backoff implementation handles transient failures in AWS service calls, automatically retrying with increasing delays to improve reliability without overwhelming the system during temporary outages.

```python
def retry_with_backoff(func, max_attempts=3, base_delay=1):
    """Retry function with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise

            delay = base_delay * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s", exc_info=True)
            time.sleep(delay)

# Usage example
def update_with_retry(table_name, key, update_expression, expression_values):
    def update():
        return dynamodb.update_item(
            TableName=table_name,
            Key=key,
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

    return retry_with_backoff(update)
```

## 9. Testing Guidelines

### 9.1 Unit Test Patterns

These unit test patterns demonstrate how to mock DynamoDB operations and validate complex business logic like prerequisite checking and transaction structure, ensuring code correctness without requiring actual AWS resources.

```python
import pytest
from unittest.mock import Mock, patch
from decimal import Decimal

class TestStoryProcessing:
    @pytest.fixture
    def mock_character(self):
        return {
            'CharacterID': 'test-char-001',
            'PlayerID': 'test-player-001',
            'GameMode': 'None',
            'Skills': {'perception': Decimal('5'), 'survival': Decimal('3')},
            'Attributes': {'agility': Decimal('3'), 'strength': Decimal('4')},
            'MaxHealth': 10,
            'Wounds': []
        }

    @pytest.fixture
    def mock_story(self):
        return {
            'StoryID': 'test-story-001',
            'Title': 'Test Adventure',
            'FirstSegmentID': 'seg-001',
            'Prerequisites': {
                'minSkills': {'survival': 2},
                'requiredItems': []
            }
        }

    def test_validate_prerequisites(self, mock_character, mock_story):
        """Test story prerequisite validation."""
        # Character meets requirements
        assert validate_prerequisites(mock_character, mock_story['Prerequisites']) == True

        # Character lacks skill
        mock_story['Prerequisites']['minSkills']['combat'] = 10
        assert validate_prerequisites(mock_character, mock_story['Prerequisites']) == False

    @patch('boto3.client')
    def test_start_story_transaction(self, mock_boto, mock_character):
        """Test atomic story start."""
        mock_dynamodb = Mock()
        mock_boto.return_value = mock_dynamodb

        # Execute transaction
        start_story('test-char-001', 'test-story-001')

        # Verify transaction structure
        mock_dynamodb.transact_write_items.assert_called_once()
        transaction = mock_dynamodb.transact_write_items.call_args[0][0]

        assert len(transaction['TransactItems']) == 2
        assert 'Update' in transaction['TransactItems'][0]
        assert 'Put' in transaction['TransactItems'][1]
```

### 9.2 Integration Test Patterns

Integration tests validate the complete polling workflow by creating segments in various states and verifying that the poller correctly identifies and processes ready and stuck segments according to business rules.

```python
class TestSegmentPolling:
    @pytest.fixture
    def setup_test_segments(self, dynamodb_table):
        """Create test segments with various states."""
        current_time = int(time.time())

        segments = [
            {
                'ActiveSegmentID': 'ready-001',
                'EndTime': current_time - 60,  # Past due
                'ProcessingStatus': 'processed'
            },
            {
                'ActiveSegmentID': 'stuck-001',
                'EndTime': current_time + 600,  # Still has 10 min to go
                'ProcessingStatus': 'processing',  # Stuck in processing
                'StartTime': current_time - 400  # Started >5 min ago (stuck threshold)
            },
            {
                'ActiveSegmentID': 'future-001',
                'EndTime': current_time + 3600,  # 1 hour future
                'ProcessingStatus': 'pending'
            }
        ]

        for segment in segments:
            dynamodb_table.put_item(Item=segment)

        return segments

    def test_polling_discovers_segments(self, setup_test_segments):
        """Test poller finds ready and stuck segments."""
        event = {}  # EventBridge event
        context = Mock()

        result = segment_poller_handler(event, context)

        assert result['processed'] == 2  # ready + stuck
        assert result['statusCode'] == 200
```

### 9.3 Load Testing

The Locust load testing script simulates realistic user behavior patterns including authentication, story browsing, and story starts, helping identify performance bottlenecks and validate system scalability under concurrent load.

```python
# locust_test.py
from locust import HttpUser, task, between
import random
import uuid

class IncrementalUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Login and select character."""
        # Login flow
        response = self.client.post("/auth/login", json={
            "email": f"test{random.randint(1,1000)}@example.com",
            "password": "TestPassword123!"
        })
        self.token = response.json()['token']
        self.headers = {'Authorization': f'Bearer {self.token}'}

        # Get characters
        response = self.client.get("/characters", headers=self.headers)
        characters = response.json()['Characters']
        self.character_id = characters[0]['CharacterID']

    @task(3)
    def view_stories(self):
        """Check available stories."""
        self.client.get(
            f"/stories?characterId={self.character_id}",
            headers=self.headers
        )

    @task(1)
    def start_story(self):
        """Start a random story."""
        # Get available stories
        response = self.client.get(
            f"/stories?characterId={self.character_id}",
            headers=self.headers
        )
        stories = response.json()['Stories']

        if stories:
            story = random.choice(stories)
            self.client.post("/stories/start",
                json={
                    "CharacterID": self.character_id,
                    "StoryID": story['StoryID']
                },
                headers=self.headers
            )
```

## 10. Performance Optimization

### 10.1 DynamoDB Optimization

These optimization techniques reduce DynamoDB costs and improve performance through batch operations, projection expressions to minimize data transfer, and query limits that prevent excessive reads while maintaining application responsiveness.

```python
# Batch operations for efficiency
def batch_write_segments(segments):
    """Write multiple segments in batches."""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(ACTIVE_SEGMENTS_TABLE)

    with table.batch_writer() as batch:
        for segment in segments:
            batch.put_item(Item=segment)

# Projection expressions to reduce data transfer
def get_character_minimal(character_id):
    """Fetch only required character fields."""
    response = dynamodb.get_item(
        TableName=CHARACTER_TABLE,
        Key={'CharacterID': {'S': character_id}},
        ProjectionExpression='CharacterID, PlayerID, GameMode, ActiveStoryID, MaxHealth, Wounds'
    )
    return response.get('Item')

# Query optimization with limits
def query_active_segments_limited(character_id, limit=10):
    """Query with result limit."""
    response = dynamodb.query(
        TableName=ACTIVE_SEGMENTS_TABLE,
        IndexName='CharacterID-index',
        KeyConditionExpression='CharacterID = :char_id',
        ExpressionAttributeValues={
            ':char_id': {'S': character_id}
        },
        Limit=limit,
        ScanIndexForward=False  # Most recent first
    )
    return response.get('Items', [])
```

### 10.2 Lambda Optimization

Lambda performance optimizations include global client initialization for connection reuse, in-memory caching of frequently accessed data, and periodic warming to minimize cold start latency for better user experience.

```python
# Global initialization for connection reuse
dynamodb = boto3.client('dynamodb')
ssm = boto3.client('ssm')

# Cache frequently accessed data
story_cache = {}
CACHE_TTL = 300  # 5 minutes

def get_story_cached(story_id):
    """Get story with caching."""
    cache_key = f"story:{story_id}"
    cached = story_cache.get(cache_key)

    if cached and cached['expires'] > time.time():
        return cached['data']

    # Fetch from database
    story = get_story_from_db(story_id)

    # Update cache
    story_cache[cache_key] = {
        'data': story,
        'expires': time.time() + CACHE_TTL
    }

    return story

# Minimize cold starts
def warm_lambda_handler(event, context):
    """Periodic warming to prevent cold starts."""
    if event.get('source') == 'aws.events' and event.get('warmer'):
        return {'statusCode': 200, 'body': 'Lambda warmed'}

    # Regular processing
    return lambda_handler(event, context)
```

### 10.3 Cost Monitoring

Cost tracking implementation emits CloudWatch metrics for every DynamoDB operation, enabling detailed cost analysis and optimization opportunities by identifying high-frequency operations and potential architectural improvements.

```python
def emit_cost_metrics(operation, item_count=1):
    """Emit CloudWatch metrics for cost tracking."""
    cloudwatch = boto3.client('cloudwatch')

    cloudwatch.put_metric_data(
        Namespace='eidolon/incremental/costs',
        MetricData=[
            {
                'MetricName': 'DynamoDBOperations',
                'Dimensions': [
                    {
                        'Name': 'Operation',
                        'Value': operation
                    }
                ],
                'Value': item_count,
                'Unit': 'Count'
            }
        ]
    )

# Usage in code
def update_character_with_metrics(character_id, updates):
    """Update character and track costs."""
    result = dynamodb.update_item(
        TableName=CHARACTER_TABLE,
        Key={'CharacterID': {'S': character_id}},
        UpdateExpression=updates['expression'],
        ExpressionAttributeValues=updates['values']
    )

    # Track the operation
    emit_cost_metrics('UpdateItem', 1)

    return result
```

## Production Deployment Status

### Deployment Metrics

- **9 CDK Stacks**: All operational in production
- **16 Lambda Functions**: Deployed with fixed logical IDs
- **14 DynamoDB Tables**: Created with RemovalPolicy.RETAIN
- **2 SQS Queues**: Processing and advancement queues (Story Stack)
- **1 EventBridge Rule**: 1-minute polling (disabled by default)
- **Module Size**: 94% under 300 lines (modular architecture)
- **Deployment Time**: Full deployment in under 15 minutes

### Key Implementation Details

- **Fixed Logical IDs**: Prevent resource recreation on updates
- **Post-Deployment Updates**: Lambda functions updated from S3
- **Shared Execution Role**: `eidolon-lambda-execution-role`
- **Managed DynamoDB Policy**: Includes DescribeTable permission
- **CORS at Lambda Level**: Configured via environment variables
- **Automated Portal Build**: Via CodeBuild with `buildspec/incremental.yml`

### Stack Dependencies

1. **CodeBuild Stack**: Provides Lambda artifacts
2. **DynamoDB Stack**: Tables and managed policy
3. **Lambda Stack**: Functions and execution role
4. **Player Stack**: Cognito authentication
5. **Story Stack**: SQS, EventBridge, SSM (Incremental/Hybrid only)
6. **API Stack**: API Gateway with Lambda integrations
7. **Client Stack**: CloudFront and portal deployment

## Conclusion

This implementation guide reflects the production-deployed Incremental Game system as part of the Eidolon Engine's 9-stack CDK architecture. All code examples and configurations match the actual deployed infrastructure, providing a reliable reference for maintenance and enhancement.
