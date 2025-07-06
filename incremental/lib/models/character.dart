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

  /// Create character from server response
  factory Character.fromJson(Map<String, dynamic> json) {
    return Character(
      id: json['id'] as String,
      name: json['name'] as String,
      archetypeId: json['archetypeId'] as String,
      archetypeName: json['archetypeName'] as String,
      health: (json['health'] as num).toDouble(),
      maxHealth: (json['maxHealth'] as num).toDouble(),
      essence: (json['essence'] as num).toDouble(),
      maxEssence: (json['maxEssence'] as num).toDouble(),
      attributes: Map<String, double>.from(
        (json['attributes'] as Map).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      skills: Map<String, double>.from(
        (json['skills'] as Map).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      resources: Map<String, int>.from(json['resources'] ?? {}),
      inventory: Map<String, String>.from(json['inventory'] ?? {}),
      progress: Map<String, dynamic>.from(json['progress'] ?? {}),
      storyState: json['storyState'] as Map<String, dynamic>?,
      gameMode: json['gameMode'] as String? ?? 'Incremental',
      lastUpdated: DateTime.parse(json['lastUpdated'] as String),
    );
  }

  /// Convert to JSON for API requests
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'archetypeId': archetypeId,
      'archetypeName': archetypeName,
      'health': health,
      'maxHealth': maxHealth,
      'essence': essence,
      'maxEssence': maxEssence,
      'attributes': attributes,
      'skills': skills,
      'resources': resources,
      'inventory': inventory,
      'progress': progress,
      'storyState': storyState,
      'gameMode': gameMode,
      'lastUpdated': lastUpdated.toIso8601String(),
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