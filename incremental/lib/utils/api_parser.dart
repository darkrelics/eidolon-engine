import 'api_validation.dart';

/// Standardized API response parser
/// and provides consistent validation
class ApiParser {
  /// Parse character response
  static Map<String, dynamic> parseCharacter(Map<String, dynamic> response) {
    final characterData = response['Character'] as Map<String, dynamic>?;
    if (characterData == null) {
      throw ValidationException('Response missing Character field');
    }

    // Validate required fields
    ApiValidation.validateResponseSchema(characterData, 'Character');

    return characterData;
  }

  /// Parse characters list response
  static List<Map<String, dynamic>> parseCharactersList(
    Map<String, dynamic> response,
  ) {
    // Extract characters array
    final characters = response['Characters'] as List<dynamic>?;
    if (characters == null) {
      throw ValidationException('Response missing Characters field');
    }

    // Validate each character
    return characters.map((char) {
      final charMap = char as Map<String, dynamic>;
      ApiValidation.validateRequiredFields(charMap, [
        'CharacterID',
        'CharacterName',
        'Dead',
      ], 'Character');
      // Default GameMode to 'None' if not provided by API
      if (!charMap.containsKey('GameMode')) {
        charMap['GameMode'] = 'None';
      }
      return charMap;
    }).toList();
  }

  /// Parse stories response
  static List<Map<String, dynamic>> parseStories(
    Map<String, dynamic> response,
  ) {
    // Extract stories array
    final stories = response['Stories'] as List<dynamic>?;
    if (stories == null) {
      throw ValidationException('Response missing Stories field');
    }

    // Validate each story
    return stories.map((story) {
      final storyMap = story as Map<String, dynamic>;
      ApiValidation.validateResponseSchema(storyMap, 'Story');
      return storyMap;
    }).toList();
  }

  /// Parse segment response
  static Map<String, dynamic> parseSegment(Map<String, dynamic> response) {
    // Extract segment data
    final segmentData = response['Segment'] as Map<String, dynamic>?;
    if (segmentData == null) {
      throw ValidationException('Response missing Segment field');
    }

    // Validate required fields
    ApiValidation.validateResponseSchema(segmentData, 'Segment');

    return segmentData;
  }

  /// Parse current story response
  static Map<String, dynamic> parseCurrentStory(Map<String, dynamic> response) {
    // Validate top-level fields
    ApiValidation.validateRequiredFields(response, [
      'Story',
      'Segment',
    ], 'CurrentStory');

    // Validate nested objects
    final story = response['Story'] as Map<String, dynamic>;
    final segment = response['Segment'] as Map<String, dynamic>;

    ApiValidation.validateResponseSchema(story, 'Story');
    ApiValidation.validateResponseSchema(segment, 'Segment');

    return response;
  }

  /// Parse outcome response
  static Map<String, dynamic> parseOutcome(Map<String, dynamic> response) {
    // Extract outcome data
    final outcomeData = response['Outcome'] as Map<String, dynamic>?;
    if (outcomeData == null) {
      throw ValidationException('Response missing Outcome field');
    }

    // Validate required outcome fields
    ApiValidation.validateRequiredFields(outcomeData, [
      'Outcome',
      'Narrative',
      'Effects',
    ], 'Outcome');

    return outcomeData;
  }

  /// Parse error response
  static String parseError(Map<String, dynamic> response) {
    // Backend returns errors as {"Error": "message"}
    final error = response['Error'] as String?;
    if (error != null) {
      return error;
    }

    // Fallback to lowercase error field
    final errorLower = response['error'] as String?;
    if (errorLower != null) {
      return errorLower;
    }

    // Fallback to message field
    final message =
        response['Message'] as String? ?? response['message'] as String?;
    if (message != null) {
      return message;
    }

    return 'Unknown error';
  }

  /// Standardize field names for sending to backend
  static Map<String, dynamic> toPascalCase(Map<String, dynamic> data) {
    final result = <String, dynamic>{};

    data.forEach((key, value) {
      // Convert first letter to uppercase
      final pascalKey = key.isEmpty
          ? key
          : key[0].toUpperCase() + key.substring(1);

      // Recursively convert nested maps
      if (value is Map<String, dynamic>) {
        result[pascalKey] = toPascalCase(value);
      } else if (value is List) {
        result[pascalKey] = value.map((item) {
          if (item is Map<String, dynamic>) {
            return toPascalCase(item);
          }
          return item;
        }).toList();
      } else {
        result[pascalKey] = value;
      }
    });

    return result;
  }
}
