# Eidolon Engine Incremental Game Technical Design Document

## 1. Executive Summary

This document provides the technical design specifications for implementing the Incremental Game component of the Eidolon Engine. It details the system architecture, data flows, API specifications, and integration patterns required to deliver a timer-based story progression system that seamlessly integrates with the existing MUD infrastructure using a simplified serverless approach.

## 2. System Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Flutter Web    │────▶│   API Gateway    │────▶│ Lambda Functions│
│  Portal (Shared)│     │   (Existing)     │     │  (Dual-Purpose) │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                    ┌──────────────────────────────────────┼──────┐
                    │                                      │      │
              ┌─────▼─────┐                        ┌──────▼──────┤
              │ DynamoDB  │                        │ EventBridge │
              │ (Shared)  │                        │  (Timers)   │
              └───────────┘                        └─────────────┘
```

### 2.2 Component Interactions

The Incremental Game system operates as an alternative gameplay mode to the MUD, leveraging the existing infrastructure:

1. **Shared Data Layer**: All existing DynamoDB tables used by both modes
2. **Mode Exclusivity**: GameMode field prevents concurrent access
3. **Timing Service**: EventBridge rules for segment scheduling at 1-second resolution
4. **Stateless Compute**: Lambda functions handle all game logic
5. **Unified Portal**: Single Flutter web app serves both game modes

## 3. Data Architecture

### 3.1 DynamoDB Table Designs

#### 3.1.1 Story Table (Existing, Extended)

```python
# Uses existing story table with PlayerID/StoryID composite key
{
    "PlayerID": "player-uuid-123",      # PK
    "StoryID": "forest-adventure#2024", # SK (includes timestamp for history)
    "Status": "active",                 # active|completed|abandoned
    "CurrentSegment": "seg-002",
    "SegmentStartTime": 1737000300,
    "NextCompletionTime": 1737003600,
    "Decisions": {
        "seg-001": {
            "choice": "take-left-path",
            "timestamp": 1737000250,
            "automated": false
        }
    },
    "Outcomes": [
        {
            "segmentId": "seg-002",
            "result": "normal-success",
            "timestamp": 1737000900,
            "effects": {
                "experience": 50,
                "items": ["herb_bundle"]
            }
        }
    ],
    "StartTime": 1737000000,
    "CompletionTime": null,
    "TTL": 1737086400  # Auto-cleanup after 24 hours for active stories
}
```

#### 3.1.2 Stories Definition Table (New)

```python
# Simple table for story definitions
{
    "StoryID": "forest-adventure",      # PK
    "StoryType": "daily",               # one-time|daily|repeatable
    "Title": "The Whispering Woods",
    "Description": "A mysterious force draws you into the ancient forest...",
    "EstimatedDuration": 3600,          # seconds
    "Prerequisites": {
        "minSkills": {
            "survival": 10,
            "combat": 5
        },
        "requiredItems": ["map_fragment"],
        "requiredRooms": ["town_square"]
    },
    "Segments": [
        {
            "segmentId": "seg-001",
            "type": "decision",
            "content": "You stand at the forest edge. The path splits...",
            "imageUrl": "s3://scripts-bucket/images/forest_edge.jpg",
            "duration": 300,  # 5 minutes
            "options": [
                {
                    "id": "take-left-path",
                    "text": "Take the moonlit path",
                    "skillChecks": ["perception", "nature"]
                },
                {
                    "id": "follow-markers",
                    "text": "Follow the ancient markers",
                    "skillChecks": ["history", "navigation"]
                }
            ],
            "defaultDecisionLogic": "highest_skill"
        },
        {
            "segmentId": "seg-002",
            "type": "narrative",
            "duration": 600,  # 10 minutes
            "content": {
                "base": "You venture deeper into the woods...",
                "outcomes": {
                    "death": {
                        "text": "The forest claims another victim...",
                        "effects": {"health": 0, "room": "death_realm"}
                    },
                    "failure": {
                        "text": "You stumble through brambles...",
                        "effects": {"health": -20, "experience": 10}
                    },
                    "minimal": {
                        "text": "You make slow progress...",
                        "effects": {"health": -5, "experience": 25}
                    },
                    "normal": {
                        "text": "You navigate successfully...",
                        "effects": {"experience": 50, "items": ["herb_bundle"]}
                    },
                    "exceptional": {
                        "text": "Your expertise shines through...",
                        "effects": {"experience": 100, "items": ["rare_herb"], "gold": 50}
                    }
                }
            }
        }
    ],
    "Version": 1,
    "Created": "2025-01-15T10:00:00Z"
}
```

#### 3.1.3 Character Table (Existing Fields Utilized)

```python
# No schema changes needed, using existing fields
{
    "CharacterID": "char-uuid-456",     # PK
    "PlayerID": "player-uuid-123",      # Existing attribute
    "GameMode": "Incremental",          # Existing field (MUD|Incremental|None)
    "AvailableStories": [               # New field to add
        "forest-adventure",
        "daily-patrol",
        "tutorial"
    ],
    # All other existing MUD fields remain unchanged...
}
```

### 3.2 Data Access Patterns

#### 3.2.1 Primary Access Patterns

1. **Get Available Stories**: Read character's AvailableStories list
2. **Check Story Participation**: Query story table by PlayerID + StoryID
3. **Get Active Story**: Query story table for Status="active"
4. **Update Segment Progress**: Transactional update to story record
5. **Mode Transition**: Update character GameMode field

#### 3.2.2 No GSIs Required

The simplified architecture avoids Global Secondary Indexes by:

- Using direct key lookups where possible
- Accepting slightly less efficient queries for admin operations
- Leveraging existing table structures

## 4. API Design

### 4.1 RESTful Endpoints

All endpoints follow existing Lambda patterns and extend the current API Gateway.

#### 4.1.1 Story Management APIs

**GET /stories**

```python
# Lambda: api_get_stories
Purpose: Retrieve available stories for character
Query Parameters: characterId
Response: {
    "stories": [
        {
            "storyId": "forest-adventure",
            "title": "The Whispering Woods",
            "type": "daily",
            "available": true,
            "cooldownRemaining": 0,
            "estimatedDuration": 3600
        }
    ]
}
```

**POST /stories/start**

```python
# Lambda: api_start_story
Purpose: Begin a new story
Request: {
    "characterId": "char-uuid-456",
    "storyId": "forest-adventure"
}
Response: {
    "segment": {
        "segmentId": "seg-001",
        "type": "decision",
        "content": "You stand at the forest edge...",
        "options": [...],
        "timeRemaining": 300
    }
}
Error Cases:
- 409: Character already in story or MUD mode
- 403: Story not available
```

**GET /stories/current**

```python
# Lambda: api_get_current_story
Purpose: Get active story state
Query Parameters: characterId
Response: Current story and segment details
```

#### 4.1.2 Segment APIs

**POST /segments/decision**

```python
# Lambda: api_submit_decision
Purpose: Submit player decision
Request: {
    "characterId": "char-uuid-456",
    "decision": "take-left-path"
}
Response: {
    "accepted": true,
    "nextSegmentTime": 1737003600
}
```

**GET /segments/outcome**

```python
# Lambda: api_get_segment_outcome
Purpose: Retrieve completed segment results
Query Parameters: characterId, segmentId
Response: {
    "outcome": "normal",
    "narrative": "You navigate successfully...",
    "effects": {
        "experience": 50,
        "items": ["herb_bundle"]
    }
}
```

**POST /stories/abandon**

```python
# Lambda: api_abandon_story
Purpose: Exit current story
Request: { "characterId": "char-uuid-456" }
Response: { "abandoned": true }
```

### 4.2 Client Communication Strategy

The Flutter portal implements smart polling:

1. **Active Story Polling**

   - Poll `/stories/current` based on segment duration
   - Start frequent polling 30 seconds before completion
   - Use exponential backoff: 30s → 15s → 5s → 1s

2. **Decision Windows**

   - Check every 30 seconds during decision segments
   - Immediate update after decision submission

3. **Idle Optimization**
   - No polling when no active story
   - Check for new stories on screen focus

## 5. Lambda Function Specifications

### 5.1 Core Lambda Functions

All Lambda functions follow the existing pattern in the `lambda/` directory and use the `eidolon` package for standardized responses, logging, and error handling.

#### 5.1.1 api_get_stories

```python
"""Get available stories for a character."""
# Key Operations:
- Fetch character record to get AvailableStories list
- Load story definitions from cache or DynamoDB
- Check participation history for cooldowns
- Filter by prerequisites
- Return formatted list using eidolon.responses
```

#### 5.1.2 api_start_story

```python
"""Initialize story participation."""
# Key Operations:
- Verify character GameMode is "None"
- Set GameMode to "Incremental" (atomic update)
- Create story participation record
- Schedule first segment completion via EventBridge
- Return first segment details
# Error Handling:
- Use eidolon.responses.error_response for conflicts
- Log with eidolon.logger
```

#### 5.1.3 api_submit_decision

```python
"""Record player decision and schedule next segment."""
# Key Operations:
- Validate decision against current segment options
- Update story record with decision
- Calculate next segment timing
- Create/update EventBridge rule for completion
- Return acknowledgment
```

#### 5.1.4 api_process_segment

```python
"""Process segment completion (triggered by EventBridge)."""
# Key Operations:
- Retrieve story and character data
- Calculate outcome based on character stats/skills
- Apply effects to character record
- Update story progression
- Schedule next segment or complete story
# Note: This runs automatically, not called by client
```

### 5.2 EventBridge Timer Implementation

Instead of a Fargate container, use EventBridge for timing:

```python
def schedule_segment_completion(player_id, story_id, segment_id, completion_time):
    """Create one-time EventBridge rule for segment completion."""
    rule_name = f"segment-{player_id}-{segment_id}"

    eventbridge.put_rule(
        Name=rule_name,
        ScheduleExpression=f"at({completion_time.isoformat()})",
        State='ENABLED'
    )

    # Target the segment processor Lambda
    eventbridge.put_targets(
        Rule=rule_name,
        Targets=[{
            'Id': '1',
            'Arn': segment_processor_lambda_arn,
            'Input': json.dumps({
                'playerId': player_id,
                'storyId': story_id,
                'segmentId': segment_id
            })
        }]
    )
```

### 5.3 Outcome Calculation Logic

The segment processor implements MUD-compatible mechanics:

```python
def calculate_narrative_outcome(character, segment, decision=None):
    """Determine narrative outcome based on character stats."""
    # Aggregate relevant skills
    skill_total = sum(character.get('skills', {}).get(skill, 0)
                     for skill in segment.get('relevantSkills', []))

    # Apply equipment modifiers
    equipment_bonus = calculate_equipment_bonus(character, segment)

    # Calculate success probability (same as MUD combat)
    success_chance = (skill_total + equipment_bonus) / 100.0

    # Roll for outcome
    roll = random.random()

    if roll < 0.05:  # 5% critical failure
        return 'death'
    elif roll < 0.20:  # 15% failure
        return 'failure'
    elif roll < 0.50:  # 30% minimal success
        return 'minimal'
    elif roll < 0.90:  # 40% normal success
        return 'normal'
    else:  # 10% exceptional success
        return 'exceptional'
```

## 6. Flutter Portal Integration

### 6.1 New Screens

Add to existing portal structure:

```dart
// portal/lib/screens/incremental/
story_selection_screen.dart    // List available stories
story_display_screen.dart      // Show current segment
equipment_screen.dart          // Manage equipment (reuse existing)
```

### 6.2 State Management

Extend existing providers:

```dart
// portal/lib/providers/incremental_state.dart
class IncrementalState extends ChangeNotifier {
  Story? activeStory;
  Segment? currentSegment;
  Timer? pollingTimer;
  DateTime? segmentCompleteTime;

  // Reuse existing ApiService for all calls
  final ApiService _api;

  Future<void> startStory(String storyId) async {
    final response = await _api.post('/stories/start', {
      'characterId': currentCharacter.id,
      'storyId': storyId
    });
    // Update state and start polling
  }
}
```

### 6.3 Navigation Integration

Update character management screen:

```dart
// Add button to enter incremental mode
if (character.gameMode == 'None') {
  ElevatedButton(
    onPressed: () => Navigator.pushNamed(
      context,
      '/incremental/stories'
    ),
    child: Text('Play Story Mode'),
  );
} else if (character.gameMode == 'Incremental') {
  ElevatedButton(
    onPressed: () => Navigator.pushNamed(
      context,
      '/incremental/current'
    ),
    child: Text('Continue Story'),
  );
}
```

## 7. Security and Validation

### 7.1 Mode Exclusivity

Enforce through GameMode field:

```python
def validate_mode_transition(character, target_mode):
    """Ensure character can transition to target mode."""
    current_mode = character.get('GameMode', 'None')

    if current_mode == target_mode:
        return True

    if current_mode == 'MUD':
        raise ValueError("Character active in MUD")

    if current_mode == 'Incremental':
        raise ValueError("Character in story mode")

    # Check for expired locks (1 hour timeout)
    last_transition = character.get('LastModeTransition', 0)
    if time.time() - last_transition < 3600:
        return True

    return True
```

### 7.2 Input Validation

Use existing eidolon validation patterns:

```python
from eidolon.validation_utils import validate_uuid, validate_string

def validate_story_request(event):
    """Validate story API request."""
    character_id = event.get('characterId')
    if not validate_uuid(character_id):
        return error_response("Invalid character ID")

    story_id = event.get('storyId')
    if not validate_string(story_id, max_length=50):
        return error_response("Invalid story ID")
```

## 8. Monitoring and Analytics

### 8.1 CloudWatch Metrics

Emit custom metrics using existing patterns:

```python
from eidolon.logger import get_logger
logger = get_logger(__name__)

# Log story events
logger.info("Story started", extra={
    "story_id": story_id,
    "character_id": character_id,
    "story_type": story_type
})

# Track completion rates
cloudwatch.put_metric_data(
    Namespace='eidolon/incremental',
    MetricData=[{
        'MetricName': 'StoryCompletion',
        'Value': 1,
        'Dimensions': [
            {'Name': 'StoryId', 'Value': story_id},
            {'Name': 'Outcome', 'Value': outcome}
        ]
    }]
)
```

### 8.2 Error Tracking

Leverage existing error patterns:

```python
try:
    # Story logic
except ValidationError as e:
    logger.warning("Validation failed", extra={"error": str(e)})
    return validation_error_response(e.field, e.message)
except Exception as e:
    logger.error("Story processing failed", extra={"error": str(e)}, exc_info=True)
    return internal_error_response(context.aws_request_id)
```

## 9. Deployment Strategy

### 9.1 CDK Integration

Add new Lambda functions to existing stack:

```python
# deployment/cdk/stacks/lambda_stack.py
# Add to existing Lambda definitions:

self.story_functions = [
    ("api-get-stories", "api_get_stories.lambda_handler"),
    ("api-start-story", "api_start_story.lambda_handler"),
    ("api-submit-decision", "api_submit_decision.lambda_handler"),
    ("api-get-segment-outcome", "api_get_segment_outcome.lambda_handler"),
    ("api-abandon-story", "api_abandon_story.lambda_handler"),
    ("process-segment", "process_segment.lambda_handler"),
]

# Add EventBridge rule for segment processor
self.segment_processor_rule = events.Rule(
    self, "segment-processor-rule",
    schedule=events.Schedule.rate(Duration.seconds(1))
)
```

### 9.2 API Gateway Routes

Extend existing API:

```python
# Add to API Gateway configuration
story_routes = [
    ("GET", "/stories", "api-get-stories"),
    ("POST", "/stories/start", "api-start-story"),
    ("GET", "/stories/current", "api-get-current-story"),
    ("POST", "/segments/decision", "api-submit-decision"),
    ("GET", "/segments/outcome", "api-get-segment-outcome"),
    ("POST", "/stories/abandon", "api-abandon-story"),
]
```

### 9.3 Database Updates

Add story definition table to DynamoDB stack:

```python
# deployment/cdk/stacks/dynamodb_stack.py
# Add to table configurations:
{"name": "story_definitions", "pk": "StoryID", "pk_type": "S"}
```

## 10. Cost Analysis

### 10.1 Simplified Cost Structure

With the serverless approach:

**Monthly Costs (10,000 concurrent users)**:

- Lambda invocations: ~$50-100
- EventBridge rules: ~$10-20
- DynamoDB (pay-per-request): ~$100-200
- No Fargate costs: $0
- **Total: ~$160-320/month**

### 10.2 Cost Optimization

1. **Lambda Optimization**:

   - Minimize cold starts by keeping functions warm
   - Use appropriate memory allocation (256MB typical)

2. **EventBridge Efficiency**:

   - Clean up completed rules promptly
   - Batch similar timings when possible

3. **DynamoDB Efficiency**:
   - Use TTL for automatic cleanup
   - Minimize unnecessary reads

## 11. Implementation Timeline

### 11.1 Phase 1: Core Story System (Week 1-2)

- Create story definition table
- Implement core Lambda functions
- Basic EventBridge timer logic
- Manual story creation tools

### 11.2 Phase 2: Flutter Integration (Week 3-4)

- Story selection screen
- Story display/decision UI
- Polling implementation
- Error handling

### 11.3 Phase 3: Game Mechanics (Week 5-6)

- Skill check calculations
- Equipment integration
- Progression balancing
- Daily story reset logic

### 11.4 Phase 4: Polish & Testing (Week 7-8)

- Performance optimization
- Comprehensive testing
- Analytics implementation
- Documentation

## 12. Benefits of Simplified Architecture

### 12.1 Development Benefits

- No new infrastructure patterns to learn
- Reuse existing Lambda/API patterns
- Consistent error handling via eidolon
- Single deployment pipeline

### 12.2 Operational Benefits

- No container management
- Automatic scaling with Lambda
- Pay-per-use pricing
- Unified monitoring

### 12.3 Maintenance Benefits

- Fewer moving parts
- Standard AWS services only
- No custom timing service to maintain
- Simple debugging with CloudWatch

## 13. Conclusion

This simplified technical design leverages the existing Eidolon Engine infrastructure to implement the incremental game with minimal additional complexity. By using shared tables, dual-purpose Lambda functions, and EventBridge for timing, the system can support 10,000 concurrent users while maintaining consistency with the MUD game mechanics and keeping operational costs low.

Key architectural decisions:

- Shared DynamoDB tables eliminate synchronization needs
- EventBridge replaces complex Fargate timing service
- Existing Lambda patterns ensure consistency
- GameMode field provides simple mode exclusivity
- 1-second resolution aligns with MUD ticker
