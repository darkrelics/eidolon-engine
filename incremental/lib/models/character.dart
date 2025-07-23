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
  final Map<String, dynamic> progress; // Story progress flags
  final Map<String, dynamic>? storyState; // Current story position
  final String gameMode; // "MUD" or "Incremental"
  final DateTime lastUpdated;

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
    required this.progress,
    this.storyState,
    required this.gameMode,
    required this.lastUpdated,
  });

  /// Parse a map of dynamic values to doubles
  static Map<String, double> parseMapToDouble(Map<String, dynamic> rawMap) {
    return rawMap.map((key, value) => MapEntry(key, (value as num).toDouble()));
  }

  /// Parse a map of dynamic values to integers
  static Map<String, int> parseMapToInt(Map<String, dynamic> rawMap) {
    return rawMap.map((key, value) => MapEntry(key, (value as num).toInt()));
  }

  /// Create character from server response
  factory Character.fromJson(Map<String, dynamic> json) {
    // Parse attributes and skills, converting numbers to doubles
    final Map<String, double> parsedAttributes = parseMapToDouble(json['Attributes'] ?? {});
    final Map<String, double> parsedSkills = parseMapToDouble(json['Skills'] ?? {});
    final Map<String, int> parsedResources = parseMapToInt(json['Resources'] ?? {});
    
    // The archetype from server is just a string name, not an object with ID
    final archetypeName = json['Archetype'] as String? ?? 'default';
    
    return Character(
      id: json['CharacterID'] as String,
      name: json['CharacterName'] as String,
      archetypeId: archetypeName, // Use archetype name as ID for now
      archetypeName: archetypeName,
      health: (json['Health'] as num).toDouble(),
      maxHealth: (json['MaxHealth'] as num).toDouble(),
      essence: (json['Essence'] as num).toDouble(),
      maxEssence: (json['MaxEssence'] as num).toDouble(),
      attributes: parsedAttributes,
      skills: parsedSkills,
      resources: parsedResources,
      inventory: Map<String, String>.from(json['Inventory'] ?? {}),
      progress: Map<String, dynamic>.from(json['Progress'] ?? {}),
      storyState: json['StoryState'] as Map<String, dynamic>?,
      gameMode: json['GameMode'] as String? ?? 'Incremental',
      lastUpdated: DateTime.parse(json['UpdatedAt'] as String),
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
      'Progress': progress,
      'StoryState': storyState,
      'GameMode': gameMode,
      'UpdatedAt': lastUpdated.toIso8601String(),
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
    Map<String, dynamic>? progress,
    Map<String, dynamic>? storyState,
    DateTime? lastUpdated,
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
      progress: progress ?? this.progress,
      storyState: storyState ?? this.storyState,
      gameMode: gameMode,
      lastUpdated: lastUpdated ?? this.lastUpdated,
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
      other is Character &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          lastUpdated == other.lastUpdated;

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

  static const List<String> all = [
    strength,
    agility,
    endurance,
    charisma,
    intrigue,
    presence,
    perception,
    intelligence,
    cunning,
  ];
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
