import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/archetype.dart';
import '../config/app_config.dart';

/// Service for loading archetype definitions dynamically
class ArchetypeService {
  static const String _manifestUrlKey = 'archetype_manifest_url';
  static const String _cachedManifestKey = 'cached_archetype_manifest';
  static const String _cachedArchetypesKey = 'cached_archetypes';
  static const String _lastUpdateCheckKey = 'archetype_last_update_check';

  final SharedPreferences _prefs;
  final http.Client _httpClient;

  ArchetypeManifest? _manifest;
  final Map<String, Archetype> _archetypeCache = {};

  ArchetypeService({required SharedPreferences prefs, http.Client? httpClient})
    : _prefs = prefs,
      _httpClient = httpClient ?? http.Client();

  /// Get manifest URL from environment or preferences
  String? get manifestUrl {
    return _prefs.getString(_manifestUrlKey);
  }

  /// Set manifest URL for production
  Future<void> setManifestUrl(String url) async {
    await _prefs.setString(_manifestUrlKey, url);
  }

  /// Load archetypes, using cache when possible
  Future<Map<String, Archetype>> loadArchetypes() async {
    // Check if we should update
    final lastCheck = _prefs.getInt(_lastUpdateCheckKey) ?? 0;
    final now = DateTime.now().millisecondsSinceEpoch;
    final shouldCheckUpdate = now - lastCheck > 3600000; // 1 hour

    if (shouldCheckUpdate && manifestUrl != null) {
      try {
        await _updateFromManifest();
      } catch (e) {
        debugPrint('Failed to update archetypes: $e');
      }
    }

    // Load from cache
    if (_archetypeCache.isEmpty) {
      await _loadCachedArchetypes();
    }

    // If still empty, load test data
    if (_archetypeCache.isEmpty) {
      await _loadTestArchetypes();
    }

    return Map.from(_archetypeCache);
  }

  /// Update archetypes from manifest
  Future<void> _updateFromManifest() async {
    final url = manifestUrl;
    if (url == null) return;

    final response = await _httpClient.get(Uri.parse(url));
    if (response.statusCode != 200) {
      throw Exception('Failed to load manifest: ${response.statusCode}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    _manifest = ArchetypeManifest.fromJson(json);

    // Save manifest
    await _prefs.setString(_cachedManifestKey, response.body);
    await _prefs.setInt(
      _lastUpdateCheckKey,
      DateTime.now().millisecondsSinceEpoch,
    );

    // Download updated archetypes
    for (final entry in _manifest!.archetypes.entries) {
      await _downloadArchetype(entry.key, entry.value);
    }
  }

  /// Download individual archetype
  Future<void> _downloadArchetype(String id, String url) async {
    try {
      final response = await _httpClient.get(Uri.parse(url));
      if (response.statusCode != 200) {
        throw Exception('Failed to load archetype $id: ${response.statusCode}');
      }

      final json = jsonDecode(response.body) as Map<String, dynamic>;
      final archetype = Archetype.fromJson(json);

      _archetypeCache[id] = archetype;

      // Cache to storage
      final cached = _prefs.getString(_cachedArchetypesKey) ?? '{}';
      final cachedMap = jsonDecode(cached) as Map<String, dynamic>;
      cachedMap[id] = json;
      await _prefs.setString(_cachedArchetypesKey, jsonEncode(cachedMap));
    } catch (e) {
      debugPrint('Failed to download archetype $id: $e');
    }
  }

  /// Load archetypes from local cache
  Future<void> _loadCachedArchetypes() async {
    final cached = _prefs.getString(_cachedArchetypesKey);
    if (cached == null) return;

    try {
      final cachedMap = jsonDecode(cached) as Map<String, dynamic>;
      for (final entry in cachedMap.entries) {
        final archetype = Archetype.fromJson(
          entry.value as Map<String, dynamic>,
        );
        _archetypeCache[entry.key] = archetype;
      }
    } catch (e) {
      debugPrint('Failed to load cached archetypes: $e');
    }
  }

  /// Load test archetypes for development
  Future<void> _loadTestArchetypes() async {
    try {
      final config = await AppConfig.instance;
      final path = config.testArchetypesPath;
      if (path == null) {
        debugPrint('No test archetypes path configured');
        return;
      }

      final jsonString = await rootBundle.loadString(path);
      final json = jsonDecode(jsonString) as Map<String, dynamic>;
      final archetypes = json['archetypes'] as Map<String, dynamic>;

      for (final entry in archetypes.entries) {
        final archetype = Archetype.fromJson(
          entry.value as Map<String, dynamic>,
        );
        _archetypeCache[entry.key] = archetype;
      }
    } catch (e) {
      debugPrint('Failed to load test archetypes: $e');
    }
  }

  /// Get specific archetype by ID
  Future<Archetype?> getArchetype(String id) async {
    if (_archetypeCache.isEmpty) {
      await loadArchetypes();
    }
    return _archetypeCache[id];
  }

  /// Clear all cached data
  Future<void> clearCache() async {
    _archetypeCache.clear();
    await _prefs.remove(_cachedManifestKey);
    await _prefs.remove(_cachedArchetypesKey);
    await _prefs.remove(_lastUpdateCheckKey);
  }
}
