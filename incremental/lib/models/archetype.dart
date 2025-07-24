/// Archetype definition matching server structure.
/// Loaded dynamically from external sources.
class Archetype {
  final String archetypeName;
  final String description;
  final double health;
  final double essence;
  final bool player;
  final Map<String, double> attributes;
  final Map<String, double> skills;
  final List<StartingItem> startingItems;
  final List<String> availableStories;

  Archetype({
    required this.archetypeName,
    required this.description,
    required this.health,
    required this.essence,
    required this.player,
    required this.attributes,
    required this.skills,
    required this.startingItems,
    this.availableStories = const [],
  });

  factory Archetype.fromJson(Map<String, dynamic> json) {
    return Archetype(
      archetypeName: json['ArchetypeName'] as String,
      description: json['Description'] as String,
      health: (json['Health'] as num).toDouble(),
      essence: (json['Essence'] as num).toDouble(),
      player: json['Player'] as bool,
      attributes: Map<String, double>.from(
        (json['Attributes'] as Map).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      skills: Map<String, double>.from(
        (json['Skills'] as Map).map(
          (key, value) => MapEntry(key, (value as num).toDouble()),
        ),
      ),
      startingItems: (json['StartingItems'] as List? ?? [])
          .map((item) => StartingItem.fromJson(item as Map<String, dynamic>))
          .toList(),
      availableStories: (json['AvailableStories'] as List? ?? [])
          .map((storyId) => storyId as String)
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'ArchetypeName': archetypeName,
      'Description': description,
      'Health': health,
      'Essence': essence,
      'Player': player,
      'Attributes': attributes,
      'Skills': skills,
      'StartingItems': startingItems.map((item) => item.toJson()).toList(),
      'AvailableStories': availableStories,
    };
  }
}

/// Starting item definition for archetypes
class StartingItem {
  final String prototypeID;
  final String slot;
  final bool isWorn;

  StartingItem({
    required this.prototypeID,
    required this.slot,
    required this.isWorn,
  });

  factory StartingItem.fromJson(Map<String, dynamic> json) {
    return StartingItem(
      prototypeID: json['PrototypeID'] as String,
      slot: json['Slot'] as String,
      isWorn: json['IsWorn'] as bool,
    );
  }

  Map<String, dynamic> toJson() {
    return {'PrototypeID': prototypeID, 'Slot': slot, 'IsWorn': isWorn};
  }
}

/// Archetype manifest for dynamic loading
class ArchetypeManifest {
  final String version;
  final DateTime lastUpdated;
  final Map<String, String> archetypes; // id -> download URL

  ArchetypeManifest({
    required this.version,
    required this.lastUpdated,
    required this.archetypes,
  });

  factory ArchetypeManifest.fromJson(Map<String, dynamic> json) {
    return ArchetypeManifest(
      version: json['version'] as String,
      lastUpdated: DateTime.parse(json['lastUpdated'] as String),
      archetypes: Map<String, String>.from(json['archetypes'] as Map),
    );
  }
}
