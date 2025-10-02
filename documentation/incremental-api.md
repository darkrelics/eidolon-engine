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

### List Characters

Retrieves a list of all characters belonging to the authenticated player.

**Endpoint:** `GET /character/list`

**Authentication:** Required

**Response:**

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

**Response:**

```json
{
  "CharacterID": "7ba8c520-a5d2-4e8f-b3c1-9f2e3d4c5b6a",
  "CharacterName": "Gandalf",
  "Archetype": "Wizard",
  "Message": "Character created successfully"
}
```

### Get Character

Retrieves complete character data including active story and segment information.

**Endpoint:** `GET /character`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character to retrieve

**Response:**

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
    "CharState": "standing",
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

### Delete Character

Deletes a character belonging to the authenticated player.

**Endpoint:** `DELETE /character`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character to delete

**Response:**

```json
{
  "Message": "Character deleted successfully"
}
```

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

**Response:**

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

**Response:**

```json
{
  "CharacterID": "550e8400-e29b-41d4-a716-446655440000",
  "StoryID": "story_uuid",
  "Abandoned": true,
  "Message": "Story abandoned successfully"
}
```

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

**Response:**

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

### Get Segment Status

Gets the current status of an active segment, including timing information.

**Endpoint:** `GET /segment/status`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character

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
  "SegmentTitle": "Walking through the forest"
}
```

**Response (Completed Segment):**

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

### Get Segment History

Retrieves historical segment data for a character.

**Endpoint:** `GET /segment/history`

**Authentication:** Required

**Query Parameters:**

- `CharacterID` (required): UUID of the character

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
      "Outcome": "exceptional",
      "SkillXPAwarded": { "Stealth": 5, "Combat": 10 },
      "AttributeXPAwarded": { "Agility": 2 }
    }
  ]
}
```

## Client Cadence (Incremental mode)

- After `POST /story/start`, the client updates the UI with the first segment immediately.
- First `GET /segment/status` occurs 60 seconds after `StartTime`.
- If the segment is still unprocessed, the client calls `GET /segment/status` every 30 seconds until processed.
- At `EndTime`, the client calls `GET /character` to load the next segment or completion state.
- Only if segments fail to process are there additional status calls beyond the first.
