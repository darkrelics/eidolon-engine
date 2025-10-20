# Eidolon Engine API Documentation

## Overview

The Eidolon Engine API provides RESTful endpoints for both MUD and Incremental game modes. Deployed via API Gateway with Lambda integrations, all endpoints require authentication via AWS Cognito and return JSON responses with PascalCase keys.

## Authentication

All API endpoints require authentication using AWS Cognito JWT tokens from the `eidolon-users` User Pool. The token should be included in the `Authorization` header:

```
Authorization: Bearer <jwt-token>
```

## Common Response Formats

### Success Response

All successful responses return HTTP 200 with JSON data using PascalCase keys matching DynamoDB field names.

### Error Response Format

All error responses use this exact format:

```json
{
  "Error": "Descriptive error message"
}
```

**HTTP Status Codes:**

- `400` - Bad Request: Invalid parameters, malformed JSON, validation failures
- `401` - Unauthorized: Missing/invalid JWT token, authentication failures
- `403` - Forbidden: Valid auth but access denied (character not owned, story not available)
- `404` - Not Found: Resource doesn't exist (character, story, segment not found)
- `409` - Conflict: Resource state conflict (character busy, decision already made)
- `500` - Internal Server Error: Database failures, AWS service issues, unexpected errors

## Endpoints

### Get Archetypes

Retrieves all player-available archetypes for character creation.

**Endpoint:** `GET /archetype`

**Authentication:** Required

**Response (200 OK):**

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

**Error Responses:**

- `401 Unauthorized` - Missing or invalid authentication token
- `500 Internal Server Error` - Database operation failed

### List Characters

Retrieves a list of all characters belonging to the authenticated player.

**Endpoint:** `GET /character/list`

**Authentication:** Required

**Response (200 OK):**

```json
{
  "Characters": [
    {
      "CharacterName": "Aragorn",
      "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
      "Dead": false
    }
  ]
}
```

**Error Responses:**

- `401 Unauthorized` - Missing or invalid authentication token
- `500 Internal Server Error` - Database operation failed

### Add Character

Creates a new character for the authenticated player.

**Endpoint:** `POST /character`

**Authentication:** Required

**Request Body:**

```json
{
  "CharacterName": "Gandalf",
  "ArchetypeName": "Wizard"
}
```

**Response (200 OK):**

```json
{
  "CharacterID": "7ba8c520-a5d2-4e8f-b3c1-9f2e3d4c5b6a",
  "CharacterName": "Gandalf",
  "Archetype": "Wizard",
  "Message": "Character created successfully"
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterName or ArchetypeName, invalid archetype, name already exists
- `401 Unauthorized` - Missing or invalid authentication token
- `500 Internal Server Error` - Database operation failed

### Get Character

Retrieves complete character data including active story and segment information.

**Endpoint:** `GET /character`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character to retrieve

**Response (200 OK):**

```json
{
  "Character": {
    "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
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
      }
    },
    "Attributes": {
      "Strength": 8,
      "Agility": 5
    },
    "Skills": {
      "Melee": 10,
      "Parry": 8
    },
    "Essence": 3,
    "MaxHealth": 12,
    "Wounds": [],
    "Resources": {},
    "AvailableStories": ["story_1", "story_2"],
    "ActiveStoryID": "story_current_uuid",
    "ActiveSegmentID": "segment_current_uuid",
    "Archetype": "Knight",
    "MaxEssence": 3
  },
  "ActiveStory": {
    "StoryID": "story_current_uuid",
    "Title": "The Dark Tower",
    "Description": "Investigate the mysterious tower",
    "EstimatedDuration": 1800
  },
  "ActiveSegment": {
    "ActiveSegmentID": "segment_current_uuid",
    "SegmentType": "mechanical",
    "Status": "active",
    "StartTime": 1704900000,
    "EndTime": 1704900300,
    "Outcome": "normal"
  },
  "AvailableStories": [
    {
      "StoryID": "story_1",
      "Title": "The Goblin Ambush",
      "Description": "A band of goblins has been terrorizing the village",
      "Available": true,
      "Prerequisites": [],
      "EstimatedDuration": 900
    }
  ]
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID parameter
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Character not owned by authenticated player
- `404 Not Found` - Character does not exist
- `500 Internal Server Error` - Database operation failed

### Delete Character

Deletes a character belonging to the authenticated player.

**Endpoint:** `DELETE /character`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character to delete

**Response (200 OK):**

```json
{
  "Message": "Character deleted successfully"
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID parameter, invalid UUID format
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Character not owned by authenticated player
- `404 Not Found` - Character does not exist
- `500 Internal Server Error` - Database operation failed

### Start Story

Starts a new story for the specified character.

**Endpoint:** `POST /story/start`

**Authentication:** Required

**Request Body:**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryID": "story_knight_honor"
}
```

**Response (200 OK):**

```json
{
  "Success": true,
  "Segment": {
    "ActiveSegmentID": "segment_uuid",
    "SegmentType": "mechanical",
    "StartTime": "2024-01-10T12:00:00Z",
    "EndTime": "2024-01-10T12:05:00Z",
    "SegmentActivity": "Starting your adventure...",
    "Duration": 300,
    "ProcessingStatus": "pending"
  }
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID or StoryID, invalid UUID format, dead characters cannot start new stories
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Story not available to character (prerequisites not met), character not owned by player
- `409 Conflict` - Character already in an active story
- `500 Internal Server Error` - Database operation failed

### Abandon Story

Abandons the current active story for a character.

**Endpoint:** `POST /story/abandon`

**Authentication:** Required

**Request Body:**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (200 OK):**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryID": "story_uuid",
  "Abandoned": true,
  "Message": "Story abandoned successfully"
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID, invalid UUID format, no active story
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Character not owned by authenticated player
- `500 Internal Server Error` - Database operation failed

### Submit Segment Decision

Submits a player decision for the current active segment.

**Endpoint:** `POST /segment/decision`

**Authentication:** Required

**Request Body:**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "Decision": "fight"
}
```

**Response (200 OK):**

```json
{
  "Accepted": true,
  "NextSegmentTime": "2024-03-14T10:25:00Z",
  "NextSegment": {
    "ActiveSegmentID": "550e8400-e29b-41d4-a716-446655440001",
    "SegmentType": "mechanical",
    "SegmentActivity": "Fighting the goblin",
    "EndTime": "2024-03-14T10:25:00Z"
  }
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID or Decision, invalid decision value, no active segment
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Character not owned by authenticated player
- `409 Conflict` - Decision already made for this segment
- `500 Internal Server Error` - Database operation failed

### Get Segment Status

Gets the current status of an active segment, including timing information.

**Endpoint:** `GET /segment/status`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character

**Response (Active Segment - 200 OK):**

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
  "SegmentTitle": "Walking through the forest"
}
```

**Response (Completed Segment - 200 OK):**

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
  "Narrative": "You successfully navigate through the forest...",
  "Effects": {
    "Wounds": 0,
    "Items": ["item_health_potion"]
  },
  "NextSegmentID": "next-segment-uuid"
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID parameter
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Character not owned by authenticated player
- `404 Not Found` - No active segment found for character
- `500 Internal Server Error` - Database operation failed

### Get Story History

Retrieves story history entries for a character by story instance IDs.

**Endpoint:** `GET /story/history`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character
- `StoryInstanceIDs` (optional): Comma-separated list of story instance UUIDs (max 10)

**Alternative Request Body:**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryInstanceIDs": ["uuid1", "uuid2"]
}
```

**Response (200 OK):**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "Stories": [
    {
      "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
      "StoryInstanceID": "uuid1",
      "StoryID": "story_uuid",
      "StoryTitle": "The Goblin's Ambush",
      "StartedAt": 1705329900,
      "CompletedAt": 1705330800,
      "Outcome": "normal",
      "SegmentHistory": ["seg1", "seg2", "seg3"],
      "TotalSkillXP": { "Investigation": 15 },
      "TotalAttributeXP": { "Perception": 5 }
    }
  ],
  "Missing": ["uuid3"]
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID or invalid StoryInstanceID format
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Character not owned by authenticated player
- `500 Internal Server Error` - Database operation failed

### Get Segment History

Retrieves completed segment history for a character's active or most recent story.

**Endpoint:** `GET /segment/history`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character

**Response (200 OK):**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryID": "story_uuid",
  "Segments": [
    {
      "ActiveSegmentID": "segment_uuid_1",
      "SegmentID": "segment_def_uuid_1",
      "SegmentType": "mechanical",
      "SegmentTitle": "The Forest Path",
      "SegmentActivity": "Investigating the path",
      "StartTime": "2025-01-15T14:25:00Z",
      "EndTime": "2025-01-15T14:30:00Z",
      "CompletedAt": "2025-01-15T14:30:00Z",
      "StoryTitle": "The Goblin's Ambush",
      "StoryInstanceID": "instance_uuid",
      "Outcome": "exceptional",
      "ClientEvents": [],
      "CharacterUpdates": {},
      "SkillXPAwarded": { "Stealth": 5, "Combat": 10 },
      "AttributeXPAwarded": { "Agility": 2 },
      "ChallengeResults": [],
      "CombatState": {},
      "Decision": "fight"
    }
  ]
}
```

**Error Responses:**

- `400 Bad Request` - Missing CharacterID parameter
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - Character not owned by authenticated player
- `404 Not Found` - Character does not exist
- `500 Internal Server Error` - Database operation failed

### Get Item Brief

Retrieves lightweight item metadata for IndexedDB caching. Returns only ItemID and PrototypeID.

**Endpoint:** `GET /item/brief`

**Authentication:** Required

**Query Parameters:**

- `ItemID` (required): UUID of the item instance

**Response (200 OK):**

```json
{
  "ItemID": "550e8400-e29b-41d4-a716-446655440000",
  "PrototypeID": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}
```

**Error Responses:**

- `400 Bad Request` - Missing ItemID parameter, invalid UUID format
- `401 Unauthorized` - Missing or invalid authentication token
- `404 Not Found` - Item does not exist
- `500 Internal Server Error` - Database operation failed

### Get Item Prototype

Retrieves complete item prototype definition for client-side caching.

**Endpoint:** `GET /item/prototype`

**Authentication:** Required

**Query Parameters:**

- `PrototypeID` (required): UUID of the item prototype

**Response (200 OK):**

```json
{
  "PrototypeID": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "PrototypeName": "Iron Sword",
  "Description": "A well-crafted iron sword with a leather-wrapped hilt.",
  "Mass": 3.5,
  "Value": 150,
  "Stackable": false,
  "MaxStack": 1,
  "Quantity": 1,
  "Wearable": true,
  "WornOn": ["right_hand", "left_hand"],
  "Verbs": {
    "examine": "You examine the iron sword closely.",
    "swing": "You swing the sword through the air."
  },
  "Overrides": {},
  "TraitMods": {
    "Melee": 1.0,
    "Damage": 3
  },
  "Container": false,
  "Contents": [],
  "IsWorn": false,
  "CanPickUp": true,
  "Metadata": {
    "WeaponType": "sword",
    "DamageType": "lethal"
  }
}
```

**Error Responses:**

- `400 Bad Request` - Missing PrototypeID parameter, invalid UUID format
- `401 Unauthorized` - Missing or invalid authentication token
- `404 Not Found` - Prototype does not exist
- `500 Internal Server Error` - Database operation failed

### Stack Operations (Future)

These endpoints will manage stackable item operations when implemented:

**Stack Merging:** Automatic during inventory updates
- When picking up stackable items, system automatically merges with existing stacks
- Uses UUIDv7 comparison - older stack keeps its ItemID
- Updates Quantity field on the surviving stack

**Stack Splitting (Planned):** `POST /item/split`
- Split a stack into two separate stacks
- Required for trade, dropping partial stacks
- Body: `{"ItemID": "uuid", "Quantity": 50}`
- Returns: New stack ItemID

**Inventory Consolidation (Planned):** `POST /inventory/consolidate`
- Merges all matching stackable items in inventory
- Reduces inventory slots used
- Returns: Updated inventory with consolidated stacks

**Stack Rules:**
- Stackable items: Immutable except for Quantity field
- Non-stackable items: Mutable, no Quantity field
- Stack merging: Oldest ItemID (UUIDv7) wins
- All coins are stackable with unlimited stack size

## Client Polling Pattern (Incremental mode)

The designed polling pattern (from backend constants):

1. **After `POST /story/start`**: Client displays first segment immediately
2. **Initial Delay**: Wait 60 seconds after `StartTime` before first poll (INITIAL_POLL_DELAY)
3. **First Status Check**: `GET /segment/status` at T+60 seconds
4. **Server-Guided Polling**: Uses `PollAfter` field from response for subsequent checks
5. **Processing States**:
   - If `ProcessingStatus="pending"`: Wait until `PollAfter` time, then poll again
   - If `ProcessingStatus="processed"` with `TimeRemaining > 0`: Wait for timer to expire
   - If `ProcessingStatus="processed"` with `TimeRemaining = 0`: Segment complete
6. **Incremental Updates**: When segment completes, apply `CharacterUpdates` from segment response to local cache via CharacterRepository
7. **Story Completion**: When `ActiveSegmentID` becomes null, fetch fresh character from server
8. **No Periodic Character Fetches**: Character only fetched at selection and story completion

**Current Implementation Note:**
- Flutter client currently polls immediately (T+0), not T+60
- This is inconsistent with backend INITIAL_POLL_DELAY constant
- Single polling source in GameScreen (no dual-polling)
- Respects server PollAfter guidance for subsequent polls
- Uses incremental character updates (not full reloads between segments)
- Falls back to full character fetch on error
