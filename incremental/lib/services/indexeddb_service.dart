import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:idb_shim/idb_browser.dart';

/// Service for managing IndexedDB caching layer
///
/// Implements comprehensive client-side data caching using IndexedDB to minimize
/// server calls, improve performance, and enable rich gameplay features.
///
/// Database: EidolonDB v1
/// Object Stores:
/// - stories: Historical preservation of completed stories
/// - story_segments: Segment history storage
/// - characters: Primary character storage with cache metadata
/// - items: Item instance storage (ItemID + PrototypeID only)
/// - item_prototypes: Item template storage (full prototype data)
class IndexedDBService {
  static const String _dbName = 'EidolonDB';

  // Object store names
  static const String storeStories = 'stories';
  static const String storeStorySegments = 'story_segments';
  static const String storeCharacters = 'characters';
  static const String storeItems = 'items';
  static const String storeItemPrototypes = 'item_prototypes';

  Database? _db;
  final IdbFactory _idbFactory = getIdbFactory()!;

  static final IndexedDBService _instance = IndexedDBService._internal();
  factory IndexedDBService() => _instance;
  IndexedDBService._internal();

  /// Check if IndexedDB is supported in the current environment
  bool get isSupported => kIsWeb && getIdbFactory() != null;

  /// Initialize the IndexedDB database
  Future<void> initialize() async {
    if (!isSupported) {
      debugPrint('IndexedDB not supported in this environment');
      return;
    }

    try {
      _db = await _idbFactory.open(
        _dbName,
        version: 1,
        onUpgradeNeeded: _createStores,
      );
      debugPrint('IndexedDB initialized: $_dbName');
    } catch (e) {
      debugPrint('Failed to initialize IndexedDB: $e');
      // Database operations will fall back to server fetches
    }
  }

  /// Create all object stores on first open.
  void _createStores(VersionChangeEvent event) {
    final db = event.database;
    _createStoriesStore(db);
    _createStorySegmentsStore(db);
    _createCharactersStore(db);
    _createItemsStore(db);
    _createItemPrototypesStore(db);
  }

  /// Create stories object store for historical preservation
  void _createStoriesStore(Database db) {
    final store = db.createObjectStore(
      storeStories,
      keyPath: ['CharacterID', 'StoryInstanceID'],
    );

    // Indexes for efficient querying
    store.createIndex('characterId', 'CharacterID', unique: false);
    store.createIndex('completedAt', 'CompletedAt', unique: false);
    store.createIndex('outcome', 'Outcome', unique: false);
    store.createIndex('storyId', 'StoryID', unique: false);

    debugPrint('Created object store: $storeStories');
  }

  /// Create story segments object store for segment history
  void _createStorySegmentsStore(Database db) {
    final store = db.createObjectStore(
      storeStorySegments,
      keyPath: ['CharacterID', 'StoryInstanceID', 'ActiveSegmentID'],
    );

    // Indexes for efficient querying
    store.createIndex('storyInstance', [
      'CharacterID',
      'StoryInstanceID',
    ], unique: false);
    store.createIndex('segmentType', 'SegmentType', unique: false);
    store.createIndex('outcome', 'Outcome', unique: false);

    debugPrint('Created object store: $storeStorySegments');
  }

  /// Create characters object store for primary character storage
  void _createCharactersStore(Database db) {
    final store = db.createObjectStore(storeCharacters, keyPath: 'CharacterID');

    // Indexes for efficient querying
    store.createIndex('playerId', 'PlayerID', unique: false);
    store.createIndex('lastFetchedAt', 'LastFetchedAt', unique: false);

    debugPrint('Created object store: $storeCharacters');
  }

  /// Create items object store for item instance storage
  /// Stores only ItemID and PrototypeID for minimal storage
  void _createItemsStore(Database db) {
    final store = db.createObjectStore(storeItems, keyPath: 'ItemID');

    // Index for retrieving all items belonging to a character
    store.createIndex('characterId', 'CharacterID', unique: false);

    debugPrint('Created object store: $storeItems');
  }

  /// Create item prototypes object store for template storage
  /// Stores complete prototype definitions
  void _createItemPrototypesStore(Database db) {
    final store = db.createObjectStore(
      storeItemPrototypes,
      keyPath: 'PrototypeID',
    );

    // Index for cache invalidation strategies
    store.createIndex('lastFetchedAt', 'LastFetchedAt', unique: false);

    debugPrint('Created object store: $storeItemPrototypes');
  }

  /// Close the database connection
  Future<void> close() async {
    _db?.close();
    _db = null;
    debugPrint('IndexedDB closed');
  }

  /// Clear all data from the database (for testing/reset)
  Future<void> clearAll() async {
    if (_db == null || !isSupported) return;

    try {
      final transaction = _db!.transaction([
        storeStories,
        storeStorySegments,
        storeCharacters,
        storeItems,
        storeItemPrototypes,
      ], idbModeReadWrite);

      transaction.objectStore(storeStories).clear();
      transaction.objectStore(storeStorySegments).clear();
      transaction.objectStore(storeCharacters).clear();
      transaction.objectStore(storeItems).clear();
      transaction.objectStore(storeItemPrototypes).clear();

      await transaction.completed;
      debugPrint('Cleared all IndexedDB stores');
    } catch (e) {
      debugPrint('Failed to clear IndexedDB: $e');
    }
  }

  /// Get a reference to a specific object store
  ObjectStore _getStore(String storeName, String mode) {
    if (_db == null) {
      throw StateError('Database not initialized');
    }

    final transaction = _db!.transaction(storeName, mode);
    return transaction.objectStore(storeName);
  }

  // ============================================================================
  // CHARACTERS STORE OPERATIONS
  // ============================================================================

  /// Store character data in cache
  Future<void> putCharacter(Map<String, dynamic> character) async {
    if (_db == null || !isSupported) return;

    try {
      // Add cache metadata
      character['LastFetchedAt'] = DateTime.now().millisecondsSinceEpoch;

      final store = _getStore(storeCharacters, idbModeReadWrite);
      await store.put(character);
      debugPrint('Cached character: ${character['CharacterID']}');
    } catch (e) {
      debugPrint('Failed to cache character: $e');
    }
  }

  /// Get character from cache
  Future<Map<String, dynamic>?> getCharacter(String characterId) async {
    if (_db == null || !isSupported) return null;

    try {
      final store = _getStore(storeCharacters, idbModeReadOnly);
      final result = await store.getObject(characterId);
      return result as Map<String, dynamic>?;
    } catch (e) {
      debugPrint('Failed to get character from cache: $e');
      return null;
    }
  }

  /// Get all characters for a player
  Future<List<Map<String, dynamic>>> getPlayerCharacters(
    String playerId,
  ) async {
    if (_db == null || !isSupported) return [];

    try {
      final store = _getStore(storeCharacters, idbModeReadOnly);
      final index = store.index('playerId');
      final results = await index.getAll(playerId);

      return results.map((e) => e as Map<String, dynamic>).toList();
    } catch (e) {
      debugPrint('Failed to get player characters: $e');
      return [];
    }
  }

  /// Delete character from cache
  Future<void> deleteCharacter(String characterId) async {
    if (_db == null || !isSupported) return;

    try {
      final store = _getStore(storeCharacters, idbModeReadWrite);
      await store.delete(characterId);
      debugPrint('Deleted character from cache: $characterId');
    } catch (e) {
      debugPrint('Failed to delete character: $e');
    }
  }

  // ============================================================================
  // STORIES STORE OPERATIONS
  // ============================================================================

  /// Store completed story in cache
  Future<void> putStory(Map<String, dynamic> story) async {
    if (_db == null || !isSupported) return;

    try {
      final store = _getStore(storeStories, idbModeReadWrite);
      await store.put(story);
      debugPrint('Cached story: ${story['StoryInstanceID']}');
    } catch (e) {
      debugPrint('Failed to cache story: $e');
    }
  }

  /// Get all stories for a character
  Future<List<Map<String, dynamic>>> getCharacterStories(
    String characterId,
  ) async {
    if (_db == null || !isSupported) return [];

    try {
      final store = _getStore(storeStories, idbModeReadOnly);
      final index = store.index('characterId');
      final results = await index.getAll(characterId);

      return results.map((e) => e as Map<String, dynamic>).toList();
    } catch (e) {
      debugPrint('Failed to get character stories: $e');
      return [];
    }
  }

  // ============================================================================
  // STORY SEGMENTS STORE OPERATIONS
  // ============================================================================

  /// Store segment in cache
  Future<void> putSegment(Map<String, dynamic> segment) async {
    if (_db == null || !isSupported) return;

    try {
      final store = _getStore(storeStorySegments, idbModeReadWrite);
      await store.put(segment);
      debugPrint('Cached segment: ${segment['ActiveSegmentID']}');
    } catch (e) {
      debugPrint('Failed to cache segment: $e');
    }
  }

  /// Get all segments for a story instance
  Future<List<Map<String, dynamic>>> getStorySegments(
    String characterId,
    String storyInstanceId,
  ) async {
    if (_db == null || !isSupported) return [];

    try {
      final store = _getStore(storeStorySegments, idbModeReadOnly);
      final index = store.index('storyInstance');
      final results = await index.getAll([characterId, storyInstanceId]);

      return results.map((e) => e as Map<String, dynamic>).toList();
    } catch (e) {
      debugPrint('Failed to get story segments: $e');
      return [];
    }
  }

  // ============================================================================
  // ITEMS STORE OPERATIONS
  // ============================================================================

  /// Store item brief (ItemID + PrototypeID only)
  Future<void> putItemBrief(Map<String, dynamic> itemBrief) async {
    if (_db == null || !isSupported) return;

    try {
      final store = _getStore(storeItems, idbModeReadWrite);
      await store.put(itemBrief);
      debugPrint('Cached item brief: ${itemBrief['ItemID']}');
    } catch (e) {
      debugPrint('Failed to cache item brief: $e');
    }
  }

  /// Get item brief from cache
  Future<Map<String, dynamic>?> getItemBrief(String itemId) async {
    if (_db == null || !isSupported) return null;

    try {
      final store = _getStore(storeItems, idbModeReadOnly);
      final result = await store.getObject(itemId);
      return result as Map<String, dynamic>?;
    } catch (e) {
      debugPrint('Failed to get item brief: $e');
      return null;
    }
  }

  // ============================================================================
  // ITEM PROTOTYPES STORE OPERATIONS
  // ============================================================================

  /// Store item prototype
  Future<void> putItemPrototype(Map<String, dynamic> prototype) async {
    if (_db == null || !isSupported) return;

    try {
      // Add cache metadata
      prototype['LastFetchedAt'] = DateTime.now().millisecondsSinceEpoch;

      final store = _getStore(storeItemPrototypes, idbModeReadWrite);
      await store.put(prototype);
      debugPrint('Cached item prototype: ${prototype['PrototypeID']}');
    } catch (e) {
      debugPrint('Failed to cache item prototype: $e');
    }
  }

  /// Get item prototype from cache
  Future<Map<String, dynamic>?> getItemPrototype(String prototypeId) async {
    if (_db == null || !isSupported) return null;

    try {
      final store = _getStore(storeItemPrototypes, idbModeReadOnly);
      final result = await store.getObject(prototypeId);
      return result as Map<String, dynamic>?;
    } catch (e) {
      debugPrint('Failed to get item prototype: $e');
      return null;
    }
  }

  /// Check if item prototype exists in cache
  Future<bool> hasItemPrototype(String prototypeId) async {
    final prototype = await getItemPrototype(prototypeId);
    return prototype != null;
  }
}
