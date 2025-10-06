import 'package:flutter_test/flutter_test.dart';
import 'package:eidolon_incremental/models/character.dart';

void main() {
  group('Character', () {
    late Map<String, dynamic> validJson;

    setUp(() {
      validJson = {
        'CharacterID': 'test-id',
        'CharacterName': 'Test Character',
        'Archetype': 'Warrior',
        'Health': 10.0,
        'MaxHealth': 12.0,
        'Essence': 2.0,
        'MaxEssence': 2.0,
        'GameMode': 'None',
        'Attributes': {
          'Strength': 3.0,
          'Agility': 2.0,
          'Endurance': 3.0,
          'Charisma': 1.0,
          'Intrigue': 1.0,
          'Presence': 2.0,
          'Perception': 1.0,
          'Intelligence': 1.0,
          'Cunning': 1.0,
        },
        'Skills': {
          'Melee': 1.0,
          'Archery': 0.0,
          'Brawling': 1.0,
          'Dodge': 1.0,
          'Parry': 1.0,
          'Stealth': 0.0,
          'Investigation': 0.0,
          'Tumbling': 0.0,
          'Climbing': 0.0,
          'Lockpicking': 0.0,
          'Mythos': 0.0,
          'Arcane': 0.0,
          'FirstAid': 1.0,
          'Foraging': 0.0,
          'Appraise': 0.0,
        },
        'Resources': {'gold': 100, 'supplies': 10},
        'UpdatedAt': '2024-01-01T00:00:00.000Z',
      };
    });

    test('creates character from valid JSON', () {
      final character = Character.fromJson(validJson);

      expect(character.id, equals('test-id'));
      expect(character.name, equals('Test Character'));
      expect(character.archetypeId, equals('Warrior'));
      expect(character.archetypeName, equals('Warrior'));
      expect(character.health, equals(10.0));
      expect(character.maxHealth, equals(12.0));
      expect(character.essence, equals(2.0));
      expect(character.maxEssence, equals(2.0));
      expect(character.attributes['Strength'], equals(3.0));
      expect(character.skills['Melee'], equals(1.0));
      expect(character.resources['gold'], equals(100));
    });

    test('converts character to JSON', () {
      final character = Character.fromJson(validJson);
      final json = character.toJson();

      expect(json['CharacterID'], equals('test-id'));
      expect(json['CharacterName'], equals('Test Character'));
      expect(json['Attributes']['Strength'], equals(3.0));
      expect(json['Skills']['Melee'], equals(1.0));
      expect(json['Resources']['gold'], equals(100));
    });

    test('calculates effective score correctly', () {
      final character = Character.fromJson(validJson);

      // Melee (1.0) + Strength (3.0) = 4
      expect(character.getEffectiveScore('Melee', 'Strength'), equals(4));

      // Arcane (0.0) + Intelligence (1.0) = 1
      expect(character.getEffectiveScore('Arcane', 'Intelligence'), equals(1));

      // Non-existent skill/attribute = 0
      expect(character.getEffectiveScore('NonExistent', 'Strength'), equals(3));
      expect(character.getEffectiveScore('Melee', 'NonExistent'), equals(1));
    });

    test('copyWith updates specified fields', () {
      final character = Character.fromJson(validJson);
      final updated = character.copyWith(
        health: 5.0,
        resources: {'gold': 150, 'supplies': 5},
      );

      expect(updated.health, equals(5.0));
      expect(updated.resources['gold'], equals(150));
      expect(updated.resources['supplies'], equals(5));

      // Unchanged fields remain the same
      expect(updated.name, equals(character.name));
      expect(updated.essence, equals(character.essence));
      expect(updated.skills, equals(character.skills));
    });

    test('handles missing resources gracefully', () {
      validJson.remove('Resources');
      final character = Character.fromJson(validJson);

      expect(character.resources, isEmpty);
    });

    test('equality based on id and lastUpdated', () {
      final character1 = Character.fromJson(validJson);
      final character2 = Character.fromJson(validJson);

      expect(character1, equals(character2));

      // Different lastUpdated
      validJson['UpdatedAt'] = '2024-01-02T00:00:00.000Z';
      final character3 = Character.fromJson(validJson);
      expect(character1, isNot(equals(character3)));

      // Different id
      validJson['CharacterID'] = 'different-id';
      validJson['UpdatedAt'] = '2024-01-01T00:00:00.000Z';
      final character4 = Character.fromJson(validJson);
      expect(character1, isNot(equals(character4)));
    });

    test('parses wounds from JSON', () {
      validJson['Wounds'] = [
        {'DamageType': 'bashing', 'HealAt': '2024-01-01T12:00:00.000Z'},
        {'DamageType': 'lethal', 'HealAt': '2024-01-01T18:00:00.000Z'},
      ];
      final character = Character.fromJson(validJson);

      expect(character.wounds, isNotNull);
      expect(character.wounds!.length, equals(2));
      expect(character.wounds![0]['DamageType'], equals('bashing'));
      expect(character.wounds![1]['DamageType'], equals('lethal'));
    });

    test('handles missing wounds gracefully', () {
      final character = Character.fromJson(validJson);
      expect(character.wounds, isNull);
    });

    test('handles empty wounds list', () {
      validJson['Wounds'] = [];
      final character = Character.fromJson(validJson);

      expect(character.wounds, isNotNull);
      expect(character.wounds, isEmpty);
    });

    test('defaults gameMode to None when missing', () {
      validJson.remove('GameMode');
      final character = Character.fromJson(validJson);

      expect(character.gameMode, equals('None'));
    });

    test('parses gameMode correctly', () {
      validJson['GameMode'] = 'Incremental';
      final character1 = Character.fromJson(validJson);
      expect(character1.gameMode, equals('Incremental'));

      validJson['GameMode'] = 'MUD';
      final character2 = Character.fromJson(validJson);
      expect(character2.gameMode, equals('MUD'));

      validJson['GameMode'] = 'None';
      final character3 = Character.fromJson(validJson);
      expect(character3.gameMode, equals('None'));
    });

    test('copyWith updates gameMode', () {
      final character = Character.fromJson(validJson);
      expect(character.gameMode, equals('None'));

      final updated = character.copyWith(gameMode: 'Incremental');
      expect(updated.gameMode, equals('Incremental'));
      expect(character.gameMode, equals('None')); // Original unchanged
    });
  });

  group('Attributes', () {
    test('contains all expected attributes', () {
      expect(Attributes.all.length, equals(9));
      expect(Attributes.all, contains('Strength'));
      expect(Attributes.all, contains('Agility'));
      expect(Attributes.all, contains('Endurance'));
      expect(Attributes.all, contains('Charisma'));
      expect(Attributes.all, contains('Intrigue'));
      expect(Attributes.all, contains('Presence'));
      expect(Attributes.all, contains('Perception'));
      expect(Attributes.all, contains('Intelligence'));
      expect(Attributes.all, contains('Cunning'));
    });
  });

  group('Skills', () {
    test('contains all expected skills', () {
      expect(Skills.all.length, equals(15));
      expect(Skills.all, contains('Melee'));
      expect(Skills.all, contains('Archery'));
      expect(Skills.all, contains('Brawling'));
      expect(Skills.all, contains('Dodge'));
      expect(Skills.all, contains('Parry'));
      expect(Skills.all, contains('Stealth'));
      expect(Skills.all, contains('Investigation'));
      expect(Skills.all, contains('Tumbling'));
      expect(Skills.all, contains('Climbing'));
      expect(Skills.all, contains('Lockpicking'));
      expect(Skills.all, contains('Mythos'));
      expect(Skills.all, contains('Arcane'));
      expect(Skills.all, contains('FirstAid'));
      expect(Skills.all, contains('Foraging'));
      expect(Skills.all, contains('Appraise'));
    });
  });
}
