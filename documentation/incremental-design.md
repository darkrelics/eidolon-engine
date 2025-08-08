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
3. **Polling System**: EventBridge triggers every minute to find completed segments
4. **Dual Queue Processing**:
   - Segment Processing Queue: Mechanical segments processed immediately when created
   - Story Advancement Queue: All segments processed when timer expires
5. **Result Application**: Pre-calculated outcomes applied and story advanced

## 2. API Design

### 2.1 RESTful Endpoints

All endpoints extend the existing API Gateway configuration. Field names use PascalCase to match DynamoDB schemas.

| Method | Endpoint           | Lambda Function         | Purpose                              |
| ------ | ------------------ | ----------------------- | ------------------------------------ |
| GET    | /stories           | api_get_stories         | List available stories for character |
| POST   | /stories/start     | api_start_story         | Begin a new story                    |
| GET    | /stories/current   | api_get_current_story   | Get active story state               |
| POST   | /stories/abandon   | api_abandon_story       | Exit current story                   |
| POST   | /segments/decision | api_submit_decision     | Submit player choice                 |
| GET    | /segments/status   | api_get_segment_status  | Check segment readiness              |
| GET    | /segments/history  | api_get_segment_history | Retrieve processed results           |

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
1. EventBridge: Trigger ops_segment_poller every minute
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

The Flutter client follows a restructured architecture that prioritizes user experience and efficient resource usage. The application flow moves from authentication through character selection to a unified game screen with persistent character and inventory panels. The architecture emphasizes responsive design with desktop-first considerations while maintaining mobile compatibility.

```
incremental/lib/
├── screens/
│   ├── login_screen.dart
│   ├── registration_screen.dart
│   ├── password_reset_screen.dart
│   ├── character_screen.dart      # Character management (create/delete/select)
│   ├── game_screen.dart           # Three-panel responsive layout
│   └── account_settings_screen.dart
├── widgets/
│   ├── game/
│   │   ├── character_panel.dart   # Left panel - always visible
│   │   ├── inventory_panel.dart   # Right panel - always visible
│   │   └── story_panel.dart       # Center panel - dynamic content
│   ├── story/
│   │   ├── active_story_widget.dart    # Active story with segments
│   │   ├── available_stories_widget.dart # Story selection cards
│   │   └── story_history_widget.dart   # Completed stories (chronological)
│   └── shared/
│       ├── loading_dialog.dart    # "Entering game" confirmation
│       └── responsive_layout.dart # Breakpoint handling
├── services/
│   ├── api_service.dart
│   └── auth_service.dart
├── models/
│   ├── character.dart
│   ├── story.dart
│   ├── active_segment.dart
│   └── segment_outcome.dart
└── providers/
    ├── auth_provider.dart
    ├── character_provider.dart
    └── segment_provider.dart
```

### 7.2 User Interface Flow

**Navigation Flow:**

1. **Authentication** → Login/Registration screens
2. **Character Screen** → Select, create, or delete characters
3. **Loading Dialog** → "Entering game" confirmation reduces perceived load time
4. **Game Screen** → Three-panel layout with persistent character/inventory

**Responsive Design Breakpoints:**

- **Desktop** (≥1200px): Three-column layout `[Character | Story | Inventory]`
- **Tablet** (≥768px): Collapsible sidebars with story focus
- **Mobile** (<768px): Tab/drawer navigation for panels

**Story Panel States:**

- **Active Story**: Story card, rest/abandon buttons, current segment, segment history
- **No Active Story**: Available stories grid (default view)
- **History View**: Chronologically ordered completed stories (most recent first)

### 7.3 State Management

The application uses Provider pattern with focused state management:

- **AuthProvider**: Authentication state and session management
- **CharacterProvider**: Character data caching and updates
- **SegmentProvider**: Active segment state and polling coordination

Character and inventory panels maintain static display with cached data, while only the story panel shows loading states. This approach prevents layout shifts and provides a stable user experience.

### 7.4 Polling Strategy

The client implements a sophisticated polling strategy optimized for server efficiency and gameplay experience:

**Initial Load:**

- Get character data before transitioning to game screen
- Cache character data with 5-minute validity

**Active Story Polling:**

- **Initial Check**: Poll 1 minute after game screen loads
- **Decision Segments**: Prompt for player input, no polling
- **Rest Segments**: Continue immediately to next segment
- **Mechanical Segments**:
  - Begin processing result display
  - Poll once per minute until completion
  - Segments can last from minutes to 24 hours
- **Segment Completion**: Automatically load next segment

**Timer-Driven Approach:**

- Use segment end times to schedule polls
- Reduce server load by 95% compared to constant polling
- Maintain responsiveness for player actions

```dart
class PollingManager {
  Timer? _pollTimer;

  void scheduleNextPoll(ActiveSegment segment) {
    _pollTimer?.cancel();

    if (segment.segmentType == 'decision') {
      // No polling needed - wait for user input
      return;
    }

    if (segment.segmentType == 'rest') {
      // Process immediately
      processNextSegment();
      return;
    }

    // Mechanical segment - poll every minute
    _pollTimer = Timer.periodic(
      Duration(minutes: 1),
      (_) => checkSegmentStatus(),
    );
  }
}
```

## 8. Infrastructure

### 8.1 AWS Services

- **Lambda**: Python 3.12 runtime with eidolon library
- **DynamoDB**: Pay-per-request pricing
- **EventBridge**: Single rule, 1-minute schedule
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
