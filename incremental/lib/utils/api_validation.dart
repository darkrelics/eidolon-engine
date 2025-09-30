/// API validation utilities for consistent data validation
/// between frontend and backend
class ApiValidation {
  /// Validate required fields in API response
  static void validateRequiredFields(
    Map<String, dynamic> data,
    List<String> requiredFields,
    String context,
  ) {
    final missingFields = <String>[];

    for (final field in requiredFields) {
      if (!data.containsKey(field) || data[field] == null) {
        missingFields.add(field);
      } else if (data[field] is String &&
          (data[field] as String).trim().isEmpty) {
        missingFields.add(field);
      }
    }

    if (missingFields.isNotEmpty) {
      throw ValidationException(
        '$context missing required fields: ${missingFields.join(', ')}',
      );
    }
  }

  /// Validate field type
  static T validateFieldType<T>(
    Map<String, dynamic> data,
    String field,
    String context,
  ) {
    if (!data.containsKey(field)) {
      throw ValidationException('$context missing field: $field');
    }

    final value = data[field];
    if (value is! T) {
      throw ValidationException(
        '$context field $field must be ${T.toString()}, got ${value.runtimeType}',
      );
    }

    return value;
  }

  /// Validate optional field type
  static T? validateOptionalFieldType<T>(
    Map<String, dynamic> data,
    String field,
    String context,
  ) {
    if (!data.containsKey(field) || data[field] == null) {
      return null;
    }

    final value = data[field];
    if (value is! T) {
      throw ValidationException(
        '$context field $field must be ${T.toString()}, got ${value.runtimeType}',
      );
    }

    return value;
  }

  /// Validate UUID format
  static bool isValidUuid(String? value) {
    if (value == null || value.isEmpty) return false;

    // UUID v4 regex pattern
    final uuidRegex = RegExp(
      r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
    );

    return uuidRegex.hasMatch(value);
  }

  /// Validate and extract UUID field
  static String validateUuidField(
    Map<String, dynamic> data,
    String field,
    String context,
  ) {
    final value = validateFieldType<String>(data, field, context);

    if (!isValidUuid(value)) {
      throw ValidationException('$context field $field must be a valid UUID');
    }

    return value;
  }

  /// Common API response schemas
  static const Map<String, List<String>> responseSchemas = {
    'Character': [
      'CharacterID',
      'CharacterName',
      'PlayerID',
      'Health',
      'MaxHealth',
      'Attributes',
      'Skills',
    ],
    'Story': ['StoryID', 'Title', 'Description', 'Type', 'Available'],
    'Segment': [
      'SegmentID',
      'StoryID',
      'SegmentType',
      'Status',
      'TimeRemaining',
    ],
  };

  /// Validate API response against schema
  static void validateResponseSchema(
    Map<String, dynamic> response,
    String schemaName,
  ) {
    final schema = responseSchemas[schemaName];
    if (schema == null) {
      throw ValidationException('Unknown schema: $schemaName');
    }

    validateRequiredFields(response, schema, schemaName);
  }
}

/// Custom exception for validation errors
class ValidationException implements Exception {
  final String message;

  ValidationException(this.message);

  @override
  String toString() => 'ValidationException: $message';
}
