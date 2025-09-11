# Eidolon Engine API Documentation

## Overview

The Eidolon Engine API provides RESTful endpoints for both MUD and Incremental game modes. Deployed via API Gateway with Lambda integrations, all endpoints require authentication via AWS Cognito and return JSON responses with PascalCase keys.

## Infrastructure

- **API Gateway**: REST API deployed at `api.{domain}` with Cognito authorizer
- **Lambda Functions**: 16 functions with shared execution role and DynamoDB access
- **CORS Configuration**: Handled at Lambda level with environment variables
- **Deployment**: Part of 9-stack CDK deployment system (API Stack #8)

## Authentication

All API endpoints require authentication using AWS Cognito JWT tokens from the `eidolon-users` User Pool. The token should be included in the `Authorization` header:

```
Authorization: Bearer <jwt-token>
```

**Cognito Configuration:**

- User Pool: `eidolon-users`
- PostConfirmation Trigger: `cognito-player-new` Lambda
- Permissions managed post-deployment for imported pools

## Lambda Functions

All API endpoints are implemented as individual Lambda functions:

### Character Management

- `api-archetype-list` - GET /archetype
- `api-character-add` - POST /character
- `api-character-delete` - DELETE /character
- `api-character-get` - GET /character
- `api-character-list` - GET /character/list

### Story Management

- `api-segment-decision` - POST /segment/decision
- `api-segment-history` - GET /segment/history
- `api-segment-rest` - POST /segment/rest
- `api-segment-status` - GET /segment/status
- `api-story-abandon` - POST /story/abandon
- `api-story-start` - POST /story/start

### Operational Functions (Not API-exposed)

- `cognito-player-new` - Cognito PostConfirmation trigger
- `ops-segment-poller` - EventBridge scheduled polling
- `ops-segment-process` - SQS segment processor
- `ops-story-advance` - SQS story advancement

## Common Response Formats

### Success Response

All successful responses return HTTP 200 with JSON data using PascalCase keys matching DynamoDB field names.

#### **Data Type Conversion Standards**

**DynamoDB → API Response Conversion:**

- **Decimal → Float**: All DynamoDB Decimal values automatically converted to JSON floats
- **Precision**: 64-bit IEEE 754 floats provide sufficient precision for all game values
- **Integer Semantics**: Values that represent counts (Health, RoomID, Currency) are returned as floats but should be treated as integers by clients
- **Fractional Values**: Skills, attributes, and XP values are true floats with 2-3 decimal precision

**Value Categories:**

```json
{
  "Health": 12.0, // Integer semantic (display as 12, not 12.0)
  "Stealth": 5.375, // Fractional semantic (display with precision)
  "RoomID": 100.0, // Integer semantic (use as 100)
  "SkillXP": {
    "fighting": 0.375 // Fractional semantic (preserve precision)
  }
}
```

**Client Handling Guidelines:**

- **Flutter**: Receive all numbers as `double`, convert to `int` for display when semantically appropriate
- **Precision**: No precision loss occurs for game values (0.00-10.00 range)
- **Display**: Show integer semantics without decimal (12, not 12.0), show fractional with 2-3 decimals (5.38, not 5.375)

### Standardized Error Response Format

**All error responses use this exact format**:

```json
{
  "Error": "Descriptive error message"
}
```

**Field Naming Rules**:

- Error field is always PascalCase `"Error"` (never `"error"` or `"message"`)
- Error messages are user-friendly strings
- No additional error fields unless specifically documented

**HTTP Status Code Standards**:

- `400` - Bad Request: Invalid parameters, malformed JSON, validation failures
- `401` - Unauthorized: Missing/invalid JWT token, authentication failures
- `403` - Forbidden: Valid auth but access denied (character not owned, story not available)
- `404` - Not Found: Resource doesn't exist (character, story, segment not found)
- `409` - Conflict: Resource state conflict (character busy, decision already made)
- `500` - Internal Server Error: Database failures, AWS service issues, unexpected errors

---

## Client Polling Strategy

**CRITICAL PRINCIPLE**: The client follows **server-authoritative design** - all timing and state decisions come from the server. Clients never predict segment completion or implement complex state logic.

### Server-Authoritative Polling Flow

**Simple 4-Step Loop:**

1. **Initial Wait**: Always wait 60 seconds after story start for server processing
2. **Check Character State**: `GET /character?CharacterID=uuid`
   - If `ActiveSegmentID == null` → Story complete, stop polling
3. **Get Server Timing**: `GET /segment/status?CharacterID=uuid`
   - Use server's `TimeRemaining` value exactly
4. **Wait Server Time**: Wait the exact seconds server specifies, then repeat from step 2

### API Call Pattern

**Per Segment (Normal Case):**

- 1x `GET /character` - Check story completion
- 1x `GET /segment/status` - Get server timing
- **Total: 2 API calls maximum**

**Error Cases:**

- Network timeout: Wait 30 seconds, retry same call
- 404 response: Story complete, stop polling
- Other errors: Wait 30 seconds, retry same call

### Implementation Requirements

#### **Simple Polling Service (Recommended Pattern)**

```dart
// File: lib/services/story_polling_service.dart
import 'dart:async';
import 'package:flutter/foundation.dart';

class StoryPollingService {
  final ApiService _apiService;
  bool _isPolling = false;
  Timer? _pollTimer;

  // Callbacks for UI updates
  Function(Character?)? onCharacterUpdated;
  Function(String)? onPollingError;
  Function()? onStoryCompleted;

  StoryPollingService({required ApiService apiService})
      : _apiService = apiService;

  /// Start server-authoritative polling
  Future<void> startPolling(String characterId) async {
    if (_isPolling) return;
    _isPolling = true;

    try {
      await _runPollingLoop(characterId);
    } finally {
      _isPolling = false;
    }
  }

  /// Core polling loop following server cadence exactly
  Future<void> _runPollingLoop(String characterId) async {
    int consecutiveErrors = 0;
    const maxConsecutiveErrors = 3;

    // ALWAYS wait 60 seconds initially for server processing
    await Future.delayed(const Duration(seconds: 60));

    while (_isPolling) {
      try {
        // Step 1: Get character state from server
        final character = await _apiService.getCharacterById(characterId);
        onCharacterUpdated?.call(character);

        // Step 2: Check if story is complete
        if (character?.activeSegmentID == null) {
          onStoryCompleted?.call();
          break; // Story finished
        }

        // Step 3: Get segment timing from server
        final segmentStatus = await _apiService.getSegmentStatus(
          characterId: characterId
        );

        // Step 4: Wait exactly what server says
        final timeRemaining = segmentStatus['TimeRemaining'] as int? ?? 0;
        if (timeRemaining > 0) {
          await _waitWithCancellation(Duration(seconds: timeRemaining));
        } else {
          await _waitWithCancellation(const Duration(seconds: 5));
        }

        consecutiveErrors = 0; // Reset on success

      } catch (e) {
        consecutiveErrors++;

        // Handle 404 as story completion
        if (e.toString().contains('404') ||
            e.toString().toLowerCase().contains('no active segment')) {
          onStoryCompleted?.call();
          break;
        }

        // Stop after too many errors
        if (consecutiveErrors >= maxConsecutiveErrors) {
          onPollingError?.call('Connection problems - please refresh');
          break;
        }

        // 30-second retry delay
        await _waitWithCancellation(const Duration(seconds: 30));
      }
    }
  }

  Future<void> _waitWithCancellation(Duration duration) async {
    final completer = Completer<void>();
    _pollTimer = Timer(duration, () => completer.complete());

    while (_isPolling && !completer.isCompleted) {
      await Future.delayed(const Duration(milliseconds: 100));
    }

    _pollTimer?.cancel();
  }

  void stopPolling() {
    _isPolling = false;
    _pollTimer?.cancel();
  }

  void dispose() => stopPolling();
}
```

#### **Integration with Game Screen**

```dart
// File: lib/screens/game_screen.dart
class _GameScreenState extends State<GameScreen> {
  late StoryPollingService _pollingService;
  Character? _character;

  @override
  void initState() {
    super.initState();

    _pollingService = StoryPollingService(apiService: _apiService);
    _pollingService.onCharacterUpdated = (character) {
      if (mounted) setState(() => _character = character);
    };
    _pollingService.onStoryCompleted = () {
      if (mounted) _loadCharacterData(); // Refresh for available stories
    };
  }

  @override
  void dispose() {
    _pollingService.dispose();
    super.dispose();
  }

  Future<void> _handleStorySelect(StoryMetadata story) async {
    await _apiService.startStory(
      characterId: _character!.id,
      storyId: story.storyID,
    );

    // Start polling - replaces all complex polling logic
    _pollingService.startPolling(_character!.id);
  }

  // REMOVE these methods completely:
  // - _runStoryPolling()
  // - _setupSegmentPolling()
  // - Complex timing calculations
  // - Local segment history management
}
```

### What NOT to Implement

❌ **Segment Type Logic**: Don't treat decision/mechanical/rest differently  
❌ **Multiple Polling Loops**: Only one polling process per character  
❌ **Client-side Timing**: Don't calculate EndTime from StartTime + Duration  
❌ **Local History Management**: Use server's segment history API only  
❌ **Complex Error Recovery**: Simple exponential backoff only  
❌ **Predictive State Updates**: Wait for server state changes

### Error Handling Standards

**Network Errors**:

```dart
catch (NetworkException e) {
  await Future.delayed(Duration(seconds: 30));
  continue; // Retry same operation
}
```

**404 Not Found**:

```dart
catch (NotFoundException e) {
  break; // Story complete, stop polling
}
```

**Rate Limiting**:

```dart
catch (RateLimitException e) {
  await Future.delayed(Duration(seconds: e.retryAfterSeconds ?? 60));
  continue; // Retry same operation
}
```

**Maximum Error Protection**:

- Stop polling after 3 consecutive errors
- Never poll faster than every 30 seconds minimum
- Use consistent 30-second retry delay for all errors

### Segment Processing Timeout Handling

#### **Server Timeout Behavior by Segment Type**

**Mechanical Segments:**

- **Normal**: Process within 5 minutes, advance at EndTime
- **Stuck**: Retry if >5 minutes old and >90 seconds remaining
- **Timeout**: Auto-marked "exceptional" outcome if not processed by EndTime
- **Client Display**: Show "Processing..." until ProcessingStatus="processed"

**Decision Segments:**

- **Normal**: No processing needed, wait for player input or EndTime
- **Timeout**: Apply DefaultDecision from segment definition
- **Client Display**: Show choices until EndTime, then show result

**Rest Segments:**

- **Normal**: No processing needed, advance at EndTime
- **Timeout**: Normal advancement with healing applied
- **Client Display**: Show countdown timer until EndTime

#### **Client Timeout Handling**

```dart
// Handle different processing states in UI
Widget buildSegmentDisplay(Map<String, dynamic> segmentStatus) {
  final segmentType = segmentStatus['SegmentType'] as String;
  final processingStatus = segmentStatus['ProcessingStatus'] as String? ?? 'pending';
  final timeRemaining = segmentStatus['TimeRemaining'] as int? ?? 0;
  final startTime = segmentStatus['StartTime'] as int? ?? 0;
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;

  // Calculate how long segment has been running
  final elapsedMinutes = (now - startTime) ~/ 60;

  if (segmentType == 'mechanical') {
    if (processingStatus == 'pending' && elapsedMinutes > 5) {
      return Text('Processing delayed - retrying...');
    } else if (processingStatus == 'pending') {
      return Text('Processing your actions...');
    } else if (processingStatus == 'processed') {
      return Text('Ready to advance!');
    }
  }

  // For decision/rest, just show normal countdown
  return Text('Time remaining: ${timeRemaining}s');
}
```

#### **Timeout Communication Strategy**

**For Players:**

- **0-5 minutes**: "Processing your actions..."
- **5-15 minutes**: "Processing delayed - retrying..."
- **15+ minutes approaching EndTime**: "Resolving automatically..."
- **After exceptional assignment**: "System protected you - exceptional result!"

**For Developers:**

- **CloudWatch Logs**: All timeouts logged with segment ID and timing
- **Metrics**: Track exceptional outcomes as potential system health indicator
- **Monitoring**: Alert on high exceptional outcome rates (indicates processing issues)

---

## API Parameter Standards

### Parameter Placement Rules

**Consistent parameter handling across all endpoints:**

1. **Query Parameters**: Used for GET and DELETE requests only
   - Example: `GET /character?CharacterID=uuid`
   - Example: `DELETE /character?CharacterID=uuid`

2. **Request Body (JSON)**: Used for ALL POST and PUT requests
   - Example: `POST /story/start` with body `{"CharacterID": "uuid", "StoryID": "uuid"}`
   - Example: `POST /story/abandon` with body `{"CharacterID": "uuid"}`

3. **Field Naming**: Follow PascalCase conventions defined in [Style Guide](style-guide.md#json-field-naming-convention)

### Important: NO Path Parameters for IDs

- **Never use**: `/characters/123` or `/stories/456`
- **Always use**: Query parameters for GET/DELETE, request body for POST/PUT

---

## Endpoints

### Get Archetypes

Retrieves all player-available archetypes for character creation.

**Endpoint:** `GET /archetype`

**Authentication:** Required

**Request:**

```http
GET /archetype HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Archetypes": [
    {
      "ArchetypeName": "Knight",
      "Description": "A stalwart defender skilled in combat and honor",
      "Attributes": {
        "Strength": 8,
        "Agility": 5,
        "Endurance": 7,
        "Charisma": 6,
        "Intrigue": 3,
        "Presence": 7,
        "Perception": 4,
        "Intelligence": 4,
        "Cunning": 3
      },
      "Skills": {
        "Melee": 10,
        "Parry": 8,
        "Dodge": 4
      },
      "Health": 12,
      "Essence": 3,
      "StartRoom": 100,
      "StartingItems": [
        {
          "PrototypeID": "sword_basic",
          "Slot": "1",
          "IsWorn": false
        }
      ],
      "AvailableStories": ["story_knight_honor", "story_common_intro"]
    }
  ],
  "Count": 5
}
```

**Response Fields:**

| Field        | Type    | Description                         |
| ------------ | ------- | ----------------------------------- |
| `Archetypes` | Array   | List of available player archetypes |
| `Count`      | Integer | Total number of archetypes returned |

**Archetype Object:**

| Field              | Type    | Description                                          |
| ------------------ | ------- | ---------------------------------------------------- |
| `ArchetypeName`    | String  | Unique identifier and display name for the archetype |
| `Description`      | String  | Flavor text describing the archetype                 |
| `Attributes`       | Object  | Map of attribute names to their starting values      |
| `Skills`           | Object  | Map of skill names to their starting values          |
| `Health`           | Integer | Starting maximum health points                       |
| `Essence`          | Integer | Starting maximum essence (mana) points               |
| `StartRoom`        | Integer | Room ID where new characters of this archetype begin |
| `StartingItems`    | Array   | List of items the character starts with              |
| `AvailableStories` | Array   | List of story IDs available to this archetype        |

**Starting Item Object:**

| Field         | Type    | Description                             |
| ------------- | ------- | --------------------------------------- |
| `PrototypeID` | String  | ID of the item prototype to create      |
| `Slot`        | String  | Inventory slot where the item is placed |
| `IsWorn`      | Boolean | Whether the item starts equipped        |

**Implementation Notes:**

1. **Lambda Configuration:** The `api-archetype-list` function uses:
   - Shared execution role: `eidolon-lambda-execution-role`
   - DynamoDB policy: `eidolon-dynamodb-policy` with DescribeTable permission
   - Environment variables: Table names from DynamoDB stack outputs
   - Fixed logical ID: `ApiArchetypeListFunction` preventing recreation

2. **Caching:** The Lambda function caches archetypes at cold start to minimize database calls. The cache persists for the lifetime of the Lambda instance.

3. **Filtering:** Only archetypes with `Player: true` in the database are returned, excluding NPC-only archetypes.

4. **Client Usage:** The Flutter client uses a subset of the returned fields, ignoring `StartRoom`, `StartingItems`, and `AvailableStories` in its `ArchetypeInfo` model.

**Example Client Code (Dart):**

```dart
final response = await apiService.getArchetypes();
// Returns List<ArchetypeInfo> with name, description, attributes, skills, health, essence
```

**Error Responses:**

| Status | Error Message               | Cause                                |
| ------ | --------------------------- | ------------------------------------ |
| `500`  | "Failed to load archetypes" | Database connection or query failure |
| `401`  | "Unauthorized"              | Invalid or missing JWT token         |

---

### List Characters

Retrieves a list of all characters belonging to the authenticated player.

**Endpoint:** `GET /character/list`

**Authentication:** Required

**Request:**

```http
GET /character/list HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Characters": [
    {
      "CharacterName": "Aragorn",
      "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
      "Dead": false
    },
    {
      "CharacterName": "Boromir",
      "CharacterID": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "Dead": true
    }
  ]
}
```

**Response Fields:**

| Field        | Type  | Description                            |
| ------------ | ----- | -------------------------------------- |
| `Characters` | Array | List of characters owned by the player |

**Character Object:**

| Field           | Type    | Description                                |
| --------------- | ------- | ------------------------------------------ |
| `CharacterName` | String  | Display name of the character              |
| `CharacterID`   | String  | Unique identifier (UUID) for the character |
| `Dead`          | Boolean | Whether the character has died             |

**Implementation Notes:**

1. **Lambda Configuration:** The `api-character-list` function:
   - Uses the shared Lambda execution role
   - Accesses the `players` DynamoDB table
   - Returns PascalCase field names matching database schema
   - Post-deployment updates ensure latest code from S3

2. **Data Source:** Character information is retrieved from the Player table's `CharacterList` field, providing a lightweight response without requiring multiple database queries.

3. **No Caching:** This endpoint always returns fresh data to ensure players see their current character list immediately after character creation or death.

4. **Client Handling:** The Flutter client adds a default `GameMode: 'None'` if not provided by the API for defensive programming.

**Example Client Code (Dart):**

```dart
final characters = await apiService.listCharacters();
// Returns List<CharacterInfo> with name, id, dead status
// Empty list returned if player has no characters
```

**Error Responses:**

| Status | Error Message           | Cause                                       |
| ------ | ----------------------- | ------------------------------------------- |
| `404`  | "Player not found"      | Player ID exists in JWT but not in database |
| `401`  | "Unauthorized"          | Invalid or missing JWT token                |
| `500`  | "Internal server error" | Database connection or query failure        |

---

### Add Character

Creates a new character for the authenticated player.

**Endpoint:** `POST /character`

**Authentication:** Required

**Request:**

```http
POST /character HTTP/1.1
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "CharacterName": "Gandalf",
  "ArchetypeName": "Wizard"
}
```

**Request Body:**

| Field           | Type   | Required | Description                                                                   |
| --------------- | ------ | -------- | ----------------------------------------------------------------------------- |
| `CharacterName` | String | Yes      | Desired name for the character (3-32 characters, letters/spaces/hyphens only) |
| `ArchetypeName` | String | No       | Archetype to use (defaults to "default" if not specified or invalid)          |

**Response:**

```json
{
  "CharacterID": "7ba8c520-a5d2-4e8f-b3c1-9f2e3d4c5b6a",
  "CharacterName": "Gandalf",
  "Archetype": "Wizard",
  "Message": "Character created successfully"
}
```

**Response Fields:**

| Field           | Type   | Description                                        |
| --------------- | ------ | -------------------------------------------------- |
| `CharacterID`   | String | Unique identifier (UUID) for the created character |
| `CharacterName` | String | The character's name as stored                     |
| `Archetype`     | String | The archetype that was applied                     |
| `Message`       | String | Success confirmation message                       |

**Implementation Notes:**

1. **Lambda Configuration:** The `api-character-add` function:
   - Accesses both `characters` and `archetypes` tables
   - Uses environment variable `MAX_CHARACTERS_PER_PLAYER` (default 1)
   - Validates against bloom filter loaded at function initialization
   - Fixed logical ID: `ApiCharacterAddFunction`

2. **Name Validation:** Character names must:
   - Be 3-32 characters long
   - Contain only letters, spaces, and hyphens
   - Not be in the restricted names bloom filter
   - Not already exist in the database

3. **Character Limit:** Players can create up to the configured maximum (from environment variable).

4. **Archetype Resolution:**
   - If no archetype is specified, "default" is used
   - If an invalid archetype is specified, "default" is used with a log warning
   - Only player-available archetypes (`Player: true`) can be used

5. **Starting Items:** Based on the archetype's `StartingItems` configuration:
   - Items are created from prototypes and added to the character's inventory
   - The first container item becomes the primary container (e.g., backpack)
   - Worn items (`IsWorn: true`) are equipped automatically
   - Non-worn items are placed inside the primary container

6. **Initial State:** New characters start with:
   - Full health (based on archetype)
   - Full essence (based on archetype)
   - No wounds
   - No active story
   - Archetype-defined attributes and skills

**Example Client Code (Dart):**

```dart
final result = await apiService.addCharacter(
  name: "Gandalf",
  archetype: "Wizard"
);
// Returns map with CharacterID, CharacterName, Archetype, Message
```

**Error Responses:**

| Status | Error Message                     | Cause                                       |
| ------ | --------------------------------- | ------------------------------------------- |
| `400`  | "CharacterName is required"       | Missing character name in request           |
| `400`  | "Character name must be..."       | Name validation failure (length/characters) |
| `400`  | "Character name is not available" | Name is in restricted list                  |
| `400`  | "Character limit reached (X)"     | Player has maximum allowed characters       |
| `409`  | "Character name is already taken" | Name exists in database                     |
| `401`  | "Unauthorized"                    | Invalid or missing JWT token                |
| `500`  | "Internal server error"           | Database or system failure                  |

---

### Get Character

Retrieves complete character data including active story and segment information.

**Endpoint:** `GET /character`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character to retrieve |

**Request:**

```http
GET /character?CharacterID=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Character": {
    "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
    "PlayerID": "123e4567-e89b-12d3-a456-426614174000",
    "CharacterName": "Aragorn",
    "GameMode": "Incremental",
    "RoomID": 100,
    "Inventory": {
      "0": "abc123-item-uuid",
      "1": "def456-item-uuid"
    },
    "InventoryDetails": {
      "0": {
        "ItemID": "abc123-item-uuid",
        "Name": "Leather Backpack",
        "Description": "A sturdy leather backpack",
        "Quantity": 1,
        "Stackable": false,
        "Equipped": true,
        "Mass": 2,
        "Value": 50
      },
      "1": {
        "ItemID": "def456-item-uuid",
        "Name": "Iron Sword",
        "Description": "A well-crafted iron sword",
        "Quantity": 1,
        "Stackable": false,
        "Equipped": false,
        "Mass": 3,
        "Value": 100
      }
    },
    "Attributes": {
      "Strength": 8,
      "Agility": 5,
      "Endurance": 7,
      "Charisma": 6,
      "Intrigue": 3,
      "Presence": 7,
      "Perception": 4,
      "Intelligence": 4,
      "Cunning": 3
    },
    "Skills": {
      "Melee": 10,
      "Parry": 8,
      "Dodge": 4
    },
    "Essence": 3,
    "MaxHealth": 12,
    "Wounds": [
      {
        "DamageType": "bashing",
        "HealAt": "2025-01-15T14:30:00Z"
      }
    ],
    "CharState": "standing",
    "AvailableStories": ["story_1", "story_2"],
    "AbandonedStories": [],
    "CompletedStories": ["story_intro"],
    "ActiveStoryID": "story_current_uuid",
    "ActiveSegmentID": "segment_current_uuid",
    "Archetype": "Knight",
    "MaxEssence": 3,
    "Resources": {
      "gold": 150,
      "supplies": 10
    },
    "Progress": {
      "tutorial_completed": true,
      "first_boss_defeated": false
    }
  },
  "ActiveStory": {
    "StoryID": "story_current_uuid",
    "Title": "The Dark Tower",
    "Description": "Investigate the mysterious tower",
    "EstimatedDuration": 1800
  },
  "ActiveSegment": {
    "ActiveSegmentID": "segment_current_uuid",
    "SegmentID": "segment_def_uuid",
    "SegmentType": "mechanical",
    "Status": "active",
    "StartTime": 1704900000,
    "EndTime": 1704900300,
    "Outcome": "normal",
    "ClientEvents": [
      {
        "Title": "Combat Begins",
        "Description": "A goblin jumps out from the shadows!"
      }
    ]
  }
}
```

**Response Fields:**

| Field              | Type   | Description                                                                                      |
| ------------------ | ------ | ------------------------------------------------------------------------------------------------ |
| `Character`        | Object | Complete character data                                                                          |
| `ActiveStory`      | Object | Current story details (optional - only present if character has active story)                    |
| `ActiveSegment`    | Object | Current segment details (optional - only present if character has active segment)                |
| `AvailableStories` | Array  | List of available stories (optional - only present if no active story and stories are available) |

**Character Object:**

Contains all character fields as stored in the database, plus:

| Field              | Type   | Description                                   |
| ------------------ | ------ | --------------------------------------------- |
| `InventoryDetails` | Object | Enriched inventory with full item information |

**InventoryDetails Structure (PascalCase):**

Maps inventory slot numbers to detailed item information:

```json
{
  "SlotNumber": {
    "ItemID": "UUID",
    "Name": "Item Name",
    "Description": "Item description",
    "Quantity": 1,
    "Stackable": false,
    "Equipped": false,
    "Mass": 1.5,
    "Value": 100
  }
}
```

**Implementation Notes:**

1. **Lambda Configuration:** The `api-character-get` function:
   - Accesses `characters`, `story`, `segments`, and `items` tables
   - Enriches response with multiple table lookups
   - Environment includes all DynamoDB table names
   - Uses shared execution role with DynamoDB policy

2. **Character Ownership:** The Lambda validates that the requested character belongs to the authenticated player. Attempting to access another player's character returns 404.

3. **Response Field Behavior:** The response dynamically includes different fields based on the character's state:
   - **With active story:** Includes `ActiveStory` and `ActiveSegment` objects (if present), does NOT include `AvailableStories`
   - **Without active story:** Does NOT include `ActiveStory` or `ActiveSegment`, but includes `AvailableStories` array if any stories are available
   - Fields are completely omitted from the response rather than being set to null

4. **Available Stories:** When the character doesn't have an active story, the `AvailableStories` field is automatically populated with story details including availability status, prerequisites, and metadata. This eliminates the need for a separate API call to get available stories.

5. **Inventory Enrichment:** The `InventoryDetails` field provides full item information for UI display without requiring additional API calls. If item lookups fail, the character is still returned without enrichment.

6. **Health Calculation:** Current health is not stored but should be calculated as: `Health = MaxHealth - Wounds.length`

7. **Container Items:** Items stored inside containers (like backpacks) are not shown in the character's inventory. They exist in the container item's Contents array.

**Example Client Code (Dart):**

```dart
final character = await apiService.getCharacterById(characterId);
if (character == null) {
  // Character not found
  return;
}
// Access character data, active story, etc.
final currentHealth = character.maxHealth - character.wounds.length;
```

**Error Responses:**

| Status | Error Message                   | Cause                                               |
| ------ | ------------------------------- | --------------------------------------------------- |
| `400`  | "Missing CharacterID parameter" | No character ID provided in query string            |
| `401`  | "Unauthorized"                  | Invalid or missing JWT token                        |
| `404`  | "Character not found"           | Character doesn't exist or doesn't belong to player |
| `500`  | "Internal server error"         | Database or system failure                          |

---

### Delete Character

Deletes a character belonging to the authenticated player.

**Endpoint:** `DELETE /character`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description                     |
| ------------- | ------ | -------- | ------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character to delete |

**Request:**

```http
DELETE /character?CharacterID=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Message": "Character deleted successfully"
}
```

**Error Responses:**

| Status | Error Message                   | Cause                                               |
| ------ | ------------------------------- | --------------------------------------------------- |
| `400`  | "Missing CharacterID parameter" | No character ID provided in query string            |
| `401`  | "Unauthorized"                  | Invalid or missing JWT token                        |
| `404`  | "Character not found"           | Character doesn't exist or doesn't belong to player |
| `500`  | "Internal server error"         | Database or system failure                          |

---

### Start Story

Starts a new story for the specified character. In Incremental/Hybrid modes, this triggers the Story Stack's SQS queues for segment processing.

**Endpoint:** `POST /story/start`

**Authentication:** Required

**Request:**

```http
POST /story/start HTTP/1.1
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryID": "story_knight_honor"
}
```

**Request Body:**

| Field         | Type   | Required | Description              |
| ------------- | ------ | -------- | ------------------------ |
| `CharacterID` | String | Yes      | UUID of the character    |
| `StoryID`     | String | Yes      | ID of the story to start |

**Response:**

```json
{
  "Success": true,
  "Segment": {
    "ActiveSegmentID": "segment_uuid",
    "SegmentType": "mechanical",
    "StartTime": "2024-01-10T12:00:00Z",
    "EndTime": "2024-01-10T12:05:00Z",
    "ShortStatus": "Starting your adventure...",
    "Duration": 300,
    "ProcessingStatus": "pending"
  }
}
```

**Implementation Notes:**

1. **Lambda Configuration:** The `api-story-start` function:
   - Writes to `story`, `active_segments` tables
   - May send message to SQS queue (Incremental/Hybrid modes)
   - Environment includes `SEGMENT_QUEUE_URL` for SQS integration
   - Story Stack provides SQS permissions via managed policy

2. **Story Processing:** In Incremental/Hybrid modes:
   - Creates initial segment in `active_segments` table
   - Sends message to `eidolon-processing-queue`
   - `ops-segment-process` Lambda processes segment asynchronously

**Error Responses:**

| Status | Error Message                     | Cause                            |
| ------ | --------------------------------- | -------------------------------- |
| `403`  | "Story not available"             | Story not available to character |
| `409`  | "Character is already in a story" | Character has an active story    |
| `401`  | "Unauthorized"                    | Invalid or missing JWT token     |
| `500`  | "Internal server error"           | Database or system failure       |

---

### Abandon Story

Abandons the current active story for a character. The story cannot be resumed and must be restarted if repeatable.

**Endpoint:** `POST /story/abandon`

**Authentication:** Required

**Request:**

```http
POST /story/abandon HTTP/1.1
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Request Body:**

| Field         | Type   | Required | Description           |
| ------------- | ------ | -------- | --------------------- |
| `CharacterID` | String | Yes      | UUID of the character |

**Response:**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryID": "story_uuid",
  "Abandoned": true,
  "Message": "Story abandoned successfully"
}
```

**Error Responses:**

| Status | Error Message           | Cause                         |
| ------ | ----------------------- | ----------------------------- |
| `400`  | "No active story found" | Character has no active story |
| `401`  | "Unauthorized"          | Invalid or missing JWT token  |
| `500`  | "Internal server error" | Database or system failure    |

---

### Submit Segment Decision

Submits a player decision for the current active segment.

**Endpoint:** `POST /segment/decision`

**Authentication:** Required

**Request:**

```http
POST /segment/decision HTTP/1.1
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "Decision": "fight"
}
```

**Request Body:**

| Field         | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character             |
| `Decision`    | String | Yes      | Player's decision for the segment |

**Response:**

```json
{
  "Accepted": true,
  "NextSegmentTime": "2024-03-14T10:25:00Z", // Optional, only if there's a next segment
  "NextSegment": {
    // Optional, only if there's a next segment
    "ActiveSegmentID": "550e8400-e29b-41d4-a716-446655440001",
    "SegmentType": "mechanical",
    "ShortStatus": "Fighting the goblin",
    "DefaultStatus": "You engage the goblin in combat",
    "EndTime": "2024-03-14T10:25:00Z",
    "DecisionText": "Choose your path", // Only for decision segments
    "DecisionOptions": {
      // Only for decision segments
      "fight": "segment-uuid-1",
      "flee": "segment-uuid-2"
    },
    "DefaultDecision": "fight" // Only for decision segments
  }
}
```

**Error Responses:**

| Status | Error Message                | Cause                         |
| ------ | ---------------------------- | ----------------------------- |
| `403`  | "Access denied"              | Character not owned by player |
| `404`  | "Segment not found"          | No active segment found       |
| `409`  | "Decision already submitted" | Decision was already made     |
| `401`  | "Unauthorized"               | Invalid or missing JWT token  |
| `500`  | "Internal server error"      | Database or system failure    |

**Error Responses:**

| Status | Error Message               | Cause                        |
| ------ | --------------------------- | ---------------------------- |
| `404`  | "Segment not found"         | Segment doesn't exist        |
| `409`  | "Segment not yet completed" | Segment is still processing  |
| `401`  | "Unauthorized"              | Invalid or missing JWT token |
| `500`  | "Internal server error"     | Database or system failure   |

---

### Get Segment Status

Gets the current status of an active segment, including timing information and narrative data when the segment is processed/completed.

**Endpoint:** `GET /segment/status`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description           |
| ------------- | ------ | -------- | --------------------- |
| `CharacterID` | String | Yes      | UUID of the character |

**Request:**

```http
GET /segment/status?CharacterID=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response (Active Segment):**

```json
{
  "ActiveSegmentID": "seg-uuid",
  "StoryID": "story-uuid",
  "SegmentID": "segment-def-uuid",
  "Status": "active",
  "IsComplete": false,
  "TimeRemaining": 120,
  "EndTime": "2025-01-15T14:30:00Z",
  "ProcessingStatus": "processed",
  "SegmentType": "mechanical",
  "DefaultStatus": "Walking through the forest",
  "ClientEvents": [...],
  "ChallengeResults": [...]
}
```

**Response (Processed/Completed Segment):**

When a segment is processed or completed, additional narrative data is included:

```json
{
  "ActiveSegmentID": "seg-uuid",
  "StoryID": "story-uuid",
  "SegmentID": "segment-def-uuid",
  "Status": "active",
  "IsComplete": true,
  "TimeRemaining": 0,
  "EndTime": "2025-01-15T14:30:00Z",
  "ProcessingStatus": "processed",
  "SegmentType": "mechanical",
  "Outcome": "normal",
  "Narrative": "You successfully navigate through the forest, finding a hidden path...",
  "Effects": {
    "Wounds": 0,
    "Items": ["item_health_potion"]
  },
  "NextSegmentID": "next-segment-uuid",
  "ChallengeResults": [...],
  "CombatState": {...}
}
```

**Timing Fields:**

- `TimeRemaining`: Seconds until segment completes (0 if complete)
- `EndTime`: ISO 8601 timestamp when segment will complete
- `IsComplete`: True if EndTime has passed
- `ProcessingStatus`: "pending" (mechanical awaiting processing), "processing" (mechanical in progress), or "processed" (ready for advancement)

**Narrative Fields (when processed/completed):**

- `Narrative`: Story text describing the outcome
- `Effects`: Changes to character state (wounds, items, etc.)
- `NextSegmentID`: ID of the next segment in the story
- `Outcome`: Result type ("normal", "exceptional", "minimal", "failure", "death")

**Error Responses:**

| Status | Error Message             | Cause                        |
| ------ | ------------------------- | ---------------------------- |
| `404`  | "No active segment found" | No active segment exists     |
| `401`  | "Unauthorized"            | Invalid or missing JWT token |
| `500`  | "Internal server error"   | Database or system failure   |

---

### Get Segment History

Retrieves historical segment data for a character from the segment_history table.

**Endpoint:** `GET /segment/history`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description           |
| ------------- | ------ | -------- | --------------------- |
| `CharacterID` | String | Yes      | UUID of the character |

**Request:**

```http
GET /segment/history?CharacterID=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryID": "story_uuid",
  "Segments": [
    {
      "ActiveSegmentID": "segment_uuid_1",
      "SegmentID": "segment_def_uuid_1",
      "SegmentType": "mechanical",
      "StartTime": "2025-01-15T14:25:00Z",
      "EndTime": "2025-01-15T14:30:00Z",
      "CompletedAt": "2025-01-15T14:30:00Z",
      "StoryTitle": "The Goblin's Ambush",
      "StoryInstanceID": "instance_uuid",
      "Outcome": "exceptional",
      "ClientEvents": [...],
      "CharacterUpdates": {...},
      "SkillXPAwarded": {"Stealth": 5, "Combat": 10},
      "AttributeXPAwarded": {"Agility": 2},
      "ChallengeResults": [...]
    },
    {
      "ActiveSegmentID": "segment_uuid_2",
      "SegmentID": "segment_def_uuid_2",
      "SegmentType": "decision",
      "StartTime": "2025-01-15T14:30:00Z",
      "EndTime": "2025-01-15T14:35:00Z",
      "CompletedAt": "2025-01-15T14:31:00Z",
      "StoryTitle": "The Goblin's Ambush",
      "StoryInstanceID": "instance_uuid",
      "Outcome": "normal",
      "Decision": "option_a",
      "ClientEvents": [...],
      "CharacterUpdates": {...}
    }
  ]
}
```

**Error Responses:**

| Status | Error Message           | Cause                         |
| ------ | ----------------------- | ----------------------------- |
| `403`  | "Access denied"         | Character not owned by player |
| `404`  | "Character not found"   | Character doesn't exist       |
| `401`  | "Unauthorized"          | Invalid or missing JWT token  |
| `500`  | "Internal server error" | Database or system failure    |

---

## Deployment Context

These API endpoints are part of the Eidolon Engine's 9-stack CDK deployment:

### Stack Dependencies

- **DynamoDB Stack**: Provides 14 tables with managed IAM policy
- **Lambda Stack**: Deploys all 16 Lambda functions with shared execution role
- **Player Stack**: Configures Cognito authorizer for API Gateway
- **Story Stack** (Incremental/Hybrid): Provides SQS queues and EventBridge
- **API Stack**: Creates API Gateway with Lambda integrations

### Post-Deployment Operations

- Lambda functions updated from S3 artifacts
- Layer versions managed with automatic cleanup
- Cognito trigger permissions configured for imported pools
- CORS configured via Lambda environment variables

---

### Character Rest

Initiates a rest segment for character healing.

**Endpoint:** `POST /segment/rest`

**Authentication:** Required

**Request:**

```http
POST /segment/rest HTTP/1.1
Authorization: Bearer <jwt-token>
Content-Type: application/json

{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Request Body:**

| Field         | Type   | Required | Description           |
| ------------- | ------ | -------- | --------------------- |
| `CharacterID` | String | Yes      | UUID of the character |

**Response:**

```json
{
  "Segment": {
    "ActiveSegmentID": "rest_segment_uuid",
    "SegmentType": "rest",
    "Status": "active",
    "StartTime": 1704900000,
    "EndTime": 1704903600,
    "HealingAmount": 2
  }
}
```

**Error Responses:**

| Status | Error Message                       | Cause                           |
| ------ | ----------------------------------- | ------------------------------- |
| `409`  | "Character is already in a segment" | Character has an active segment |
| `401`  | "Unauthorized"                      | Invalid or missing JWT token    |
| `500`  | "Internal server error"             | Database or system failure      |

## Environment Variables

All API Lambda functions receive these environment variables:

```python
# From lambda_stack.py
"APPLICATION_NAME": "eidolon-engine"
"LOG_LEVEL": "INFO"  # Validated by eidolon/environment.py
"ALLOWED_ORIGINS": "https://{client_host}.{domain}"
"CORS_ALLOW_CREDENTIALS": "true"
"CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,..."
"CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS"
"CORS_MAX_AGE": "86400"

# DynamoDB table names from stack outputs
"players_table": "players"
"characters_table": "characters"
"archetypes_table": "archetypes"
"story_table": "story"
"segments_table": "segments"
"active_segments_table": "active_segments"
# ... etc

# Function-specific (e.g., ops-segment-process)
"SEGMENT_BATCH_SIZE": "10"
"SEGMENT_QUEUE_URL": "https://sqs.{region}.amazonaws.com/{account}/eidolon-processing-queue"
```

## API Domain Configuration

The API is deployed at `api.{domain}` with:

- ACM certificate for HTTPS
- Route53 DNS record
- CloudFront distribution (optional)
- CORS preflight handled by API Gateway with wildcard
- Actual origin validation in Lambda functions

**Important:** The Flutter client receives the domain without protocol:

```python
# In client_stack.py
"API_DOMAIN": f"{api_host}.{domain}"  # Not the full URL
```

## Frequently Asked Questions

### System Performance

**Q: What are the actual performance targets?**
A: 10,000 total users, <5,000 concurrent users, 2,000-4,000 active stories typical, with capability to handle 3,000 concurrent story starts during peak scenarios.

**Q: Why is the system limited to North America?**  
A: Single region deployment (us-east-1) provides cost optimization and operational simplicity while maintaining acceptable latency (20-80ms) across North America.

### Client Implementation

**Q: How should clients handle network failures during polling?**
A: Use simple 30-second retry delays. Server-authoritative design means clients can always recover by requesting current state from server.

**Q: What happens if a player force-closes their app during a story?**
A: Stories continue server-side. Next `api-character-get` call automatically recovers GameMode state. No progress is lost.

### Technical Architecture

**Q: Why use polling instead of WebSockets for story updates?**
A: Story segments last 1-60 minutes, making real-time updates unnecessary. Polling is more battery-efficient, serverless-compatible, and fault-tolerant for this use case.
