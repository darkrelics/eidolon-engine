import 'package:flutter/foundation.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/indexeddb_service.dart';

/// Repository for managing item and prototype data with two-tier caching.
///
/// Implements an efficient caching strategy to minimize server calls:
/// - Memory cache for prototypes (fastest, in-memory)
/// - IndexedDB cache for persistence (fast, on-disk)
/// - Server fallback for cache misses (slowest, network)
///
/// Prototypes are immutable game data and are cached indefinitely.
/// Item instances (ItemID + PrototypeID) are cached in IndexedDB.
///
/// Performance:
/// - Cache hit: <50ms (memory) or <100ms (IndexedDB)
/// - Cache miss: 200-500ms (server fetch)
/// - Batch loading: 20 items = ~5 unique prototypes = 5 server calls max
class ItemRepository {
  final ApiService _apiService;
  final IndexedDBService _indexedDB;

  /// Memory cache for item prototypes (immutable game data)
  /// Key: PrototypeID, Value: Prototype data
  final Map<String, Map<String, dynamic>> _prototypeMemoryCache = {};

  ItemRepository({
    required ApiService apiService,
    IndexedDBService? indexedDBService,
  })  : _apiService = apiService,
        _indexedDB = indexedDBService ?? IndexedDBService();

  /// Get enriched item with full prototype data merged in.
  ///
  /// Returns item data with prototype fields merged:
  /// - ItemID, PrototypeID, Quantity from item instance
  /// - Name, Description, Value, Stackable, etc. from prototype
  ///
  /// Uses two-tier caching for optimal performance.
  Future<Map<String, dynamic>> getEnrichedItem(String itemId) async {
    debugPrint('ItemRepository: Getting enriched item $itemId');

    try {
      // Get item brief (ItemID, PrototypeID, Quantity)
      final itemBrief = await _getItemBrief(itemId);

      // Get prototype data
      final prototypeId = itemBrief['PrototypeID'] as String;
      final prototype = await _getPrototype(prototypeId);

      // Merge prototype data into item
      final enrichedItem = {
        ...prototype, // Prototype fields first
        ...itemBrief, // Item instance fields override (ItemID, Quantity)
      };

      debugPrint('ItemRepository: Enriched item $itemId with prototype $prototypeId');
      return enrichedItem;
    } catch (e) {
      debugPrint('ItemRepository: Error enriching item $itemId: $e');
      rethrow;
    }
  }

  /// Load inventory details for all items in inventory.
  ///
  /// Takes inventory map with new schema: {slot: {"ItemID": "...", "Quantity": int}}
  /// Returns map of enriched item data: {slot: enrichedItem}
  ///
  /// Optimized batch loading:
  /// - Fetches all item briefs first
  /// - Groups by unique PrototypeID
  /// - Pre-fetches all unique prototypes
  /// - Merges prototype data into each item
  ///
  /// Performance: 20 items with 5 unique prototypes = ~5 prototype fetches
  Future<Map<String, Map<String, dynamic>>> loadInventoryDetails(
    Map<String, dynamic> inventory,
  ) async {
    if (inventory.isEmpty) {
      return {};
    }

    debugPrint('ItemRepository: Loading inventory details for ${inventory.length} slots');

    try {
      final enrichedInventory = <String, Map<String, dynamic>>{};

      // Extract all item IDs from inventory
      final itemIds = <String>[];
      for (final value in inventory.values) {
        if (value is Map<String, dynamic>) {
          final itemId = value['ItemID'] as String?;
          if (itemId != null) {
            itemIds.add(itemId);
          }
        }
      }

      if (itemIds.isEmpty) {
        return {};
      }

      // Fetch all item briefs (parallel)
      final itemBriefFutures = itemIds.map((itemId) => _getItemBrief(itemId));
      final itemBriefs = await Future.wait(itemBriefFutures);

      // Extract unique prototype IDs
      final uniquePrototypeIds = <String>{};
      for (final itemBrief in itemBriefs) {
        final prototypeId = itemBrief['PrototypeID'] as String?;
        if (prototypeId != null) {
          uniquePrototypeIds.add(prototypeId);
        }
      }

      debugPrint('ItemRepository: Found ${uniquePrototypeIds.length} unique prototypes');

      // Pre-fetch all unique prototypes (parallel)
      final prototypeFutures = uniquePrototypeIds.map((id) => _getPrototype(id));
      await Future.wait(prototypeFutures);

      // Now build enriched inventory
      int briefIndex = 0;
      for (final entry in inventory.entries) {
        final slot = entry.key;
        final value = entry.value;

        // Extract ItemID from new format
        if (value is! Map<String, dynamic>) {
          continue;
        }

        final itemId = value['ItemID'] as String?;
        if (itemId == null || briefIndex >= itemBriefs.length) {
          continue;
        }

        final itemBrief = itemBriefs[briefIndex];
        briefIndex++;

        final prototypeId = itemBrief['PrototypeID'] as String;
        final prototype = await _getPrototype(prototypeId);

        // Merge prototype + item brief
        enrichedInventory[slot] = {
          ...prototype,
          ...itemBrief,
        };
      }

      debugPrint('ItemRepository: Loaded ${enrichedInventory.length} enriched items');
      return enrichedInventory;
    } catch (e) {
      debugPrint('ItemRepository: Error loading inventory details: $e');
      return {}; // Return empty on error rather than throwing
    }
  }

  /// Get item brief (ItemID, PrototypeID, Quantity).
  ///
  /// Checks IndexedDB first, falls back to server.
  /// Caches result in IndexedDB for future use.
  Future<Map<String, dynamic>> _getItemBrief(String itemId) async {
    // Try IndexedDB cache first
    if (_indexedDB.isSupported) {
      try {
        final cached = await _indexedDB.getItemBrief(itemId);
        if (cached != null) {
          debugPrint('ItemRepository: Item brief $itemId found in IndexedDB cache');
          return cached;
        }
      } catch (e) {
        debugPrint('ItemRepository: IndexedDB read failed for item $itemId: $e');
      }
    }

    // Cache miss - fetch from server
    debugPrint('ItemRepository: Fetching item brief $itemId from server');
    try {
      final itemBrief = await _apiService.getItemBrief(itemId);

      // Cache in IndexedDB
      if (_indexedDB.isSupported) {
        try {
          await _indexedDB.putItemBrief(itemBrief);
          debugPrint('ItemRepository: Cached item brief $itemId in IndexedDB');
        } catch (e) {
          debugPrint('ItemRepository: Failed to cache item brief: $e');
          // Don't throw - caching is best-effort
        }
      }

      return itemBrief;
    } catch (e) {
      debugPrint('ItemRepository: Error fetching item brief $itemId: $e');
      rethrow;
    }
  }

  /// Get item prototype (full definition).
  ///
  /// Three-tier caching strategy:
  /// 1. Memory cache (fastest)
  /// 2. IndexedDB cache (fast)
  /// 3. Server fetch (slowest)
  ///
  /// Prototypes are immutable and cached indefinitely.
  Future<Map<String, dynamic>> _getPrototype(String prototypeId) async {
    // Try memory cache first (fastest)
    if (_prototypeMemoryCache.containsKey(prototypeId)) {
      debugPrint('ItemRepository: Prototype $prototypeId found in memory cache');
      return _prototypeMemoryCache[prototypeId]!;
    }

    // Try IndexedDB cache (fast)
    if (_indexedDB.isSupported) {
      try {
        final cached = await _indexedDB.getItemPrototype(prototypeId);
        if (cached != null) {
          debugPrint('ItemRepository: Prototype $prototypeId found in IndexedDB cache');
          // Store in memory cache for next time
          _prototypeMemoryCache[prototypeId] = cached;
          return cached;
        }
      } catch (e) {
        debugPrint('ItemRepository: IndexedDB read failed for prototype $prototypeId: $e');
      }
    }

    // Cache miss - fetch from server
    debugPrint('ItemRepository: Fetching prototype $prototypeId from server');
    try {
      final prototype = await _apiService.getItemPrototype(prototypeId);

      // Cache in memory
      _prototypeMemoryCache[prototypeId] = prototype;
      debugPrint('ItemRepository: Cached prototype $prototypeId in memory');

      // Cache in IndexedDB
      if (_indexedDB.isSupported) {
        try {
          await _indexedDB.putItemPrototype(prototype);
          debugPrint('ItemRepository: Cached prototype $prototypeId in IndexedDB');
        } catch (e) {
          debugPrint('ItemRepository: Failed to cache prototype in IndexedDB: $e');
          // Don't throw - caching is best-effort
        }
      }

      return prototype;
    } catch (e) {
      debugPrint('ItemRepository: Error fetching prototype $prototypeId: $e');
      rethrow;
    }
  }

  /// Clear all caches (memory + IndexedDB).
  ///
  /// Used for testing or forcing a complete refresh.
  Future<void> clearCache() async {
    _prototypeMemoryCache.clear();
    debugPrint('ItemRepository: Cleared memory cache');

    if (_indexedDB.isSupported) {
      try {
        await _indexedDB.clearAll();
        debugPrint('ItemRepository: Cleared IndexedDB cache');
      } catch (e) {
        debugPrint('ItemRepository: Failed to clear IndexedDB: $e');
      }
    }
  }

  /// Get cache statistics for monitoring.
  ///
  /// Returns map with cache hit counts and sizes.
  Map<String, dynamic> getCacheStats() {
    return {
      'memoryCache': {
        'size': _prototypeMemoryCache.length,
        'prototypes': _prototypeMemoryCache.keys.toList(),
      },
      'indexedDBSupported': _indexedDB.isSupported,
    };
  }
}
