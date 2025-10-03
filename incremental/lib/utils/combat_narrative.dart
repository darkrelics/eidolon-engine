import 'dart:math';

/// Combat narrative generation for mechanical segments.
///
/// Provides template-based combat descriptions from combat round data.
class CombatNarrative {
  static final _random = Random();

  /// Offensive action templates
  static const _offensiveTemplates = {
    'Melee': {
      'success': [
        '{attacker} swings their blade at {defender}, landing a {severity} strike',
        '{attacker}\'s melee attack catches {defender} off guard, dealing {severity} damage',
        '{attacker} closes in and delivers a {severity} blow with their weapon',
        '{attacker}\'s blade finds its mark, striking {defender} with {severity} force',
      ],
      'failure': [
        '{attacker} swings at {defender}, but the attack is deflected',
        '{attacker}\'s melee attack misses as {defender} evades',
        '{attacker} lunges forward, but {defender} sidesteps the blow',
        '{attacker}\'s weapon slices through empty air',
      ],
    },
    'Brawling': {
      'success': [
        '{attacker} lands a {severity} punch on {defender}',
        '{attacker} grapples {defender} and delivers a {severity} strike',
        '{attacker}\'s fist connects with {severity} impact',
        '{attacker} strikes {defender} with a {severity} blow',
      ],
      'failure': [
        '{attacker} throws a punch, but {defender} blocks it',
        '{attacker}\'s strike is parried by {defender}',
        '{attacker} attempts to grapple, but {defender} breaks free',
        '{attacker}\'s attack is dodged at the last moment',
      ],
    },
    'Archery': {
      'success': [
        '{attacker} looses an arrow that strikes {defender} with {severity} precision',
        '{attacker}\'s shot finds its target, dealing {severity} damage',
        '{attacker} fires a {severity} shot that pierces {defender}',
        '{attacker}\'s arrow flies true, hitting {defender} with {severity} force',
      ],
      'failure': [
        '{attacker} fires an arrow, but it sails past {defender}',
        '{attacker}\'s shot goes wide as {defender} dodges',
        '{attacker} releases their bowstring, but the arrow misses',
        '{attacker}\'s aim is off, and the arrow clatters harmlessly away',
      ],
    },
    'Arcane': {
      'success': [
        '{attacker} unleashes arcane energy that strikes {defender} with {severity} power',
        '{attacker}\'s spell blast hits {defender} for {severity} damage',
        '{attacker} channels magic into a {severity} attack against {defender}',
        '{attacker}\'s arcane bolt sears {defender} with {severity} intensity',
      ],
      'failure': [
        '{attacker} casts a spell, but {defender} resists the magic',
        '{attacker}\'s arcane bolt dissipates before reaching {defender}',
        '{attacker} attempts to channel magic, but the spell fizzles',
        '{attacker}\'s magical attack is deflected by {defender}',
      ],
    },
  };

  /// Severity descriptors based on sigma and damage
  static const _severityNormal = ['solid', 'strong', 'fierce', 'powerful'];
  static const _severityCritical = ['devastating', 'crushing', 'brutal', 'mighty'];

  /// Generate a combat narrative from round data.
  ///
  /// Takes combat round data containing offensive/defensive actions and damage,
  /// along with character and opponent names, and returns an engaging narrative.
  static String generateNarrative(
    Map<String, dynamic> roundData,
    String characterName,
    String opponentName,
  ) {
    final narratives = <String>[];

    // Character's offensive action
    final charOffensive = roundData['CharacterOffensive'] as Map<String, dynamic>?;
    final oppDefensive = roundData['OpponentDefensive'] as Map<String, dynamic>?;
    final damage = roundData['Damage'] as Map<String, dynamic>?;

    if (charOffensive != null) {
      final action = charOffensive['Action'] as String? ?? 'Melee';
      final success = charOffensive['Success'] as bool? ?? false;
      final sigma = (charOffensive['Sigma'] as num?)?.toDouble() ?? 0.0;
      final opponentDamage = (damage?['OpponentTook'] as num?)?.toInt() ?? 0;

      // Get opponent's defensive action
      final defenseAction = oppDefensive?['Action'] as String?;
      final defenseSuccess = oppDefensive?['Success'] as bool?;

      final narrative = _generateAttackNarrative(
        action: action,
        success: success,
        sigma: sigma,
        damage: opponentDamage,
        attacker: characterName,
        defender: opponentName,
        defenseAction: defenseAction,
        defenseSuccess: defenseSuccess,
      );

      if (narrative.isNotEmpty) {
        narratives.add(narrative);
      }
    }

    // Opponent's offensive action
    final oppOffensive = roundData['OpponentOffensive'] as Map<String, dynamic>?;
    final charDefensive = roundData['CharacterDefensive'] as Map<String, dynamic>?;

    if (oppOffensive != null) {
      final action = oppOffensive['Action'] as String? ?? 'Melee';
      final success = oppOffensive['Success'] as bool? ?? false;
      final sigma = (oppOffensive['Sigma'] as num?)?.toDouble() ?? 0.0;
      final characterDamage = (damage?['CharacterTook'] as num?)?.toInt() ?? 0;

      // Get character's defensive action
      final defenseAction = charDefensive?['Action'] as String?;
      final defenseSuccess = charDefensive?['Success'] as bool?;

      final narrative = _generateAttackNarrative(
        action: action,
        success: success,
        sigma: sigma,
        damage: characterDamage,
        attacker: opponentName,
        defender: characterName,
        defenseAction: defenseAction,
        defenseSuccess: defenseSuccess,
      );

      if (narrative.isNotEmpty) {
        narratives.add(narrative);
      }
    }

    // Combine narratives
    if (narratives.isNotEmpty) {
      return '${narratives.join('. ')}.';
    }

    return 'The combatants exchange blows.';
  }

  /// Generate a narrative for a single attack action
  static String _generateAttackNarrative({
    required String action,
    required bool success,
    required double sigma,
    required int damage,
    required String attacker,
    required String defender,
    String? defenseAction,
    bool? defenseSuccess,
  }) {
    final templates = _offensiveTemplates[action];
    if (templates == null) return '';

    final successKey = success ? 'success' : 'failure';
    final templateList = templates[successKey];
    if (templateList == null || templateList.isEmpty) return '';

    final template = templateList[_random.nextInt(templateList.length)];

    // Get severity descriptor if attack was successful and dealt damage
    String severity = '';
    if (success && damage > 0) {
      severity = _getSeverityDescriptor(sigma, damage);
    }

    // Replace placeholders
    var narrative = template
        .replaceAll('{attacker}', attacker)
        .replaceAll('{defender}', defender)
        .replaceAll('{severity}', severity)
        .trim();

    // Clean up double spaces that might occur if severity was empty
    narrative = narrative.replaceAll(RegExp(r'\s+'), ' ');

    // Add defensive action flavor if available and defense succeeded
    if (!success && defenseAction != null && defenseSuccess == true) {
      final defenseText = _getDefenseText(defenseAction, defender);
      if (defenseText.isNotEmpty) {
        narrative = '$narrative $defenseText';
      }
    }

    return narrative;
  }

  /// Get descriptive text for successful defensive actions
  static String _getDefenseText(String defenseAction, String defender) {
    switch (defenseAction) {
      case 'Dodge':
        final dodgeTexts = [
          'as $defender nimbly sidesteps',
          'while $defender weaves away',
          'as $defender ducks aside',
          'while $defender evades with quick reflexes',
        ];
        return dodgeTexts[_random.nextInt(dodgeTexts.length)];
      case 'Parry':
        final parryTexts = [
          'as $defender parries expertly',
          'while $defender deflects with their weapon',
          'as $defender blocks skillfully',
          'while $defender turns the attack aside',
        ];
        return parryTexts[_random.nextInt(parryTexts.length)];
      default:
        return '';
    }
  }

  /// Get a descriptor for attack severity based on sigma and damage
  static String _getSeverityDescriptor(double sigma, int damage) {
    if (damage >= 2 || sigma > 3.0) {
      return _severityCritical[_random.nextInt(_severityCritical.length)];
    }
    return _severityNormal[_random.nextInt(_severityNormal.length)];
  }

  /// Check if an event is a combat event that should use narrative generation
  static bool isCombatEvent(Map<String, dynamic> event) {
    final eventType = event['EventType'] as String?;
    return eventType == 'combat' && event['Data'] is Map<String, dynamic>;
  }

  /// Generate narrative for a combat event, using character name if available
  static String generateEventNarrative(
    Map<String, dynamic> event, {
    String characterName = 'You',
    String? opponentName,
  }) {
    if (!isCombatEvent(event)) {
      return event['Description'] as String? ?? '';
    }

    final roundData = event['Data'] as Map<String, dynamic>;

    // Try to get opponent name from the event or use default
    final finalOpponentName = opponentName ?? 'the opponent';

    return generateNarrative(roundData, characterName, finalOpponentName);
  }
}
