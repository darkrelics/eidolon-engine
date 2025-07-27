/// Utility functions for flexible JSON parsing
/// Supports both PascalCase and camelCase field names
class JsonUtils {
  /// Get a value from a map using either PascalCase or camelCase key
  static T? getFlexible<T>(
    Map<String, dynamic> json,
    String pascalKey,
    String camelKey,
  ) {
    // Try PascalCase first (preferred)
    if (json.containsKey(pascalKey)) {
      return json[pascalKey] as T?;
    }
    // Fall back to camelCase
    if (json.containsKey(camelKey)) {
      return json[camelKey] as T?;
    }
    return null;
  }

  /// Get a required value from a map using either PascalCase or camelCase key
  static T getFlexibleRequired<T>(
    Map<String, dynamic> json,
    String pascalKey,
    String camelKey, {
    required T defaultValue,
  }) {
    final value = getFlexible<T>(json, pascalKey, camelKey);
    return value ?? defaultValue;
  }

  /// Get a list from a map using either PascalCase or camelCase key
  static List<T> getFlexibleList<T>(
    Map<String, dynamic> json,
    String pascalKey,
    String camelKey,
  ) {
    final value = getFlexible<List>(json, pascalKey, camelKey);
    if (value == null) return [];
    return value.cast<T>();
  }

  /// Get a map from a map using either PascalCase or camelCase key
  static Map<String, dynamic> getFlexibleMap(
    Map<String, dynamic> json,
    String pascalKey,
    String camelKey,
  ) {
    final value = getFlexible<Map>(json, pascalKey, camelKey);
    if (value == null) return {};
    return Map<String, dynamic>.from(value);
  }

  /// Convert camelCase to PascalCase
  static String toPascalCase(String camelCase) {
    if (camelCase.isEmpty) return camelCase;
    return camelCase[0].toUpperCase() + camelCase.substring(1);
  }

  /// Convert PascalCase to camelCase
  static String toCamelCase(String pascalCase) {
    if (pascalCase.isEmpty) return pascalCase;
    return pascalCase[0].toLowerCase() + pascalCase.substring(1);
  }
}
