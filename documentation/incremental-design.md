# Eidolon Engine Incremental Game Technical Design

## 1. Architecture Overview

### 1.1 System Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Flutter Web    │────▶│   API Gateway    │────▶│ Lambda Functions│
│ (Incremental)   │     │  api.{domain}    │     │  16 Functions   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                    ┌──────────────────────────────────────┼────────────┐
                    │                                      │            │
              ┌─────▼─────┐                        ┌──────▼──────┐     │
              │ DynamoDB  │                        │ EventBridge │     │
              │ 14 Tables │                        │   (1 min)   │     │
              └───────────┘                        └──────┬──────┘     │
                                                          │            │
                                                   ┌──────▼──────┐     │
                                                   │  SQS Queue  │─────┘
                                                   │ (Processing)│
                                                   └─────────────┘
                                                   ┌─────────────┐
                                                   │  SQS Queue  │─────┘
                                                   │ (Advancement)│
                                                   └─────────────┘
```

**Infrastructure Context (9 CDK Stacks):**

- **Lambda Stack**: 16 functions with shared execution role
- **DynamoDB Stack**: 14 tables with managed IAM policy
- **Story Stack**: SQS queues, EventBridge rule, SSM parameter
- **API Stack**: API Gateway with Lambda integrations
- **Client Stack**: CloudFront and automated portal build

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

All endpoints use the existing API Gateway at `api.{domain}`. Field names use PascalCase to match DynamoDB schemas.

| Method | Endpoint          | Lambda Function      | Purpose                    |
| ------ | ----------------- | -------------------- | -------------------------- |
| GET    | /archetype        | api-archetype-list   | List available archetypes  |
| POST   | /character        | api-character-add    | Create new character       |
| DELETE | /character        | api-character-delete | Delete character           |
| GET    | /character        | api-character-get    | Get character details      |
| GET    | /character/list   | api-character-list   | List player's characters   |
| POST   | /segment/decision | api-segment-decision | Submit player choice       |
| GET    | /segment/history  | api-segment-history  | Retrieve processed results |
| GET    | /segment/outcome  | api-segment-outcome  | Get segment outcome        |
| POST   | /segment/rest     | api-segment-rest     | Initiate rest segment      |
| GET    | /segment/status   | api-segment-status   | Check segment readiness    |
| POST   | /story/abandon    | api-story-abandon    | Exit current story         |
| POST   | /story/start      | api-story-start      | Begin a new story          |

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

**Production Lambda Functions (16 Total):**

All functions use:

- Shared execution role: `eidolon-lambda-execution-role`
- DynamoDB managed policy with DescribeTable permission
- Fixed logical IDs preventing recreation on updates
- Post-deployment updates from S3 artifacts
- Environment variables for table names and configuration

**api-story-start**

- Validates character ownership and GameMode="None"
- Creates ActiveSegments record with calculated end time
- Generates ActiveSegmentID using UUIDv7 for time-based ordering
- Sends message to `eidolon-processing-queue` for mechanical segments
- Uses DynamoDB transaction to ensure atomicity
- Environment: `SEGMENT_QUEUE_URL` for SQS integration

**ops-segment-poller** (EventBridge triggered)

- EventBridge rule: `eidolon-story-poller` (1-minute schedule)
- Reads SSM parameter `/eidolon/story/config` for run/stop state
- Queries EndTimeIndex for segments where EndTime <= Now
- Sends ALL completed segments to `eidolon-advancement-queue`
- Manages polling state (auto-disable when no segments)

**ops-segment-process** (SQS triggered)

- Triggered by `eidolon-processing-queue`
- Processes mechanical segments only
- Uses MUD mechanics for calculations:
  - ResolveStaticCheckWithXP for skill challenges
  - ResolveOpposedCheckWithXP for combat encounters
- Generates ClientEvents array for display
- Stores results in ActiveSegments record
- Environment: `SEGMENT_BATCH_SIZE` for processing limits

**ops-story-advance** (SQS triggered)

- Triggered by `eidolon-advancement-queue`
- Claims segment with ProcessingStatus state transition to prevent duplicates
- Processes simple segments (rest/decision) if not already processed
- Applies CharacterUpdates (XP, wounds, room changes)
- Creates next segment if story continues
- Resets GameMode="None" if story ends
- Writes to StoryHistory and SegmentHistory tables

## 4. Database Design

Production deployment includes 14 DynamoDB tables with RemovalPolicy.RETAIN:

### 4.1 Table Usage

**Core Tables:**

- `players`: User accounts with CharacterList
- `characters`: Character data with GameMode field
- `archetypes`: Character classes (Player: true for player-available)
- `items`, `prototypes`: Item definitions
- `rooms`, `exits`: MUD world structure (shared)
- `motd`: Message of the day

**Story Tables (Incremental/Hybrid modes):**

- `story`: Immutable story definitions
- `segments`: Immutable segment templates
- `active_segments`: Runtime instances with pre-calculated results
- `story_history`: Completed story records
- `segment_history`: Completed segment records
- `opponents`: Combat opponent definitions

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

### 8.1 AWS Services (Story Stack - Incremental/Hybrid Only)

**Lambda Functions:**

- 16 total functions deployed via Lambda Stack
- Python 3.12 runtime with eidolon library layer
- Shared execution role with DynamoDB access
- Post-deployment updates from S3 artifacts

**DynamoDB Tables:**

- 14 tables deployed via DynamoDB Stack
- Pay-per-request pricing
- Point-in-time recovery enabled
- RemovalPolicy.RETAIN for data persistence

**Story Stack Components:**

- **EventBridge**: Rule `eidolon-story-poller` (1-minute schedule, disabled by default)
- **SQS Queues**:
  - `eidolon-processing-queue`: For immediate mechanical segment processing
  - `eidolon-advancement-queue`: For all segment advancement when timers expire
- **SSM Parameter**: `/eidolon/story/config` for poller state
- **IAM Policies**: Managed policies for Lambda-SQS integration

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

### 10.1 CDK Deployment Architecture

The incremental game deploys as part of the 9-stack CDK system:

**Stack Deployment Order (Incremental Mode):**

1. **CodeBuild**: Build infrastructure and Lambda artifacts
2. **DynamoDB**: 14 tables with managed IAM policy
3. **Lambda**: Layer and 16 functions with shared execution role
4. **Player**: Cognito User Pool with PostConfirmation trigger
5. **Story**: SSM, SQS queues, EventBridge rule (Incremental/Hybrid only)
6. **API**: API Gateway with Lambda integrations
7. **Client**: CloudFront, S3, and automated incremental build

**Lambda Stack Implementation:**

```python
# From lambda_stack.py - Fixed logical IDs prevent recreation
lambda_configs = [
    # Character API functions
    ("api-archetype-list", "api_archetype_list.lambda_handler"),
    ("api-character-add", "api_character_add.lambda_handler"),
    ("api-character-delete", "api_character_delete.lambda_handler"),
    ("api-character-get", "api_character_get.lambda_handler"),
    ("api-character-list", "api_character_list.lambda_handler"),
    # Story API functions
    ("api-segment-decision", "api_segment_decision.lambda_handler"),
    ("api-segment-history", "api_segment_history.lambda_handler"),
    ("api-segment-outcome", "api_segment_outcome.lambda_handler"),
    ("api-segment-rest", "api_segment_rest.lambda_handler"),
    ("api-segment-status", "api_segment_status.lambda_handler"),
    ("api-story-abandon", "api_story_abandon.lambda_handler"),
    ("api-story-start", "api_story_start.lambda_handler"),
    # Operational functions
    ("cognito-player-new", "cognito_player_new.lambda_handler"),
    ("ops-segment-poller", "ops_segment_poller.lambda_handler"),
    ("ops-segment-process", "ops_segment_process.lambda_handler"),
    ("ops-story-advance", "ops_story_advance.lambda_handler"),
]
```

**Portal Build Automation:**

- CodeBuild uses `buildspec/incremental.yml`
- Builds from `incremental/` directory
- Syncs to S3 and invalidates CloudFront
- Portal URL displayed on completion

### 10.2 Environment Variables

All Lambda functions receive standardized environment variables:

**Common Variables (from lambda_stack.py):**

```python
"APPLICATION_NAME": "eidolon-engine"
"LOG_LEVEL": "INFO"  # Validated by eidolon/environment.py
"ALLOWED_ORIGINS": f"https://{client_host}.{domain}"
"CORS_ALLOW_CREDENTIALS": "true"
"CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,..."
"CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS"
"CORS_MAX_AGE": "86400"
```

**DynamoDB Table Names:**

```python
"players_table": "players"
"characters_table": "characters"
"archetypes_table": "archetypes"
"items_table": "items"
"prototypes_table": "prototypes"
"story_table": "story"
"segments_table": "segments"
"active_segments_table": "active_segments"
"story_history_table": "story_history"
"segment_history_table": "segment_history"
"opponents_table": "opponents"
```

**Story Stack Integration (Incremental/Hybrid):**

```python
"SEGMENT_QUEUE_URL": "https://sqs.{region}.amazonaws.com/{account}/eidolon-processing-queue"
"STORY_ADVANCEMENT_QUEUE_URL": "https://sqs.{region}.amazonaws.com/{account}/eidolon-advancement-queue"
"SSM_POLLER_STATE_PARAMETER": "/eidolon/story/config"
"SEGMENT_BATCH_SIZE": "10"  # For ops-segment-process
```

### 10.3 Production Deployment Status

**Deployment Metrics:**

- **9 CDK Stacks**: All operational in production
- **16 Lambda Functions**: Deployed with fixed logical IDs
- **14 DynamoDB Tables**: Created with RemovalPolicy.RETAIN
- **Module Size**: 94% under 300 lines (modular architecture)
- **Deployment Time**: Full deployment in under 15 minutes
- **Lessons Applied**: 140 documented improvements implemented

**Key Implementation Details:**

- Fixed logical IDs prevent resource recreation
- Post-deployment Lambda updates from S3
- Automated portal build via CodeBuild
- CORS handled at Lambda level with environment variables
- Cognito trigger permissions managed post-deployment
