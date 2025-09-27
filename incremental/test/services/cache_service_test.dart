import 'package:flutter_test/flutter_test.dart';
import 'package:eidolon_incremental/services/cache_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('CacheService Tests', () {
    late CacheService cacheService;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      cacheService = CacheService();
      await cacheService.initialize();
    });

    tearDown(() async {
      await cacheService.clear();
    });

    test('set and get simple value', () async {
      const key = 'test_key';
      const value = 'test_value';

      await cacheService.set(key, value);
      final retrieved = cacheService.get<String>(key);

      expect(retrieved, equals(value));
    });

    test('set and get complex object', () async {
      const key = 'complex_key';
      final value = {
        'name': 'Test',
        'level': 5,
        'items': ['sword', 'shield'],
      };

      await cacheService.set(key, value);
      final retrieved = cacheService.get<Map<String, dynamic>>(key);

      expect(retrieved, equals(value));
    });

    test('cache expiration with TTL', () async {
      const key = 'expiring_key';
      const value = 'expires_soon';

      await cacheService.set(
        key,
        value,
        ttl: const Duration(milliseconds: 100),
      );

      // Should exist immediately
      expect(cacheService.has(key), isTrue);

      // Wait for expiration
      await Future.delayed(const Duration(milliseconds: 150));

      // Should be expired
      expect(cacheService.has(key), isFalse);
    });

    test('cache with maxAge validation', () async {
      const key = 'age_key';
      const value = 'age_test';

      await cacheService.set(key, value);

      // Should be valid with longer maxAge
      expect(
        cacheService.get<String>(key, maxAge: const Duration(hours: 1)),
        equals(value),
      );

      // Should be invalid with very short maxAge
      await Future.delayed(const Duration(milliseconds: 10));
      expect(
        cacheService.get<String>(key, maxAge: const Duration(milliseconds: 5)),
        isNull,
      );
    });

    test('remove specific key', () async {
      const key = 'remove_key';
      const value = 'to_remove';

      await cacheService.set(key, value);
      expect(cacheService.has(key), isTrue);

      await cacheService.remove(key);
      expect(cacheService.has(key), isFalse);
    });

    test('clear all cache', () async {
      await cacheService.set('key1', 'value1');
      await cacheService.set('key2', 'value2');
      await cacheService.set('key3', 'value3');

      expect(cacheService.has('key1'), isTrue);
      expect(cacheService.has('key2'), isTrue);
      expect(cacheService.has('key3'), isTrue);

      await cacheService.clear();

      expect(cacheService.has('key1'), isFalse);
      expect(cacheService.has('key2'), isFalse);
      expect(cacheService.has('key3'), isFalse);
    });

    test('memory cache is faster than persistent cache', () async {
      const key = 'perf_key';
      const value = 'performance_test';

      await cacheService.set(key, value);

      // First get should populate memory cache
      final stopwatch1 = Stopwatch()..start();
      cacheService.get<String>(key);
      stopwatch1.stop();

      // Second get should be from memory cache (faster)
      final stopwatch2 = Stopwatch()..start();
      cacheService.get<String>(key);
      stopwatch2.stop();

      // Memory cache should be faster or equal
      expect(
        stopwatch2.elapsedMicroseconds <= stopwatch1.elapsedMicroseconds,
        isTrue,
      );
    });
  });

  group('CachedData Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      final cache = CacheService();
      await cache.initialize();
    });

    test('fetches data on cache miss', () async {
      int fetchCount = 0;
      final cachedData = CachedData<String>(
        key: 'cached_data_key',
        fetcher: () async {
          fetchCount++;
          return 'fetched_value_$fetchCount';
        },
      );

      final result = await cachedData.get();
      expect(result, equals('fetched_value_1'));
      expect(fetchCount, equals(1));
    });

    test('returns cached data on subsequent calls', () async {
      int fetchCount = 0;
      final cachedData = CachedData<String>(
        key: 'cached_data_key2',
        fetcher: () async {
          fetchCount++;
          return 'fetched_value_$fetchCount';
        },
      );

      final result1 = await cachedData.get();
      final result2 = await cachedData.get();

      expect(result1, equals('fetched_value_1'));
      expect(result2, equals('fetched_value_1'));
      expect(fetchCount, equals(1)); // Only fetched once
    });

    test('force refresh bypasses cache', () async {
      int fetchCount = 0;
      final cachedData = CachedData<String>(
        key: 'cached_data_key3',
        fetcher: () async {
          fetchCount++;
          return 'fetched_value_$fetchCount';
        },
      );

      final result1 = await cachedData.get();
      final result2 = await cachedData.get(forceRefresh: true);

      expect(result1, equals('fetched_value_1'));
      expect(result2, equals('fetched_value_2'));
      expect(fetchCount, equals(2));
    });

    test('invalidate clears cached data', () async {
      int fetchCount = 0;
      final cachedData = CachedData<String>(
        key: 'cached_data_key4',
        fetcher: () async {
          fetchCount++;
          return 'fetched_value_$fetchCount';
        },
      );

      await cachedData.get();
      cachedData.invalidate();
      await cachedData.get();

      expect(fetchCount, equals(2)); // Fetched twice due to invalidation
    });
  });
}
