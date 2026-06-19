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
  }) : _apiService = apiService,
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

      debugPrint(
        'ItemRepository: Enriched item $itemId with prototype $prototypeId',
      );
      return enrichedItem;
    } catch (e) {
      debugPrint('ItemRepository: Error enriching item $itemId: $e');
      rethrow;
    }
  }

  /// Load enriched details for every item reachable from a set of root IDs.
  ///
  /// Pass the character's top-level Contents list (or any container's). The
  /// returned map is keyed by ItemID and includes items nested inside any
  /// container (recursively via the brief's Contents list).
  ///
  /// Each enriched entry merges prototype fields with the instance brief
  /// (ItemID, PrototypeID, Quantity, Container, Contents, IsWorn).
  Future<Map<String, Map<String, dynamic>>> loadInventoryDetails(
    List<String> rootItemIds,
  ) async {
    if (rootItemIds.isEmpty) {
      return {};
    }

    debugPrint(
      'ItemRepository: Loading inventory details for ${rootItemIds.length} root items',
    );

    try {
      final seedIds = rootItemIds.where((id) => id.isNotEmpty).toSet();
      if (seedIds.isEmpty) {
        return {};
      }

      // BFS: fetch briefs level by level, queueing Contents items for the next
      // pass. Keeps fetches parallel within each level.
      final briefsById = <String, Map<String, dynamic>>{};
      var frontier = seedIds;
      while (frontier.isNotEmpty) {
        final pending = frontier
            .where((id) => !briefsById.containsKey(id))
            .toList();
        if (pending.isEmpty) {
          break;
        }
        final fetched = await Future.wait(pending.map(_getItemBrief));
        final next = <String>{};
        for (var i = 0; i < pending.length; i++) {
          final brief = fetched[i];
          briefsById[pending[i]] = brief;
          final contents = brief['Contents'];
          if (contents is List) {
            for (final childId in contents) {
              if (childId is String && !briefsById.containsKey(childId)) {
                next.add(childId);
              }
            }
          }
        }
        frontier = next;
      }

      // Pre-fetch every unique prototype in parallel so per-item merges hit cache.
      final prototypeIds = <String>{};
      for (final brief in briefsById.values) {
        final prototypeId = brief['PrototypeID'] as String?;
        if (prototypeId != null) {
          prototypeIds.add(prototypeId);
        }
      }
      debugPrint(
        'ItemRepository: Found ${prototypeIds.length} unique prototypes',
      );
      await Future.wait(prototypeIds.map(_getPrototype));

      final enriched = <String, Map<String, dynamic>>{};
      for (final entry in briefsById.entries) {
        final brief = entry.value;
        final prototypeId = brief['PrototypeID'] as String?;
        if (prototypeId == null) {
          continue;
        }
        final prototype = await _getPrototype(prototypeId);
        enriched[entry.key] = {...prototype, ...brief};
      }

      debugPrint('ItemRepository: Loaded ${enriched.length} enriched items');
      return enriched;
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
          debugPrint(
            'ItemRepository: Item brief $itemId found in IndexedDB cache',
          );
          return cached;
        }
      } catch (e) {
        debugPrint(
          'ItemRepository: IndexedDB read failed for item $itemId: $e',
        );
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
      debugPrint(
        'ItemRepository: Prototype $prototypeId found in memory cache',
      );
      return _prototypeMemoryCache[prototypeId]!;
    }

    // Try IndexedDB cache (fast)
    if (_indexedDB.isSupported) {
      try {
        final cached = await _indexedDB.getItemPrototype(prototypeId);
        if (cached != null) {
          debugPrint(
            'ItemRepository: Prototype $prototypeId found in IndexedDB cache',
          );
          // Store in memory cache for next time
          _prototypeMemoryCache[prototypeId] = cached;
          return cached;
        }
      } catch (e) {
        debugPrint(
          'ItemRepository: IndexedDB read failed for prototype $prototypeId: $e',
        );
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
          debugPrint(
            'ItemRepository: Cached prototype $prototypeId in IndexedDB',
          );
        } catch (e) {
          debugPrint(
            'ItemRepository: Failed to cache prototype in IndexedDB: $e',
          );
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
