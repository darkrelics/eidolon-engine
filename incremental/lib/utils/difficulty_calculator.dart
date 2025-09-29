import 'package:flutter/material.dart';
import 'package:eidolon_incremental/models/character.dart';

enum DifficultyLevel { trivial, easy, moderate, hard, extreme }

class DifficultyCalculator {
  /// Calculate story difficulty based on character's skills vs required checks
  static DifficultyLevel calculateStoryDifficulty(
    Map<String, num> difficultyMap,
    Character character,
  ) {
    if (difficultyMap.isEmpty) return DifficultyLevel.moderate;

    // Calculate success chance for each skill check
    final successChances = <double>[];

    difficultyMap.forEach((skill, difficulty) {
      final skillValue = character.skills[skill] ?? 0.0;
      final attribute = _getGoverningAttribute(skill);
      final attributeValue = character.attributes[attribute] ?? 0.0;
      final effectiveScore = skillValue + attributeValue;

      // Approximate success chance using simplified mechanics
      // Based on MUD mechanics where difficulty is the target number
      final difference = effectiveScore - difficulty;
      final successChance = (0.5 + (difference * 0.05)).clamp(0.0, 1.0);
      successChances.add(successChance);
    });

    // Average success chance across all checks
    final avgSuccess = successChances.isEmpty
        ? 0.5
        : successChances.reduce((a, b) => a + b) / successChances.length;

    if (avgSuccess >= 0.9) return DifficultyLevel.trivial;
    if (avgSuccess >= 0.7) return DifficultyLevel.easy;
    if (avgSuccess >= 0.5) return DifficultyLevel.moderate;
    if (avgSuccess >= 0.3) return DifficultyLevel.hard;
    return DifficultyLevel.extreme;
  }

  /// Get the color associated with a difficulty level
  static Color getDifficultyColor(DifficultyLevel level) {
    switch (level) {
      case DifficultyLevel.trivial:
        return Colors.grey;
      case DifficultyLevel.easy:
        return Colors.green;
      case DifficultyLevel.moderate:
        return Colors.yellow.shade700;
      case DifficultyLevel.hard:
        return Colors.orange;
      case DifficultyLevel.extreme:
        return Colors.red;
    }
  }

  /// Get the display label for a difficulty level
  static String getDifficultyLabel(DifficultyLevel level) {
    switch (level) {
      case DifficultyLevel.trivial:
        return 'Trivial';
      case DifficultyLevel.easy:
        return 'Easy';
      case DifficultyLevel.moderate:
        return 'Moderate';
      case DifficultyLevel.hard:
        return 'Hard';
      case DifficultyLevel.extreme:
        return 'Extreme';
    }
  }

  /// Map skills to their governing attributes
  static String _getGoverningAttribute(String skill) {
    // Based on incremental game skill/attribute pairings
    final skillAttributeMap = {
      'Melee': 'Strength',
      'Brawling': 'Strength',
      'Archery': 'Agility',
      'Dodge': 'Agility',
      'Stealth': 'Agility',
      'Tumbling': 'Agility',
      'Parry': 'Endurance',
      'Climbing': 'Endurance',
      'Investigation': 'Perception',
      'Lockpicking': 'Cunning',
      'Mythos': 'Intelligence',
      'Arcane': 'Intelligence',
      'FirstAid': 'Intelligence',
      'Foraging': 'Perception',
      'Appraise': 'Intelligence',
    };

    return skillAttributeMap[skill] ?? 'Intelligence';
  }
}
