/// Type-safe JSON parsing utilities for handling API responses.
///
/// Provides safe extraction methods that handle DynamoDB's decimal type
/// (which returns as `num` instead of `int`) and other common type mismatches.
class JsonParser {
  /// Extract an integer value from JSON, handling num to int conversion.
  /// DynamoDB returns numeric values as Decimal which Dart sees as num.
  static int getInt(Map<String, dynamic> json, String key, {int defaultValue = 0}) {
    final value = json[key];
    if (value == null) return defaultValue;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return defaultValue;
  }

  /// Extract an optional integer value from JSON.
  static int? getIntOrNull(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.toInt();
    return null;
  }

  /// Extract a double value from JSON.
  static double getDouble(Map<String, dynamic> json, String key, {double defaultValue = 0.0}) {
    final value = json[key];
    if (value == null) return defaultValue;
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return defaultValue;
  }

  /// Extract an optional double value from JSON.
  static double? getDoubleOrNull(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return null;
    if (value is double) return value;
    if (value is num) return value.toDouble();
    return null;
  }

  /// Extract a string value from JSON.
  static String getString(Map<String, dynamic> json, String key, {String defaultValue = ''}) {
    final value = json[key];
    if (value == null) return defaultValue;
    if (value is String) return value;
    return value.toString();
  }

  /// Extract an optional string value from JSON.
  static String? getStringOrNull(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return null;
    if (value is String) return value;
    return value.toString();
  }

  /// Extract a boolean value from JSON.
  static bool getBool(Map<String, dynamic> json, String key, {bool defaultValue = false}) {
    final value = json[key];
    if (value == null) return defaultValue;
    if (value is bool) return value;
    if (value is String) return value.toLowerCase() == 'true';
    if (value is num) return value != 0;
    return defaultValue;
  }

  /// Extract a nested map from JSON.
  static Map<String, dynamic> getMap(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return {};
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return {};
  }

  /// Extract an optional nested map from JSON.
  static Map<String, dynamic>? getMapOrNull(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return null;
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return null;
  }

  /// Extract a list from JSON.
  static List<dynamic> getList(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return [];
    if (value is List) return value;
    return [];
  }

  /// Extract a list of maps from JSON.
  static List<Map<String, dynamic>> getMapList(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return [];
    if (value is List) {
      return value.whereType<Map>().map((m) => Map<String, dynamic>.from(m)).toList();
    }
    return [];
  }

  /// Extract a list of strings from JSON.
  static List<String> getStringList(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return [];
    if (value is List) {
      return value.map((e) => e?.toString() ?? '').where((s) => s.isNotEmpty).toList();
    }
    return [];
  }

  /// Extract a list of integers from JSON, handling num to int conversion.
  static List<int> getIntList(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return [];
    if (value is List) {
      return value.whereType<num>().map((n) => n.toInt()).toList();
    }
    return [];
  }

  /// Sum integer values from a map, handling num to int conversion.
  /// Useful for summing XP from various skill categories.
  static int sumMapValues(Map<String, dynamic> map) {
    int total = 0;
    for (final value in map.values) {
      if (value is num) {
        total += value.toInt();
      }
    }
    return total;
  }

  /// Get an integer from a nested map path.
  /// Example: getNestedInt(json, ['Stats', 'Health'], defaultValue: 100)
  static int getNestedInt(
    Map<String, dynamic> json,
    List<String> path, {
    int defaultValue = 0,
  }) {
    dynamic current = json;
    for (final key in path.take(path.length - 1)) {
      if (current is Map<String, dynamic>) {
        current = current[key];
      } else {
        return defaultValue;
      }
    }
    if (current is Map<String, dynamic> && path.isNotEmpty) {
      return getInt(current, path.last, defaultValue: defaultValue);
    }
    return defaultValue;
  }

  /// Get a string from a nested map path.
  static String getNestedString(
    Map<String, dynamic> json,
    List<String> path, {
    String defaultValue = '',
  }) {
    dynamic current = json;
    for (final key in path.take(path.length - 1)) {
      if (current is Map<String, dynamic>) {
        current = current[key];
      } else {
        return defaultValue;
      }
    }
    if (current is Map<String, dynamic> && path.isNotEmpty) {
      return getString(current, path.last, defaultValue: defaultValue);
    }
    return defaultValue;
  }

  /// Get a map from a nested path.
  static Map<String, dynamic> getNestedMap(
    Map<String, dynamic> json,
    List<String> path,
  ) {
    dynamic current = json;
    for (final key in path) {
      if (current is Map<String, dynamic>) {
        current = current[key];
      } else {
        return {};
      }
    }
    if (current is Map<String, dynamic>) {
      return current;
    }
    if (current is Map) {
      return Map<String, dynamic>.from(current);
    }
    return {};
  }
}
