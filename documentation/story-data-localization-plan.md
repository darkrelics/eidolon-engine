# Incremental Client Data Re-Architecture  
**IndexedDB Cache Layer for Server-Authoritative Design**

## Strategic Overview

This document outlines a comprehensive re-architecture of the Incremental client's data layer, replacing SharedPreferences-based caching with IndexedDB to handle complex game data relationships while preserving server-authoritative design principles.

### Core Architectural Problems
1. **Inventory Complexity**: Container hierarchies, item relationships, equipment states cannot be efficiently managed with simple key-value caching (see [Inventory Complexity Analysis](inventory-complexity-analysis.md))
2. **Character Data Access Patterns**: 100+ API calls per hour for character updates creates expensive operational overhead  
3. **Story History Preservation**: Rich narrative experiences lost due to inadequate historical data access
4. **Cache Architecture Limitations**: SharedPreferences insufficient for relational data queries and complex state management

### Server-Authoritative Design Preservation
The IndexedDB implementation maintains server authority while adding intelligent caching:
- **Server Authority**: All calculations, progression, timing remain server-controlled
- **IndexedDB Role**: Intelligent cache layer with relational capabilities, not competing authority
- **Update Pattern**: Server provides authoritative updates, IndexedDB stores and organizes locally
- **Consistency Model**: Server state always wins, local state provides performance and UX enhancement

---

## Architectural Problem Analysis

### **1. Inventory Management Crisis**

**Current Implementation** (from `character.dart:17-18`):
```dart
final Map<String, String> inventory;        // slot -> itemId (UUID)
final Map<String, dynamic> inventoryDetails; // Enriched item data
```

**Fundamental Issues:**
- **Container Hierarchies**: Bags containing items containing items - impossible to efficiently traverse with flat maps
- **Item State Tracking**: Equipment status, quantities, locations, conditions require relational queries
- **UUID Resolution**: Every inventory display requires UUID → item details lookup
- **Performance**: Complex inventory operations require multiple API calls and complex client-side assembly

**Example Container Problem:**
```
Backpack (itemId: abc123)
  ├── Health Potions x5 (itemId: def456)
  ├── Scroll Case (itemId: ghi789)
  │   ├── Scroll of Fireball (itemId: jkl012)
  │   └── Scroll of Healing (itemId: mno345)
  └── Coin Purse (itemId: pqr678)
      └── 500 Gold Pieces (itemId: stu901)
```

Current SharedPreferences **cannot efficiently represent or query this structure**.

### **2. Character Data Access Pattern Inefficiency**

**Current API Usage** (from `game_screen.dart:157-161`):
```dart
final character = await retryWithBackoff(
  () => _rateLimiter.limiter.executeAutomated(
    GlobalRateLimiter.getCharacter,
    () => _apiService.getCharacterById(_characterInfo!.id),
  ),
);
```

**API Call Frequency Analysis:**
- **Character Panel Updates**: Every health/essence change
- **Polling Updates**: Every 60 seconds during active stories
- **Inventory Changes**: After every item interaction  
- **Story Progression**: After every segment completion

**Cost Analysis:**
```
Active Player: 100+ GET /character calls per hour
1,000 Active Players: 100,000+ API calls per hour
Operational Cost: ~$200-400/month just for character data
```

### **3. Story History User Experience Gap**

**Current Issues:**
- ❌ `story_history_widget.dart`: Mock data implementation (line 24)
- ❌ No access to completed story narratives
- ❌ Cannot review personal story journey
- ❌ Lost connection to player's progression story

**User Impact:**
- Players cannot revisit their favorite story moments
- No sense of character progression or journey
- Reduced emotional connection to character development

---

## Solution Architecture: IndexedDB Cache Layer

### Intelligent Caching with Server Authority Preserved

The IndexedDB re-architecture creates an **intelligent cache layer** that works with the server-authoritative design:

- **Server Authority Maintained**: All calculations, progression, and state transitions remain server-controlled
- **IndexedDB as Smart Cache**: Local storage handles complex data relationships and reduces API calls
- **Authoritative Update Pattern**: Server provides updates, IndexedDB organizes and persists them locally
- **Performance Enhancement**: 85-90% reduction in API calls while maintaining data consistency

### Three Data Domain Strategy

#### **Domain 1: Stories - Rich Historical Preservation**
**Purpose**: Enable players to review and connect with their narrative journey
**Pattern**: Accumulative historical data with rich querying capabilities
**Storage**: Complete story records with segments, narratives, and outcomes

#### **Domain 2: Character - Intelligent State Caching**  
**Purpose**: Eliminate redundant API calls while maintaining real-time accuracy
**Pattern**: Current state cache with smart field-level updates
**Storage**: Single character record per character (overwrite on server updates)

#### **Domain 3: Inventory - Complex Relationship Management**
**Purpose**: Support rich inventory UI features and container hierarchies
**Pattern**: Relational item storage with container traversal capabilities  
**Storage**: Item definitions, container relationships, equipment states

### Data Flow Architecture
```
Server Updates → IndexedDB Cache Layer → UI Components
     ↑                     ↓
     └─── Smart Invalidation ←──┘

Server: Authoritative calculations and state
IndexedDB: Intelligent organization and relationships  
UI: Instant access to organized data
```

---

## Technical Implementation

### Storage Technology: idb_shim v2.6.7

**IndexedDB via idb_shim package provides:**
- **Cross-Platform Consistency**: Identical API across Flutter web, desktop, mobile
- **Relational Capabilities**: Complex queries, indexes, and data relationships  
- **Transaction Support**: Atomic operations for data consistency
- **Testing Support**: In-memory database for comprehensive unit testing
- **Browser Compatibility**: Automatic handling of browser-specific limitations

```yaml
dependencies:
  idb_shim: ^2.6.7  # IndexedDB abstraction layer
```

### Database Schema: 'eidolon'

#### Database Structure - Three Data Domains
```dart
class GameDatabaseSchema {
  static const String DB_NAME = 'eidolon';
  static const int DB_VERSION = 1;
  
  static Future<Database> create(IdbFactory factory) async {
    return await factory.open(DB_NAME, version: DB_VERSION, 
      onUpgradeNeeded: (VersionChangeEvent e) {
        final db = e.database;
        
        // ===== STORIES: Historical Preservation =====
        
        // Completed stories with rich metadata
        final storiesStore = db.createObjectStore('stories', 
          keyPath: ['characterId', 'storyInstanceId']);
        storiesStore.createIndex('by-character', 'characterId');
        storiesStore.createIndex('by-completion-date', ['characterId', 'completedAt']);
        storiesStore.createIndex('by-outcome', ['characterId', 'finalOutcome']);
        storiesStore.createIndex('by-story-type', ['characterId', 'storyType']);
        
        // Story segments with full narrative data
        final segmentsStore = db.createObjectStore('story_segments',
          keyPath: ['characterId', 'storyInstanceId', 'activeSegmentId']);
        segmentsStore.createIndex('by-story-instance', ['characterId', 'storyInstanceId']);
        segmentsStore.createIndex('by-segment-type', ['characterId', 'segmentType']);
        segmentsStore.createIndex('by-outcome', ['characterId', 'outcome']);
        
        // ===== CHARACTER: Intelligent State Caching =====
        
        // Character data with timestamp tracking
        final charactersStore = db.createObjectStore('characters', keyPath: 'characterId');
        charactersStore.createIndex('by-last-updated', 'lastUpdated');
        
        // ===== INVENTORY: Complex Relationship Management =====
        
        // Item definitions cache
        final itemsStore = db.createObjectStore('items', keyPath: 'itemId');
        itemsStore.createIndex('by-type', 'type');
        itemsStore.createIndex('by-name', 'name');
        
        // Character inventory with relational data
        final inventoryStore = db.createObjectStore('character_inventory', 
          keyPath: ['characterId', 'slotId']);
        inventoryStore.createIndex('by-character', 'characterId');
        inventoryStore.createIndex('by-item-type', ['characterId', 'itemType']);
        inventoryStore.createIndex('by-equipped', ['characterId', 'isEquipped']);
        
        // Container contents tracking
        final containersStore = db.createObjectStore('container_contents',
          keyPath: ['characterId', 'containerId', 'itemId']);
        containersStore.createIndex('by-container', ['characterId', 'containerId']);
        containersStore.createIndex('by-item', ['characterId', 'itemId']);
      });
  }
}
```

### Required Server API Extensions

#### New Lambda Functions

**`api_story_history.py`** - `GET /story/history`:
```python
def lambda_handler(event: dict, context: object) -> dict:
    """Get completed story history from StoryHistory and SegmentHistory tables"""
    # Query existing server data and return formatted for client consumption
    
def get_story_history(character_id: str, limit: int = 20) -> dict:
    """Query StoryHistory + SegmentHistory tables"""
    # 1. Query StoryHistory table for completed stories
    # 2. For each story, query SegmentHistory table for segments  
    # 3. Return structured data for IndexedDB storage
```

**`api_item_get.py`** - `GET /item`:  
```python
def lambda_handler(event: dict, context: object) -> dict:
    """Get item details for inventory management"""
    # Bulk item lookup for efficient inventory operations
    
def get_bulk_item_details(item_ids: list[str]) -> dict:
    """Query items table for bulk item data"""
    # Support efficient container traversal and inventory display
```

### Implementation Activity Sequence

#### **Foundation Layer**

**1. IndexedDB Infrastructure**
**Dependencies**: None  
**Blocks**: All data operations

**Activities**:
- Add `idb_shim: ^2.6.7` to `pubspec.yaml`
- Create `GameDatabaseService` with schema for three data domains
- Implement database initialization and transaction management
- Add error handling for database operations
- Create testing infrastructure with memory database

**2. Data Service Layer**
**Dependencies**: IndexedDB Infrastructure  
**Blocks**: All domain-specific operations

**Activities**:
- Create `GameDataService` with domain-specific operations
- Implement story preservation methods
- Implement character caching methods  
- Implement inventory relationship management
- Add data validation and consistency checks

#### **Server API Extensions**

**3. Story History API**
**Dependencies**: None (uses existing DynamoDB tables)
**Blocks**: Story historical data access

**Activities**:
- Create `api_story_history.py` Lambda function
- Query `StoryHistory` and `SegmentHistory` tables
- Return structured data for IndexedDB storage
- Add to API Gateway with proper CORS and auth
- Follow existing Lambda deployment patterns

**4. Item Details API**  
**Dependencies**: None (uses existing DynamoDB tables)
**Blocks**: Inventory enrichment operations

**Activities**:
- Create `api_item_get.py` Lambda function
- Support bulk item UUID resolution
- Query existing `items` table efficiently
- Return formatted item data with container support
- Add to API Gateway following existing patterns

#### **Client Integration Layer**

**5. Replace CharacterProvider with IndexedDB**
**Dependencies**: Data Service Layer + APIs deployed
**Blocks**: Character panel performance improvements

**Activities**:
- Replace `CharacterProvider` SharedPreferences with IndexedDB caching
- Implement smart character update patterns (field-level changes)
- Add character data freshness checks and auto-refresh
- Maintain existing Provider pattern interfaces for compatibility
- Add proper error handling and fallback mechanisms

**6. Inventory System Re-Architecture**
**Dependencies**: Character Provider replacement + Item API
**Blocks**: Rich inventory features

**Activities**:
- Replace flat inventory maps with relational IndexedDB storage
- Implement container hierarchy traversal and management
- Add inventory filtering, searching, and sorting capabilities
- Build rich inventory UI features (equipment visualization, container navigation)
- Support complex inventory operations (item movement, container organization)

**7. Story History Implementation**
**Dependencies**: Story History API + Data Service Layer
**Blocks**: Narrative journey features

**Activities**:
- Replace mock data in `story_history_widget.dart` with IndexedDB queries
- Implement story completion preservation during gameplay
- Add completed story viewing with full segment details
- Enable story search, filtering, and personal curation features
- Build story analytics and pattern recognition

#### **UI Enhancement Layer**

**8. Natural Story Flow**
**Dependencies**: Story History Implementation
**Blocks**: Seamless story experience

**Activities**:
- Remove blocking completion dialogs
- Implement unified story selection (available + completed)
- Preserve story data throughout completion process
- Add natural story-to-story navigation flows
- Enable story comparison and recommendation features

**9. Advanced Inventory UI**
**Dependencies**: Inventory System Re-Architecture
**Blocks**: Rich inventory experience

**Activities**:
- Build container exploration interfaces
- Add inventory search and filtering UI
- Implement drag-and-drop item organization
- Add equipment comparison and optimization tools
- Enable inventory analytics and insights

#### **Optimization Layer**

**10. Performance Optimization**
**Dependencies**: All core features implemented
**Blocks**: Production deployment

**Activities**:
- Optimize database queries with proper indexing strategies
- Implement intelligent background sync and refresh patterns
- Add storage management and cleanup policies
- Build performance monitoring and alerting
- Optimize for offline operation and data consistency

---

## Server-Authoritative Data Strategy

### Intelligent Cache Layer Architecture

**Server Authority Preserved Through Update Patterns:**
- **Server calculates** all game mechanics, outcomes, and state transitions
- **Server provides authoritative updates** via existing API responses
- **IndexedDB receives and organizes** server updates for local query efficiency
- **UI accesses IndexedDB** for instant display without server round-trips

### Smart Update Strategies by Domain

#### **Stories: Completion-Triggered Preservation**
```dart
class StoryDataSync {
  // When story completes, preserve narrative before server clears it
  Future<void> onStoryCompleted(Character character) async {
    final storyState = character.storyState;
    if (storyState != null) {
      await gameDataService.preserveCompletedStory(
        characterId: character.id,
        storyState: storyState,
      );
    }
    
    // Background: Sync with server historical data
    _backgroundSyncStoryHistory(character.id);
  }
}
```

#### **Character: Change-Based Updates**
```dart
class CharacterDataSync {
  // Smart field-level updates instead of full character reloads
  Future<void> updateCharacterState(Character newCharacter) async {
    final cached = await gameDataService.getCachedCharacter(newCharacter.id);
    
    if (cached == null || _hasSignificantChanges(cached, newCharacter)) {
      // Store full update
      await gameDataService.cacheCharacterState(newCharacter);
    } else {
      // Incremental field updates for performance
      await gameDataService.updateCharacterFields(newCharacter.id, {
        'health': newCharacter.health,
        'essence': newCharacter.essence,
        'lastUpdated': newCharacter.lastUpdated.toIso8601String(),
      });
    }
  }
}
```

#### **Inventory: Relationship-Aware Caching**
```dart
class InventoryDataSync {
  // Process inventory changes with container relationship tracking
  Future<void> syncInventoryState(Character character) async {
    // Cache item definitions for UUID resolution
    final itemIds = character.inventory.values.toList();
    await gameDataService.cacheItemDefinitions(itemIds);
    
    // Update character inventory with container tracking
    await gameDataService.updateCharacterInventory(
      characterId: character.id,
      inventory: character.inventory,
      inventoryDetails: character.inventoryDetails,
    );
  }
}
```

### Performance Impact Analysis

#### **API Call Reduction**
```
Current Pattern:
- Character Panel: 60+ API calls/hour
- Inventory Display: 20+ API calls/hour  
- Story History: 5-10 API calls per view

IndexedDB Pattern:
- Character Panel: 5-10 API calls/hour (80-90% reduction)
- Inventory Display: 1-2 API calls/hour (90-95% reduction)
- Story History: 0 API calls after initial load (100% reduction)
```

#### **Operational Cost Benefits**
```
1,000 Active Players (Current):
- Character API calls: 60,000/hour
- Inventory API calls: 20,000/hour
- Estimated monthly cost: $800-1200

1,000 Active Players (IndexedDB):
- Character API calls: 8,000/hour
- Inventory API calls: 1,500/hour  
- Estimated monthly cost: $200-400

Cost Reduction: 65-75% operational savings
```

---

## Error Handling & Resilience

### IndexedDB Error Recovery with Server Fallback

```dart
class GameDataErrorHandling {
  // Three-tier fallback strategy for each data domain
  
  // Stories: IndexedDB → API → Empty (graceful degradation)
  Future<List<CompletedStoryInfo>> getStoriesWithFallback(String characterId) async {
    try {
      // Primary: IndexedDB cache
      final localStories = await gameDataService.getCompletedStories(characterId);
      if (localStories.isNotEmpty) return localStories;
    } catch (e) {
      debugPrint('IndexedDB story access failed: $e');
    }
    
    try {
      // Fallback: Server API
      final serverStories = await _apiService.getStoryHistory(characterId: characterId);
      
      // Background cache for next time
      _backgroundCacheStories(serverStories);
      
      return serverStories;
    } catch (e) {
      debugPrint('Server story access failed: $e');
      return []; // Graceful degradation
    }
  }
  
  // Character: IndexedDB → API → Previous cache (preserve state)
  Future<Character?> getCharacterWithFallback(String characterId) async {
    try {
      // Check IndexedDB freshness
      if (await gameDataService.isCharacterCacheFresh(characterId)) {
        return await gameDataService.getCachedCharacter(characterId);
      }
    } catch (e) {
      debugPrint('IndexedDB character access failed: $e');
    }
    
    try {
      // Get fresh from server and cache
      final character = await _apiService.getCharacterById(characterId);
      if (character != null) {
        _backgroundCacheCharacter(character);
      }
      return character;
    } catch (e) {
      // Last resort: return stale cache if available
      return await gameDataService.getCachedCharacter(characterId);
    }
  }
}
```

### Database Corruption Recovery

```dart
class IndexedDBRecovery {
  Future<void> handleDatabaseCorruption(String characterId) async {
    try {
      // Clear corrupted character data
      await gameDataService.clearCharacterCache(characterId);
      
      // Preserve stories if possible
      final stories = await gameDataService.getCompletedStories(characterId);
      
      // Reinitialize database
      await gameDataService.initialize();
      
      // Restore stories
      for (final story in stories) {
        await gameDataService.restoreStoryFromBackup(story);
      }
      
    } catch (e) {
      // Complete database reset as last resort
      await gameDataService.clearAllData();
      await gameDataService.initialize();
    }
  }
}
```

### Integration with Existing Patterns

**Preserve Existing Error Handling:**
- Use existing error types (`NotFoundException`, `ApiException`)
- Follow existing retry logic with `retryWithBackoff()`
- Use existing rate limiting with `GlobalRateLimiter`
- Maintain existing Provider notification patterns

---

## Conclusion

This comprehensive IndexedDB re-architecture addresses fundamental data management challenges in the Incremental client while preserving and enhancing the server-authoritative design.

### Architectural Justification
1. **Inventory Complexity**: Container hierarchies and item relationships require relational data management that SharedPreferences cannot provide
2. **Character Data Access Patterns**: 100+ API calls per hour per active player creates unsustainable operational costs
3. **Story Historical Preservation**: Rich narrative experiences require sophisticated data organization and offline access
4. **Cache Architecture Limitations**: Simple key-value caching inadequate for complex game data relationships

### Implementation Benefits

#### **User Experience Transformation**
- **Instant UI Responsiveness**: All panels load from local data without API delays
- **Rich Inventory Features**: Container exploration, item search, equipment optimization
- **Story Journey Preservation**: Complete narrative history with search and analytics
- **Offline Capability**: Core gameplay data available without network connectivity

#### **Operational Cost Reduction**
- **65-75% API call reduction** across all game data operations
- **$400-800/month savings** for 1,000 active players
- **Reduced server load** enables system scaling without proportional cost increases
- **Better resource utilization** through intelligent client-side data management

#### **Technical Architecture Benefits**
- **Server Authority Preserved**: All calculations and state transitions remain server-controlled
- **Enhanced Caching**: IndexedDB provides sophisticated data organization capabilities
- **Future Feature Foundation**: Enables rich analytics, personalization, and offline features
- **Maintainable Complexity**: Organized data relationships rather than hidden complexity in API calls

### Strategic Impact

This re-architecture transforms the Incremental client from a **simple server display layer** into an **intelligent game data curator** while maintaining the robust server-authoritative design that ensures game integrity.

The IndexedDB cache layer provides the foundation for rich gameplay features (inventory management, story analytics, character progression tracking) that would be impossible or prohibitively expensive with the current API-dependent architecture.

**The complexity investment in IndexedDB is justified by the fundamental architectural problems it solves and the rich user experiences it enables.**

---

**Document Version**: 3.0 (IndexedDB Re-Architecture)
**Last Updated**: 2025-01-15  
**Status**: Ready for Implementation - Comprehensive Data Layer Enhancement