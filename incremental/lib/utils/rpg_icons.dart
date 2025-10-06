import 'package:flutter/material.dart';
import 'package:fluttericon/rpg_awesome_icons.dart';

class RpgIcons {
  static IconData getEquipmentSlotIcon(String slot) {
    switch (slot.toLowerCase()) {
      case 'head':
      case 'helmet':
        return RpgAwesome.helmet;
      case 'chest':
      case 'armor':
      case 'body':
        return RpgAwesome.vest;
      case 'weapon':
      case 'main_hand':
      case 'mainhand':
        return RpgAwesome.axe;
      case 'off_hand':
      case 'offhand':
      case 'shield':
        return RpgAwesome.shield;
      case 'ring':
      case 'ring1':
      case 'ring2':
      case 'finger':
        return RpgAwesome.diamond;
      case 'neck':
      case 'amulet':
        return RpgAwesome.gem;
      case 'back':
      case 'cloak':
        return RpgAwesome.vest;
      case 'boots':
      case 'feet':
        return RpgAwesome.footprint;
      case 'gloves':
      case 'hands':
        return RpgAwesome.hand;
      case 'belt':
      case 'waist':
        return RpgAwesome.vest;
      default:
        return RpgAwesome.daggers;
    }
  }

  static IconData getItemTypeIcon(String type) {
    switch (type.toLowerCase()) {
      case 'weapon':
        return RpgAwesome.axe;
      case 'armor':
        return RpgAwesome.vest;
      case 'potion':
        return RpgAwesome.potion;
      case 'scroll':
        return RpgAwesome.scroll_unfurled;
      case 'ring':
        return RpgAwesome.diamond;
      case 'amulet':
        return RpgAwesome.gem;
      case 'consumable':
      case 'food':
        return RpgAwesome.meat;
      case 'material':
      case 'component':
        return RpgAwesome.crystal_wand;
      case 'key':
        return RpgAwesome.key;
      case 'book':
        return RpgAwesome.book;
      case 'container':
      case 'bag':
        return RpgAwesome.key;
      default:
        return Icons.paid;
    }
  }

  static IconData getAttributeIcon(String attribute) {
    switch (attribute.toLowerCase()) {
      case 'strength':
        return RpgAwesome.muscle_up;
      case 'agility':
      case 'dexterity':
        return Icons.flash_on;
      case 'endurance':
      case 'constitution':
        return Icons.directions_run;
      case 'intelligence':
        return Icons.psychology;
      case 'wisdom':
        return Icons.auto_awesome;
      case 'charisma':
        return Icons.chat;
      case 'presence':
        return RpgAwesome.aura;
      case 'intrigue':
        return RpgAwesome.hood;
      case 'cunning':
        return Icons.record_voice_over;
      case 'perception':
        return Icons.visibility;
      default:
        return RpgAwesome.double_team;
    }
  }

  static IconData getSkillIcon(String skill) {
    switch (skill.toLowerCase()) {
      case 'melee':
        return RpgAwesome.broadsword;
      case 'archery':
      case 'ranged':
      case 'bow':
        return RpgAwesome.crossbow;
      case 'brawling':
      case 'unarmed':
        return Icons.sports_martial_arts;
      case 'dodge':
        return RpgAwesome.player_dodge;
      case 'parry':
        return RpgAwesome.crossed_swords;
      case 'stealth':
        return Icons.visibility_off;
      case 'investigation':
      case 'perception':
        return Icons.hearing;
      case 'tumbling':
      case 'acrobatics':
        return Icons.sports_gymnastics;
      case 'climbing':
        return Icons.terrain;
      case 'lockpicking':
      case 'lockpick':
        return RpgAwesome.key;
      case 'mythos':
      case 'lore':
        return RpgAwesome.book;
      case 'arcane':
      case 'magic':
        return Icons.blur_circular;
      case 'firstaid':
      case 'first_aid':
      case 'healing':
        return RpgAwesome.health;
      case 'foraging':
      case 'survival':
        return RpgAwesome.leaf;
      case 'appraise':
      case 'merchant':
        return Icons.balance;
      case 'crafting':
        return RpgAwesome.hammer;
      default:
        return RpgAwesome.quill_ink;
    }
  }

  static IconData getResourceIcon(String resource) {
    switch (resource.toLowerCase()) {
      case 'gold':
      case 'coins':
      case 'money':
        return RpgAwesome.gold_bar;
      case 'experience':
      case 'xp':
        return RpgAwesome.burning_book;
      case 'reputation':
      case 'fame':
        return RpgAwesome.crown;
      case 'health':
        return RpgAwesome.health;
      case 'essence':
      case 'mana':
      case 'magic':
        return RpgAwesome.water_drop;
      default:
        return RpgAwesome.book;
    }
  }

  static IconData getCombatIcon(String eventType) {
    switch (eventType.toLowerCase()) {
      case 'combat':
        return RpgAwesome.crossed_swords;
      case 'attack':
      case 'combatattack':
        return RpgAwesome.axe;
      case 'defense':
      case 'combatdefense':
        return RpgAwesome.shield;
      case 'damage':
      case 'combatdamage':
        return RpgAwesome.health_decrease;
      case 'victory':
      case 'combatvictory':
        return RpgAwesome.trophy;
      case 'defeat':
      case 'combatdefeat':
        return RpgAwesome.skull;
      case 'critical':
      case 'crit':
        return RpgAwesome.doubled;
      default:
        return RpgAwesome.crossed_swords;
    }
  }

  static IconData getStoryIcon(String storyType) {
    switch (storyType.toLowerCase()) {
      case 'quest':
      case 'mission':
        return RpgAwesome.scroll_unfurled;
      case 'daily':
        return RpgAwesome.sun;
      case 'single':
      case 'one_time':
        return RpgAwesome.bleeding_eye;
      case 'repeatable':
      case 'recurring':
        return RpgAwesome.cycle;
      case 'completed':
      case 'success':
        return RpgAwesome.crown;
      case 'failed':
      case 'defeat':
        return RpgAwesome.skull;
      case 'active':
      case 'current':
        return RpgAwesome.burning_book;
      default:
        return RpgAwesome.quill_ink;
    }
  }

  static IconData getStatusIcon(String status) {
    switch (status.toLowerCase()) {
      case 'success':
      case 'completed':
        return RpgAwesome.trophy;
      case 'failed':
      case 'failure':
        return RpgAwesome.skull;
      case 'warning':
      case 'caution':
        return RpgAwesome.lightning_bolt;
      case 'death':
      case 'dead':
        return RpgAwesome.skull;
      case 'wounded':
      case 'injured':
        return RpgAwesome.health_decrease;
      case 'poisoned':
        return RpgAwesome.flask;
      case 'blessed':
      case 'buff':
        return RpgAwesome.sun;
      case 'cursed':
      case 'debuff':
        return RpgAwesome.skull;
      default:
        return RpgAwesome.perspective_dice_six;
    }
  }

  static IconData getWeaponTypeIcon(String weaponType) {
    switch (weaponType.toLowerCase()) {
      case 'sword':
      case 'longsword':
        return RpgAwesome.broadsword;
      case 'dagger':
      case 'knife':
        return RpgAwesome.daggers;
      case 'axe':
      case 'greataxe':
        return RpgAwesome.axe;
      case 'mace':
      case 'club':
        return RpgAwesome.hammer;
      case 'bow':
        return RpgAwesome.crossbow;
      case 'staff':
      case 'quarterstaff':
        return RpgAwesome.crystal_wand;
      case 'hammer':
        return RpgAwesome.hammer;
      default:
        return RpgAwesome.axe;
    }
  }

  static IconData getArmorTypeIcon(String armorType) {
    switch (armorType.toLowerCase()) {
      case 'heavy':
      case 'plate':
        return RpgAwesome.vest;
      case 'medium':
      case 'chainmail':
        return RpgAwesome.vest;
      case 'light':
      case 'leather':
        return RpgAwesome.vest;
      case 'robe':
      case 'cloth':
        return RpgAwesome.vest;
      default:
        return RpgAwesome.vest;
    }
  }
}
