# Incremental Game Technical Design

## 1. Architecture Overview

### 1.1 System Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Flutter Web    │────▶│   API Gateway    │────▶│ Lambda Functions│
│     Client      │     │   (Existing)     │     │  (Python 3.12)  │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                    ┌──────────────────────────────────────┼────────────┐
                    │                                      │            │
              ┌─────▼─────┐                        ┌──────▼──────┐     │
              │ DynamoDB  │                        │ EventBridge │     │
              │ (Shared)  │                        │  (30 sec)   │     │
              └───────────┘                        └──────┬──────┘     │
                                                          │            │
                                                   ┌──────▼──────┐     │
                                                   │  SQS Queue  │─────┘
                                                   │  (Segment)  │
                                                   └─────────────┘
                                                   ┌─────────────┐
                                                   │  SQS Queue  │─────┘
                                                   │   (Story)   │
                                                   └─────────────┘
```

### 1.2 Processing Architecture

The system uses a front-loaded processing model where all outcomes are calculated when segments start:

1. **Segment Creation**: When a story starts or advances, outcomes are immediately calculated
2. **Timer Management**: Segments have start/end times for client countdown display
3. **Polling System**: EventBridge triggers every 30 seconds to find completed segments
4. **Dual Queue Processing**: 
   - Segment Processing Queue: Mechanical segments processed immediately when created
   - Story Advancement Queue: All segments processed when timer expires
5. **Result Application**: Pre-calculated outcomes applied and story advanced

## 2. API Design

### 2.1 RESTful Endpoints

All endpoints extend the existing API Gateway configuration. Field names use PascalCase to match DynamoDB schemas.

| Method | Endpoint | Lambda Function | Purpose |
|--------|----------|-----------------|---------|
| GET | /stories | api_get_stories | List available stories for character |
| POST | /stories/start | api_start_story | Begin a new story |
| GET | /stories/current | api_get_current_story | Get active story state |
| POST | /stories/abandon | api_abandon_story | Exit current story |
| POST | /segments/decision | api_submit_decision | Submit player choice |
| GET | /segments/status | api_get_segment_status | Check segment readiness |
| GET | /segments/history | api_get_segment_history | Retrieve processed results |

### 2.2 Request/Response Examples

The API uses JSON for all request and response payloads. When a player initiates a story, the client sends the character ID and desired story ID to the backend. The server validates prerequisites, ensures the character is not already in a game mode, and creates the first segment. The response includes timing information that allows the client to display an accurate countdown timer and the segment's status text for immediate display.

**Start Story Request:**
```json
POST /stories/start
{
    "CharacterID": "char-uuid-456",
    "StoryID": "forest-adventure-uuid"
}
```

**Start Story Response:**
```json
{
    "success": true,
    "segment": {
        "activeSegmentId": "active-seg-uuid-123",
        "segmentType": "decision",
        "startTime": 1737000000,
        "endTime": 1737000300,
        "shortStatus": "Choosing your path",
        "duration": 300
    }
}
```

## 3. Lambda Function Specifications

### 3.1 Lambda Architecture Pattern

The Lambda architecture enforces a strict separation of concerns to improve testability and maintainability. Every Lambda function in the incremental system follows a two-layer pattern: the handler layer manages AWS-specific concerns like authentication extraction and CORS headers, while the business logic layer contains pure Python functions that can be tested without AWS dependencies. This pattern allows developers to unit test business logic in isolation and ensures that infrastructure changes don't affect core game mechanics. The handler always logs the invocation details for debugging and returns standardized responses using the eidolon library's response formatters.

Each Lambda follows a consistent pattern:

```python
def lambda_handler(event: dict, context: object) -> dict:
    """AWS Lambda entry point - handles infrastructure concerns."""
    # 1. Log invocation with request details
    # 2. Handle CORS preflight if needed
    # 3. Extract and validate authentication
    # 4. Parse and validate request
    # 5. Call business logic function
    # 6. Return formatted response with CORS headers

def business_logic(param1: str, param2: str) -> dict:
    """Pure business logic - testable without AWS dependencies."""
    # Uses eidolon library functions
    # Returns success/error dictionary
```

### 3.2 Core Lambda Functions

**api_start_story**
- Validates character ownership and GameMode="None"
- Creates ActiveSegments record with calculated end time
- Generates ActiveSegmentID using UUIDv7 for time-based ordering
- Immediately calls ops_process_segment for non-decision segments
- Uses DynamoDB transaction to ensure atomicity
- Enables polling if not already active

**ops_segment_poller** (EventBridge triggered)
- Reads SSM parameter for run/stop state
- Queries EndTimeIndex for segments where EndTime <= Now
- Sends ALL completed segments to Story Advancement Queue
- Manages polling state (auto-disable when no segments)

**ops_process_segment** (SQS triggered)
- Processes mechanical segments only
- Uses MUD mechanics for calculations:
  - ResolveStaticCheckWithXP for skill challenges
  - ResolveOpposedCheckWithXP for combat encounters
- Generates ClientEvents array for display
- Stores results in ActiveSegments record

**ops_advance_story** (SQS triggered from Story Advancement Queue)
- Claims segment with RunningFlag to prevent duplicates
- Processes simple segments (rest/decision) if not already processed
- Applies CharacterUpdates (XP, wounds, room changes)
- Creates next segment if story continues
- Resets GameMode="None" if story ends
- Writes to StoryHistory and SegmentHistory tables

## 4. Database Design

See [schema.md](schema.md) for complete table definitions. Key design patterns:

### 4.1 Table Usage

- **Story/Segments**: Immutable content definitions
- **ActiveSegments**: Runtime instances with pre-calculated results
- **Character**: Extended with story lists and mode tracking
- **StoryHistory/SegmentHistory**: Audit trail and analytics

### 4.2 Global Secondary Indexes

- **CharacterID-index** on ActiveSegments: Query by character
- **EndTimeIndex** on ActiveSegments: Find ready segments
- **CharacterNameIndex** on Character: Name uniqueness

### 4.3 Transaction Patterns

Use DynamoDB transactions for critical operations:
- Story start (Character + ActiveSegments)
- Story completion (Character + History + Cleanup)

Avoid transactions for high-frequency operations:
- Segment processing (use idempotent design)
- XP updates (use conditional writes)

## 5. Processing Flows

### 5.1 Story Start Flow

```
1. Client: POST /stories/start
2. Lambda: Validate prerequisites and GameMode
3. Lambda: Transaction {
     - Update Character (GameMode, ActiveStoryID)
     - Create ActiveSegments record
   }
4. Lambda: If not decision segment:
     - Call ops_process_segment immediately
5. Lambda: Check/enable polling system
6. Lambda: Return segment details to client
```

### 5.2 Segment Processing Flow

```
1. EventBridge: Trigger ops_segment_poller every 30 seconds
2. Poller: Query EndTimeIndex for expired segments
3. Poller: Send ALL segments to Story Advancement Queue
4. SQS: Trigger ops_advance_story for each message
5. Advance: Process simple segments if needed (rest/decision)
6. Advance: Apply CharacterUpdates
7. Advance: Create next segment or complete story
8. Advance: Record history and delete completed segment
```

### 5.3 Mechanical Segment Flow

```
1. Determine segment content (challenges and/or combat)
2. For skill challenges:
   - Execute ResolveStaticCheckWithXP for each attempt
   - Accumulate results and XP
3. For combat encounters:
   - Load opponent from Opponents table
   - Simulate rounds using ResolveOpposedCheckWithXP
   - Track wounds and determine victory/defeat
4. Generate ClientEvents array with all results
5. Calculate final outcome based on performance
```

## 6. Game Mechanics Integration

### 6.1 Skill Checks

All skill checks use MUD mechanics functions:

```python
# Narrative challenges
result = ResolveStaticCheckWithXP(
    character, 
    skill="perception",
    attribute="agility", 
    difficulty=8
)
# Returns: (success, sigma, skill_xp, attribute_xp)

# Combat actions  
result = ResolveOpposedCheckWithXP(
    attacker, defender,
    "melee", "strength",  # Attacker
    "dodge", "agility"    # Defender
)
```

### 6.2 Outcome Calculation

Mechanical segment outcomes combine all challenge and combat results:

For skill challenges (based on average sigma):
- Death: Any sigma ≤ -3.0 or average < -2.0
- Failure: Average -2.0 to -0.5
- Minimal: Average -0.5 to 0.5
- Normal: Average 0.5 to 1.5
- Exceptional: Average > 1.5

For combat encounters (based on wounds):
- Death: Health reaches 0
- Failure: Max rounds without victory
- Minimal: Victory with 3+ wounds
- Normal: Victory with 1-2 wounds
- Exceptional: Victory without wounds

When both exist in a segment, the worse outcome takes precedence.

### 6.3 Wound System

Full MUD wound implementation:
- Each damage point creates wound map: {DamageType, HealAt}
- Damage types: bashing (15min), lethal (6hr), aggravated (7d)
- Health = MaxHealth - len(wounds)
- Wounds persist across game modes

## 7. Client Integration

### 7.1 Flutter Architecture

The Flutter client integrates into the existing portal application as a separate module for incremental gameplay. The architecture follows Flutter best practices with screens handling UI presentation, services managing API communication, models defining data structures, and providers coordinating state management. This modular approach allows the incremental game to share authentication, character selection, and common UI components with the MUD client while maintaining its own distinct gameplay screens. The incremental module can be enabled or disabled through feature flags without affecting the core portal functionality.

```
portal/lib/
├── screens/incremental/
│   ├── story_selection_screen.dart
│   ├── active_story_screen.dart
│   └── story_history_screen.dart
├── services/
│   └── incremental_service.dart
├── models/incremental/
│   ├── story.dart
│   ├── segment.dart
│   └── active_segment.dart
└── providers/
    └── incremental_provider.dart
```

### 7.2 State Management

Using Provider pattern:
- IncrementalProvider manages active story state
- Polling based on segment end time
- Local countdown calculation
- Automatic state refresh on completion

### 7.3 Polling Strategy

The client implements an intelligent polling strategy that balances server load with user experience. During most of a segment's duration, the client polls every 30 seconds to check for early completion or status updates. As the segment approaches its scheduled end time, the polling frequency increases progressively: at 5 minutes remaining it polls every 10 seconds, and in the final 30 seconds it polls every second. This graduated approach ensures players see immediate updates when segments complete while minimizing unnecessary API calls during the waiting period. The polling system also handles edge cases like network disconnections by resuming from the last known state.

```dart
// Start aggressive polling 30 seconds before completion
if (timeRemaining <= 30) {
    pollInterval = Duration(seconds: 1);
} else if (timeRemaining <= 300) {
    pollInterval = Duration(seconds: 10);  
} else {
    pollInterval = Duration(seconds: 30);
}
```

## 8. Infrastructure

### 8.1 AWS Services

- **Lambda**: Python 3.12 runtime with eidolon library
- **DynamoDB**: Pay-per-request pricing
- **EventBridge**: Single rule, 30-second schedule
- **SQS**: Two standard queues:
  - Segment Processing Queue: For immediate mechanical segment processing
  - Story Advancement Queue: For all segment advancement when timers expire
- **SSM Parameter**: /eidolon/segment-poller-state
- **CloudWatch**: Logs and metrics

### 8.2 Cost Optimization

For 10,000 concurrent users:
- Lambda: ~$80-120/month (reduced by 67% with 30-sec polling)
- DynamoDB: ~$150-200/month (efficient GSI usage)
- EventBridge: <$1/month (single rule)
- SQS: ~$5-10/month
- **Total: ~$235-335/month**

### 8.3 Monitoring

CloudWatch metrics:
- Lambda duration and errors
- Segment processing times
- Stuck segment detection
- Story completion rates
- API response times

## 9. Security

### 9.1 Authentication

- All APIs require Cognito JWT tokens
- Character ownership verified via PlayerID
- GameMode prevents concurrent access

### 9.2 Data Validation

- UUID format validation
- Business rule enforcement
- Server-side outcome calculation
- Rate limiting on endpoints

## 10. Deployment

### 10.1 CDK Integration

The incremental game functions integrate seamlessly with the existing Eidolon Engine CDK infrastructure. Rather than creating a separate stack, the incremental components are added to the existing Lambda function definitions and share the same DynamoDB tables, API Gateway, and authentication system. This approach minimizes operational overhead and ensures consistent deployment patterns. The EventBridge rule for segment polling starts in a disabled state and is dynamically enabled only when players have active stories, preventing unnecessary Lambda invocations during idle periods.

```python
# Lambda function definitions in CDK
incremental_functions = [
    'api_get_stories',
    'api_start_story', 
    'api_submit_decision',
    'api_get_current_story',
    'api_abandon_story',
    'api_get_segment_status',
    'api_get_segment_history',
    'ops_segment_poller',
    'ops_process_segment',
    'ops_advance_story'
]

# Create Lambda functions with shared configuration
for func_name in incremental_functions:
    lambda_function = aws_lambda.Function(
        self, f"Incremental{func_name}",
        runtime=aws_lambda.Runtime.PYTHON_3_12,
        handler=f"{func_name}.lambda_handler",
        code=aws_lambda.Code.from_asset("lambda"),
        environment=common_env_vars,
        timeout=Duration.seconds(30)
    )
    
    # Grant DynamoDB permissions
    for table in [story_table, segments_table, active_segments_table]:
        table.grant_read_write_data(lambda_function)
```

### 10.2 Environment Variables

Required for Lambda functions:
- STORY_TABLE
- SEGMENTS_TABLE  
- ACTIVE_SEGMENTS_TABLE
- CHARACTER_TABLE
- OPPONENTS_TABLE
- STORY_HISTORY_TABLE
- SEGMENT_HISTORY_TABLE
- SEGMENT_QUEUE_URL
- STORY_ADVANCEMENT_QUEUE_URL
- SSM_PARAMETER_NAME