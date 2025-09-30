import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Service for caching data locally
class CacheService {
  static const String _cachePrefix = 'cache_';
  static const String _timestampPrefix = 'cache_ts_';
  static const Duration _defaultTTL = Duration(minutes: 5);
  static const Duration _defaultCleanupThreshold = Duration(hours: 24);

  late SharedPreferences _prefs;
  final Map<String, dynamic> _memoryCache = {};
  final Map<String, DateTime> _memoryCacheTimestamps = {};

  /// Configurable cleanup threshold for expired cache entries
  Duration _cleanupThreshold = _defaultCleanupThreshold;

  static final CacheService _instance = CacheService._internal();
  factory CacheService() => _instance;
  CacheService._internal();

  Future<void> initialize() async {
    _prefs = await SharedPreferences.getInstance();
    await _cleanExpiredCache();
  }

  /// Set the cleanup threshold for expired cache entries
  void setCleanupThreshold(Duration threshold) {
    _cleanupThreshold = threshold;
  }

  /// Get the current cleanup threshold
  Duration get cleanupThreshold => _cleanupThreshold;

  /// Store data in cache with optional TTL
  Future<void> set(
    String key,
    dynamic value, {
    Duration ttl = _defaultTTL,
  }) async {
    final cacheKey = '$_cachePrefix$key';
    final timestampKey = '$_timestampPrefix$key';
    final now = DateTime.now();

    try {
      // Store in memory cache
      _memoryCache[key] = value;
      _memoryCacheTimestamps[key] = now;

      // Store in persistent cache
      final jsonString = jsonEncode(value);
      await _prefs.setString(cacheKey, jsonString);
      await _prefs.setString(timestampKey, now.toIso8601String());

      // Schedule cleanup
      if (ttl != Duration.zero) {
        Timer(ttl, () => remove(key));
      }
    } catch (e) {
      debugPrint('Cache set error: $e');
    }
  }

  /// Get data from cache
  T? get<T>(String key, {Duration? maxAge}) {
    // Check memory cache first
    if (_memoryCache.containsKey(key)) {
      final timestamp = _memoryCacheTimestamps[key];
      if (timestamp != null && _isValid(timestamp, maxAge)) {
        return _memoryCache[key] as T?;
      }
    }

    // Check persistent cache
    final cacheKey = '$_cachePrefix$key';
    final timestampKey = '$_timestampPrefix$key';

    final jsonString = _prefs.getString(cacheKey);
    final timestampString = _prefs.getString(timestampKey);

    if (jsonString != null && timestampString != null) {
      final timestamp = DateTime.parse(timestampString);

      if (_isValid(timestamp, maxAge)) {
        try {
          final value = jsonDecode(jsonString);
          // Update memory cache
          _memoryCache[key] = value;
          _memoryCacheTimestamps[key] = timestamp;
          return value as T?;
        } catch (e) {
          debugPrint('Cache get error: $e');
        }
      }
    }

    return null;
  }

  /// Check if cached data exists and is valid
  bool has(String key, {Duration? maxAge}) {
    return get(key, maxAge: maxAge) != null;
  }

  /// Remove specific key from cache
  Future<void> remove(String key) async {
    _memoryCache.remove(key);
    _memoryCacheTimestamps.remove(key);

    await _prefs.remove('$_cachePrefix$key');
    await _prefs.remove('$_timestampPrefix$key');
  }

  /// Clear all cache
  Future<void> clear() async {
    _memoryCache.clear();
    _memoryCacheTimestamps.clear();

    final keys = _prefs.getKeys();
    for (final key in keys) {
      if (key.startsWith(_cachePrefix) || key.startsWith(_timestampPrefix)) {
        await _prefs.remove(key);
      }
    }
  }

  /// Clean expired cache entries
  Future<void> _cleanExpiredCache() async {
    final keys = _prefs.getKeys();
    final now = DateTime.now();

    for (final key in keys) {
      if (key.startsWith(_timestampPrefix)) {
        final timestampString = _prefs.getString(key);
        if (timestampString != null) {
          final timestamp = DateTime.parse(timestampString);
          // Remove entries older than cleanup threshold
          if (now.difference(timestamp) > _cleanupThreshold) {
            final cacheKey = key.replaceFirst(_timestampPrefix, '');
            await remove(cacheKey);
          }
        }
      }
    }
  }

  bool _isValid(DateTime timestamp, Duration? maxAge) {
    if (maxAge == null) return true;

    final age = DateTime.now().difference(timestamp);
    return age <= maxAge;
  }
}

/// Cache wrapper for async operations
class CachedData<T> {
  final String key;
  final Future<T> Function() fetcher;
  final Duration ttl;
  final CacheService _cache = CacheService();

  CachedData({
    required this.key,
    required this.fetcher,
    this.ttl = const Duration(minutes: 5),
  });

  Future<T> get({bool forceRefresh = false}) async {
    if (!forceRefresh) {
      final cached = _cache.get<T>(key, maxAge: ttl);
      if (cached != null) {
        debugPrint('Cache hit: $key');
        return cached;
      }
    }

    debugPrint('Cache miss: $key - fetching...');
    final data = await fetcher();
    await _cache.set(key, data, ttl: ttl);
    return data;
  }

  void invalidate() {
    _cache.remove(key);
  }
}

/// Mixin for widgets that need caching
mixin CacheableMixin<T extends StatefulWidget> on State<T> {
  final CacheService _cache = CacheService();

  /// Cache data with a unique key
  Future<void> cacheData(String key, dynamic data, {Duration? ttl}) async {
    await _cache.set(key, data, ttl: ttl ?? const Duration(minutes: 5));
  }

  /// Get cached data
  K? getCachedData<K>(String key, {Duration? maxAge}) {
    return _cache.get<K>(key, maxAge: maxAge);
  }

  /// Clear cache for this widget
  Future<void> clearCache(String key) async {
    await _cache.remove(key);
  }

  /// Generate cache key based on widget type and additional identifiers
  String generateCacheKey(String identifier) {
    return '${widget.runtimeType}_$identifier';
  }
}
