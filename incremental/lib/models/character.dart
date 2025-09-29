import 'package:flutter/foundation.dart';

import '../services/api_service.dart';
import 'story.dart';

/// Character model for display purposes only.
/// All progression and calculations happen server-side.
class Character {
  final String id;
  final String name;
  final String archetypeId;
  final String archetypeName;
  final double health;
  final double maxHealth;
  final double essence;
  final double maxEssence;
  final Map<String, double> attributes;
  final Map<String, double> skills;
  final Map<String, int> resources;
  final Map<String, String> inventory; // MUD-compatible: slot -> itemId
  final Map<String, dynamic> inventoryDetails; // Enriched inventory data with item details
  final Map<String, dynamic> progress; // Story progress flags
  Map<String, dynamic>? storyState; // Current story position
  final String? activeStoryID; // Currently active story ID
  final String? activeSegmentID; // Currently active segment ID
  final String gameMode; // "MUD" or "Incremental"
  final DateTime lastUpdated;
  final List<String> availableStories;
  final List<String> abandonedStories;
  final List<String> completedStories;
  final List<Map<String, dynamic>>? availableStoriesDetails; // Full story metadata when no active story

  Character({
    required this.id,
    required this.name,
    required this.archetypeId,
    required this.archetypeName,
    required this.health,
    required this.maxHealth,
    required this.essence,
    required this.maxEssence,
    required this.attributes,
    required this.skills,
    required this.resources,
    required this.inventory,
    this.inventoryDetails = const {},
    required this.progress,
    this.storyState,
    this.activeStoryID,
    this.activeSegmentID,
    required this.gameMode,
    required this.lastUpdated,
    this.availableStories = const [],
    this.abandonedStories = const [],
    this.completedStories = const [],
    this.availableStoriesDetails,
  });

  /// Safely parse a map of dynamic values to doubles.
  ///
  /// This method handles various input types gracefully:
  /// - If value is already a double, it's used as-is
  /// - If value is an int or other num type, it's converted to double
  /// - If value is null, it defaults to 0.0
  /// - If value is not a number, it logs a warning and defaults to 0.0
  ///
  /// This prevents runtime crashes from unexpected server data formats.
  static Map<String, double> parseMapToDouble(Map<String, dynamic> rawMap) {
    return rawMap.map((key, value) {
      // Handle null values explicitly - skills/attributes might not exist yet
      if (value == null) {
        return MapEntry(key, 0.0);
      }

      // Try to convert to double safely
      if (value is num) {
        return MapEntry(key, value.toDouble());
      }

      // Log warning for unexpected types and provide safe default
      // This could happen if server data format changes unexpectedly
      debugPrint('Warning: Expected numeric value for $key, got ${value.runtimeType}. Defaulting to 0.0');
      return MapEntry(key, 0.0);
    });
  }

  /// Safely parse a map of dynamic values to integers.
  ///
  /// Similar to parseMapToDouble but for integer values:
  /// - Handles null by defaulting to 0
  /// - Converts any numeric type to int safely
  /// - Logs warnings for unexpected types
  static Map<String, int> parseMapToInt(Map<String, dynamic> rawMap) {
    return rawMap.map((key, value) {
      // Handle null values explicitly - resources might not exist yet
      if (value == null) {
        return MapEntry(key, 0);
      }

      // Try to convert to int safely
      if (value is num) {
        // Use round() instead of toInt() to handle floating point values gracefully
        return MapEntry(key, value.round());
      }

      // Log warning for unexpected types and provide safe default
      debugPrint('Warning: Expected numeric value for $key, got ${value.runtimeType}. Defaulting to 0');
      return MapEntry(key, 0);
    });
  }

  /// Create character from server response
  factory Character.fromJson(Map<String, dynamic> json) {
    // Debug logging (commented out to reduce verbosity)
    // debugPrint('Character.fromJson - Raw JSON keys: ${json.keys.toList()}');
    // debugPrint('Character.fromJson - Attributes: ${json['Attributes']}');
    // debugPrint('Character.fromJson - Skills: ${json['Skills']}');
    // debugPrint('Character.fromJson - Inventory: ${json['Inventory']}');
    // debugPrint('Character.fromJson - InventoryDetails: ${json['InventoryDetails']}');

    // Parse attributes and skills, converting numbers to doubles
    final Map<String, double> parsedAttributes = parseMapToDouble(json['Attributes'] ?? {});
    final Map<String, double> parsedSkills = parseMapToDouble(json['Skills'] ?? {});
    final Map<String, int> parsedResources = parseMapToInt(json['Resources'] ?? {});

    // Debug parsed data (commented out to reduce verbosity)
    // debugPrint('Character.fromJson - Parsed attributes: $parsedAttributes');
    // debugPrint('Character.fromJson - Parsed skills: $parsedSkills');

    // The archetype from server is just a string name, not an object with ID
    final archetypeName = json['Archetype'] as String? ?? 'default';

    return Character(
      id: json['CharacterID'] as String,
      name: json['CharacterName'] as String,
      archetypeId: archetypeName, // Use archetype name as ID for now
      archetypeName: archetypeName,
      // Safely handle health and essence values with defaults
      // These are critical values that must always have valid numbers
      health: (json['Health'] as num?)?.toDouble() ?? 10.0,
      maxHealth: (json['MaxHealth'] as num?)?.toDouble() ?? 10.0,
      essence: (json['Essence'] as num?)?.toDouble() ?? 0.0,
      maxEssence: (json['MaxEssence'] as num?)?.toDouble() ?? 3.0,
      attributes: parsedAttributes,
      skills: parsedSkills,
      resources: parsedResources,
      inventory: Map<String, String>.from(json['Inventory'] ?? {}),
      inventoryDetails: Map<String, dynamic>.from(json['InventoryDetails'] ?? {}),
      progress: Map<String, dynamic>.from(json['Progress'] ?? {}),
      storyState: json['StoryState'] as Map<String, dynamic>?,
      activeStoryID: json['ActiveStoryID'] as String?,
      activeSegmentID: json['ActiveSegmentID'] as String?,
      gameMode: json['GameMode'] as String? ?? 'Incremental',
      lastUpdated: DateTime.parse(json['UpdatedAt'] as String),
      availableStories: (json['AvailableStories'] as List? ?? []).map((storyId) => storyId as String).toList(),
      abandonedStories: (json['AbandonedStories'] as List? ?? []).map((storyId) => storyId as String).toList(),
      completedStories: (json['CompletedStories'] as List? ?? []).map((storyId) => storyId as String).toList(),
      availableStoriesDetails: json['AvailableStoriesDetails'] != null
          ? (json['AvailableStoriesDetails'] as List).map((story) => story as Map<String, dynamic>).toList()
          : null,
    );
  }

  /// Convert to JSON for API requests
  Map<String, dynamic> toJson() {
    return {
      'CharacterID': id,
      'CharacterName': name,
      'Archetype': archetypeName,
      'Health': health,
      'MaxHealth': maxHealth,
      'Essence': essence,
      'MaxEssence': maxEssence,
      'Attributes': attributes,
      'Skills': skills,
      'Resources': resources,
      'Inventory': inventory,
      'InventoryDetails': inventoryDetails,
      'Progress': progress,
      'StoryState': storyState,
      'GameMode': gameMode,
      'UpdatedAt': lastUpdated.toIso8601String(),
      'AvailableStories': availableStories,
      'AbandonedStories': abandonedStories,
      'CompletedStories': completedStories,
      if (availableStoriesDetails != null) 'AvailableStoriesDetails': availableStoriesDetails,
    };
  }

  /// Create a copy with updated values from server
  Character copyWith({
    double? health,
    double? essence,
    Map<String, double>? attributes,
    Map<String, double>? skills,
    Map<String, int>? resources,
    Map<String, String>? inventory,
    Map<String, dynamic>? inventoryDetails,
    Map<String, dynamic>? progress,
    Map<String, dynamic>? storyState,
    String? activeStoryId,
    String? activeSegmentId,
    DateTime? lastUpdated,
    List<String>? availableStories,
    List<String>? abandonedStories,
    List<String>? completedStories,
    List<Map<String, dynamic>>? availableStoriesDetails,
  }) {
    return Character(
      id: id,
      name: name,
      archetypeId: archetypeId,
      archetypeName: archetypeName,
      health: health ?? this.health,
      maxHealth: maxHealth,
      essence: essence ?? this.essence,
      maxEssence: maxEssence,
      attributes: attributes ?? this.attributes,
      skills: skills ?? this.skills,
      resources: resources ?? this.resources,
      inventory: inventory ?? this.inventory,
      inventoryDetails: inventoryDetails ?? this.inventoryDetails,
      progress: progress ?? this.progress,
      storyState: storyState ?? this.storyState,
      activeStoryID: activeStoryId ?? activeStoryID,
      activeSegmentID: activeSegmentId ?? activeSegmentID,
      gameMode: gameMode,
      lastUpdated: lastUpdated ?? this.lastUpdated,
      availableStories: availableStories ?? this.availableStories,
      abandonedStories: abandonedStories ?? this.abandonedStories,
      completedStories: completedStories ?? this.completedStories,
      availableStoriesDetails: availableStoriesDetails ?? this.availableStoriesDetails,
    );
  }

  /// Get effective score for a challenge (display only)
  ///
  /// Skills are flexible and can be dynamically added as the game matures.
  /// If a character doesn't have a skill, it's treated as 0.0.
  /// When a character receives XP for a skill they don't have, the skill
  /// is automatically added to their character record with the XP value.
  /// Attributes are fixed and defined in the Attributes class.
  int getEffectiveScore(String skillName, String attributeName) {
    final skill = skills[skillName] ?? 0.0;
    final attribute = attributes[attributeName] ?? 0.0;
    return (skill + attribute).floor();
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Character && runtimeType == other.runtimeType && id == other.id && lastUpdated == other.lastUpdated;

  @override
  int get hashCode => id.hashCode ^ lastUpdated.hashCode;
}

/// Attribute names matching server implementation
class Attributes {
  static const String strength = 'Strength';
  static const String agility = 'Agility';
  static const String endurance = 'Endurance';
  static const String charisma = 'Charisma';
  static const String intrigue = 'Intrigue';
  static const String presence = 'Presence';
  static const String perception = 'Perception';
  static const String intelligence = 'Intelligence';
  static const String cunning = 'Cunning';

  static const List<String> all = [strength, agility, endurance, charisma, intrigue, presence, perception, intelligence, cunning];
}

/// Skill names matching server implementation
class Skills {
  static const String melee = 'Melee';
  static const String archery = 'Archery';
  static const String brawling = 'Brawling';
  static const String dodge = 'Dodge';
  static const String parry = 'Parry';
  static const String stealth = 'Stealth';
  static const String investigation = 'Investigation';
  static const String tumbling = 'Tumbling';
  static const String climbing = 'Climbing';
  static const String lockpicking = 'Lockpicking';
  static const String mythos = 'Mythos';
  static const String arcane = 'Arcane';
  static const String firstAid = 'FirstAid';
  static const String foraging = 'Foraging';
  static const String appraise = 'Appraise';

  static const List<String> all = [
    melee,
    archery,
    brawling,
    dodge,
    parry,
    stealth,
    investigation,
    tumbling,
    climbing,
    lockpicking,
    mythos,
    arcane,
    firstAid,
    foraging,
    appraise,
  ];
}

/// Common resource types
class Resources {
  static const String gold = 'gold';
  static const String supplies = 'supplies';
  static const String reputation = 'reputation';
}

/// Data passed to GameScreen when starting a story
class StoryStartData {
  final CharacterInfo characterInfo;
  final Map<String, dynamic> initialSegment;
  final StoryMetadata storyMetadata;

  const StoryStartData({required this.characterInfo, required this.initialSegment, required this.storyMetadata});
}
