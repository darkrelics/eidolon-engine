import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Application configuration loaded from JSON
class AppConfig {
  final String? testArchetypesPath;
  final String? archetypeManifestUrl;

  AppConfig._({this.testArchetypesPath, this.archetypeManifestUrl});

  static AppConfig? _instance;

  static Future<AppConfig> get instance async {
    if (_instance == null) {
      await _loadConfig();
    }
    return _instance!;
  }

  static Future<void> _loadConfig() async {
    try {
      final jsonString = await rootBundle.loadString(
        'assets/config/app_config.json',
      );
      final json = jsonDecode(jsonString) as Map<String, dynamic>;

      final environment = kDebugMode ? 'development' : 'production';
      final envConfig = json[environment] as Map<String, dynamic>?;

      if (envConfig == null) {
        _instance = AppConfig._();
        return;
      }

      _instance = AppConfig._(
        testArchetypesPath: envConfig['testArchetypesPath'] as String?,
        archetypeManifestUrl: envConfig['archetypeManifestUrl'] as String?,
      );
    } catch (e) {
      debugPrint('Failed to load app config: $e');
      _instance = AppConfig._();
    }
  }
}
