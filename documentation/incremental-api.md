# Incremental Game API Documentation

## Overview

The Incremental Game API provides RESTful endpoints for the Eidolon Engine incremental game mode. All endpoints require authentication via AWS Cognito and return JSON responses with PascalCase keys.

## Authentication

All API endpoints require authentication using AWS Cognito JWT tokens. The token should be included in the `Authorization` header:

```
Authorization: Bearer <jwt-token>
```

## Common Response Formats

### Success Response

All successful responses return HTTP 200 with JSON data using PascalCase keys.

### Error Response

Error responses include an `Error` field with a descriptive message:

```json
{
  "Error": "Error description"
}
```

Common HTTP status codes:

- `401` - Unauthorized (invalid or missing JWT token)
- `404` - Resource not found
- `500` - Internal server error

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

1. **Caching:** The Lambda function caches archetypes at cold start to minimize database calls. The cache persists for the lifetime of the Lambda instance (typically 30 minutes to 2 hours).

2. **Filtering:** Only archetypes with `Player: true` in the database are returned, excluding NPC-only archetypes.

3. **Sorting:** Results are sorted alphabetically by `ArchetypeName` for consistent ordering.

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

1. **Data Source:** Character information is retrieved from the Player table's `CharacterList` field, providing a lightweight response without requiring multiple database queries.

2. **No Caching:** This endpoint always returns fresh data to ensure players see their current character list immediately after character creation or death.

3. **Minimal Data:** Only essential information for character selection is returned. Full character details are retrieved separately via the Get Character endpoint.

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

1. **Name Validation:** Character names must:
   - Be 3-32 characters long
   - Contain only letters, spaces, and hyphens
   - Not be in the restricted names bloom filter
   - Not already exist in the database

2. **Character Limit:** Players can create up to the configured maximum (default 10) characters.

3. **Archetype Resolution:**
   - If no archetype is specified, "default" is used
   - If an invalid archetype is specified, "default" is used with a log warning
   - Only player-available archetypes (`Player: true`) can be used

4. **Starting Items:** Based on the archetype's `StartingItems` configuration:
   - Items are created from prototypes and added to the character's inventory
   - The first container item becomes the primary container (e.g., backpack)
   - Worn items (`IsWorn: true`) are equipped automatically
   - Non-worn items are placed inside the primary container

5. **Initial State:** New characters start with:
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
        "itemId": "abc123-item-uuid",
        "name": "Leather Backpack",
        "description": "A sturdy leather backpack",
        "quantity": 1,
        "stackable": false,
        "equipped": true,
        "mass": 2,
        "value": 50
      },
      "1": {
        "itemId": "def456-item-uuid",
        "name": "Iron Sword",
        "description": "A well-crafted iron sword",
        "quantity": 1,
        "stackable": false,
        "equipped": false,
        "mass": 3,
        "value": 100
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
        "eventType": "narrative",
        "title": "Combat Begins",
        "description": "A goblin jumps out from the shadows!"
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

**InventoryDetails Structure:**

Maps inventory slot numbers to detailed item information:

```json
{
  "slotNumber": {
    "itemId": "UUID",
    "name": "Item Name",
    "description": "Item description",
    "quantity": 1,
    "stackable": false,
    "equipped": false,
    "mass": 1.5,
    "value": 100
  }
}
```

**Implementation Notes:**

1. **Character Ownership:** The Lambda validates that the requested character belongs to the authenticated player. Attempting to access another player's character returns 404.

2. **Response Field Behavior:** The response dynamically includes different fields based on the character's state:
   - **With active story:** Includes `ActiveStory` and `ActiveSegment` objects (if present), does NOT include `AvailableStories`
   - **Without active story:** Does NOT include `ActiveStory` or `ActiveSegment`, but includes `AvailableStories` array if any stories are available
   - Fields are completely omitted from the response rather than being set to null

3. **Available Stories:** When the character doesn't have an active story, the `AvailableStories` field is automatically populated with story details including availability status, cooldown information, prerequisites, and metadata. This eliminates the need for a separate API call to get available stories.

4. **Inventory Enrichment:** The `InventoryDetails` field provides full item information for UI display without requiring additional API calls. If item lookups fail, the character is still returned without enrichment.

5. **Health Calculation:** Current health is not stored but should be calculated as: `Health = MaxHealth - Wounds.length`

6. **Container Items:** Items stored inside containers (like backpacks) are not shown in the character's inventory. They exist in the container item's Contents array.

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

| Parameter     | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
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

Starts a new story for the specified character.

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

| Field         | Type   | Required | Description                         |
| ------------- | ------ | -------- | ----------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character               |
| `StoryID`     | String | Yes      | ID of the story to start            |

**Response:**

```json
{
  "Segment": {
    "ActiveSegmentID": "segment_uuid",
    "SegmentID": "segment_def_uuid",
    "SegmentType": "narrative",
    "Status": "active",
    "StartTime": 1704900000,
    "EndTime": 1704900300,
    "ClientEvents": [
      {
        "eventType": "narrative",
        "title": "Story Begins",
        "description": "Your journey starts here..."
      }
    ]
  }
}
```

**Error Responses:**

| Status | Error Message                     | Cause                              |
| ------ | --------------------------------- | ---------------------------------- |
| `403`  | "Story not available"             | Story not available to character   |
| `409`  | "Character is already in a story" | Character has an active story      |
| `401`  | "Unauthorized"                    | Invalid or missing JWT token       |
| `500`  | "Internal server error"           | Database or system failure         |

---

### Abandon Story

Abandons the current active story for a character.

**Endpoint:** `POST /story/abandon`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character             |

**Request:**

```http
POST /story/abandon?CharacterID=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Message": "Story abandoned successfully"
}
```

**Error Responses:**

| Status | Error Message           | Cause                          |
| ------ | ----------------------- | ------------------------------ |
| `400`  | "No active story found" | Character has no active story  |
| `401`  | "Unauthorized"          | Invalid or missing JWT token   |
| `500`  | "Internal server error" | Database or system failure     |

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

| Field         | Type   | Required | Description                         |
| ------------- | ------ | -------- | ----------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character               |
| `Decision`    | String | Yes      | Player's decision for the segment   |

**Response:**

```json
{
  "Message": "Decision submitted successfully"
}
```

**Error Responses:**

| Status | Error Message              | Cause                          |
| ------ | -------------------------- | ------------------------------ |
| `404`  | "Segment not found"        | No active segment found        |
| `409`  | "Decision already submitted" | Decision was already made     |
| `401`  | "Unauthorized"             | Invalid or missing JWT token   |
| `500`  | "Internal server error"    | Database or system failure     |

---

### Get Segment Outcome

Retrieves the outcome of a completed segment.

**Endpoint:** `GET /segment/outcome`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character             |
| `SegmentID`   | String | Yes      | UUID of the segment               |

**Request:**

```http
GET /segment/outcome?CharacterID=550e8400-e29b-41d4-a716-446655440000&SegmentID=segment_uuid HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Outcome": {
    "Result": "success",
    "Rewards": {
      "gold": 50,
      "experience": 100
    },
    "Consequences": {
      "wounds": 1
    },
    "NextSegment": "segment_next_uuid"
  }
}
```

**Error Responses:**

| Status | Error Message              | Cause                          |
| ------ | -------------------------- | ------------------------------ |
| `404`  | "Segment not found"        | Segment doesn't exist          |
| `409`  | "Segment not yet completed" | Segment is still processing    |
| `401`  | "Unauthorized"             | Invalid or missing JWT token   |
| `500`  | "Internal server error"    | Database or system failure     |

---

### Get Segment Status

Gets the current status of an active segment.

**Endpoint:** `GET /segment/status`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character             |

**Request:**

```http
GET /segment/status?CharacterID=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Status": "active",
  "TimeRemaining": 120,
  "DecisionSubmitted": false
}
```

**Error Responses:**

| Status | Error Message           | Cause                          |
| ------ | ----------------------- | ------------------------------ |
| `404`  | "No active segment found" | No active segment exists      |
| `401`  | "Unauthorized"          | Invalid or missing JWT token   |
| `500`  | "Internal server error" | Database or system failure     |

---

### Get Segment History

Retrieves historical segment data for a character.

**Endpoint:** `GET /segment/history`

**Authentication:** Required

**Query Parameters:**

| Parameter     | Type   | Required | Description                       |
| ------------- | ------ | -------- | --------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character             |

**Request:**

```http
GET /segment/history?CharacterID=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <jwt-token>
```

**Response:**

```json
{
  "Segments": [
    {
      "SegmentID": "segment_uuid_1",
      "CompletedAt": "2025-01-15T14:30:00Z",
      "Outcome": "success",
      "StoryID": "story_uuid"
    },
    {
      "SegmentID": "segment_uuid_2",
      "CompletedAt": "2025-01-15T14:35:00Z",
      "Outcome": "failure",
      "StoryID": "story_uuid"
    }
  ]
}
```

**Error Responses:**

| Status | Error Message           | Cause                          |
| ------ | ----------------------- | ------------------------------ |
| `404`  | "No history found"      | No segment history exists      |
| `401`  | "Unauthorized"          | Invalid or missing JWT token   |
| `500`  | "Internal server error" | Database or system failure     |

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

| Field         | Type   | Required | Description                         |
| ------------- | ------ | -------- | ----------------------------------- |
| `CharacterID` | String | Yes      | UUID of the character               |

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

| Status | Error Message                     | Cause                              |
| ------ | --------------------------------- | ---------------------------------- |
| `409`  | "Character is already in a segment" | Character has an active segment   |
| `401`  | "Unauthorized"                    | Invalid or missing JWT token       |
| `500`  | "Internal server error"           | Database or system failure         |
