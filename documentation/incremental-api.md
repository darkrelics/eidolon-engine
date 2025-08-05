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

**Endpoint:** `GET /archetypes`

**Authentication:** Required

**Request:**
```http
GET /archetypes HTTP/1.1
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

| Field | Type | Description |
|-------|------|-------------|
| `Archetypes` | Array | List of available player archetypes |
| `Count` | Integer | Total number of archetypes returned |

**Archetype Object:**

| Field | Type | Description |
|-------|------|-------------|
| `ArchetypeName` | String | Unique identifier and display name for the archetype |
| `Description` | String | Flavor text describing the archetype |
| `Attributes` | Object | Map of attribute names to their starting values |
| `Skills` | Object | Map of skill names to their starting values |
| `Health` | Integer | Starting maximum health points |
| `Essence` | Integer | Starting maximum essence (mana) points |
| `StartRoom` | Integer | Room ID where new characters of this archetype begin |
| `StartingItems` | Array | List of items the character starts with |
| `AvailableStories` | Array | List of story IDs available to this archetype |

**Starting Item Object:**

| Field | Type | Description |
|-------|------|-------------|
| `PrototypeID` | String | ID of the item prototype to create |
| `Slot` | String | Inventory slot where the item is placed |
| `IsWorn` | Boolean | Whether the item starts equipped |

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

| Status | Error Message | Cause |
|--------|---------------|-------|
| `500` | "Failed to load archetypes" | Database connection or query failure |
| `401` | "Unauthorized" | Invalid or missing JWT token |

---

### List Characters

Retrieves a list of all characters belonging to the authenticated player.

**Endpoint:** `GET /characters`

**Authentication:** Required

**Request:**
```http
GET /characters HTTP/1.1
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

| Field | Type | Description |
|-------|------|-------------|
| `Characters` | Array | List of characters owned by the player |

**Character Object:**

| Field | Type | Description |
|-------|------|-------------|
| `CharacterName` | String | Display name of the character |
| `CharacterID` | String | Unique identifier (UUID) for the character |
| `Dead` | Boolean | Whether the character has died |

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

| Status | Error Message | Cause |
|--------|---------------|-------|
| `404` | "Player not found" | Player ID exists in JWT but not in database |
| `401` | "Unauthorized" | Invalid or missing JWT token |
| `500` | "Internal server error" | Database connection or query failure |