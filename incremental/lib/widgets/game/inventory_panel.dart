import 'package:flutter/material.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/utils/rpg_icons.dart';
import 'package:fluttericon/rpg_awesome_icons.dart';

/// Right panel displaying character inventory
class InventoryPanel extends StatelessWidget {
  final Character character;
  final Function(String itemId)? onItemTap;

  const InventoryPanel({super.key, required this.character, this.onItemTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Card(
      margin: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: colorScheme.primaryContainer,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(12),
                topRight: Radius.circular(12),
              ),
            ),
            child: Row(
              children: [
                Icon(Icons.inventory_2, color: colorScheme.onPrimaryContainer),
                const SizedBox(width: 8),
                Text(
                  'Inventory',
                  style: theme.textTheme.titleLarge?.copyWith(
                    color: colorScheme.onPrimaryContainer,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                if (character.inventory.isNotEmpty)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: colorScheme.onPrimaryContainer.withValues(
                        alpha: 0.2,
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${character.inventory.length} items',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: colorScheme.onPrimaryContainer,
                      ),
                    ),
                  ),
              ],
            ),
          ),

          // Content
          Expanded(
            child: character.inventory.isEmpty
                ? _buildEmptyInventory(context)
                : _buildInventoryGrid(context),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyInventory(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.inventory_2,
            size: 64,
            color: colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
          ),
          const SizedBox(height: 16),
          Text(
            'No Items',
            style: theme.textTheme.titleMedium?.copyWith(
              color: colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Items you acquire will appear here',
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInventoryGrid(BuildContext context) {
    // Group items by slot type
    final equippedItems = <String, MapEntry<String, String>>{};
    final unequippedItems = <MapEntry<String, String>>[];

    for (final entry in character.inventory.entries) {
      if (_isEquipmentSlot(entry.key)) {
        equippedItems[entry.key] = entry;
      } else {
        unequippedItems.add(entry);
      }
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Equipped Items Section
          if (equippedItems.isNotEmpty) ...[
            _SectionHeader(title: 'Equipped'),
            const SizedBox(height: 12),
            ...equippedItems.entries.map(
              (equipped) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: _InventorySlot(
                  slot: equipped.key,
                  itemId: equipped.value.value,
                  itemDetails: _getItemDetails(equipped.value.value),
                  isEquipped: true,
                  onTap: onItemTap != null
                      ? () => onItemTap!(equipped.value.value)
                      : null,
                ),
              ),
            ),
            const SizedBox(height: 20),
          ],

          // Bag/Unequipped Items Section
          if (unequippedItems.isNotEmpty) ...[
            _SectionHeader(title: 'Bag'),
            const SizedBox(height: 12),
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 4,
                crossAxisSpacing: 8,
                mainAxisSpacing: 8,
                childAspectRatio: 1,
              ),
              itemCount: unequippedItems.length,
              itemBuilder: (context, index) {
                final item = unequippedItems[index];
                return _InventoryGridItem(
                  itemId: item.value,
                  itemDetails: _getItemDetails(item.value),
                  onTap: onItemTap != null
                      ? () => onItemTap!(item.value)
                      : null,
                );
              },
            ),
          ],
        ],
      ),
    );
  }

  bool _isEquipmentSlot(String slot) {
    const equipmentSlots = [
      'head',
      'helmet',
      'chest',
      'armor',
      'body',
      'legs',
      'pants',
      'feet',
      'boots',
      'shoes',
      'hands',
      'gloves',
      'weapon',
      'main_hand',
      'mainhand',
      'off_hand',
      'offhand',
      'shield',
      'neck',
      'amulet',
      'ring',
      'ring1',
      'ring2',
      'back',
      'cloak',
      'cape',
    ];
    return equipmentSlots.contains(slot.toLowerCase());
  }

  Map<String, dynamic>? _getItemDetails(String itemId) {
    // Get item details from inventoryDetails if available
    if (character.inventoryDetails.isNotEmpty) {
      for (final details in character.inventoryDetails.values) {
        if (details is Map<String, dynamic> && details['ItemID'] == itemId) {
          return details;
        }
      }
    }
    return null;
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;

  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: theme.colorScheme.primary, width: 2),
        ),
      ),
      child: Text(
        title,
        style: theme.textTheme.titleSmall?.copyWith(
          fontWeight: FontWeight.bold,
          color: theme.colorScheme.primary,
        ),
      ),
    );
  }
}

class _InventorySlot extends StatelessWidget {
  final String slot;
  final String itemId;
  final Map<String, dynamic>? itemDetails;
  final bool isEquipped;
  final VoidCallback? onTap;

  const _InventorySlot({
    required this.slot,
    required this.itemId,
    this.itemDetails,
    this.isEquipped = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    final itemName = itemDetails?['Name'] ?? itemId;
    final itemRarity = itemDetails?['Rarity'] ?? 'common';

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: isEquipped
              ? colorScheme.primaryContainer.withValues(alpha: 0.3)
              : colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: _getRarityColor(itemRarity).withValues(alpha: 0.5),
            width: 2,
          ),
        ),
        child: Row(
          children: [
            Icon(
              _getSlotIcon(slot),
              size: 20,
              color: colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: 8),
            Text(
              _formatSlotName(slot),
              style: theme.textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                itemName,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: _getRarityColor(itemRarity),
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (isEquipped)
              Icon(RpgAwesome.doubled, size: 16, color: colorScheme.primary),
          ],
        ),
      ),
    );
  }

  String _formatSlotName(String slot) {
    return slot
        .replaceAll('_', ' ')
        .split(' ')
        .map((word) => word[0].toUpperCase() + word.substring(1))
        .join(' ');
  }

  IconData _getSlotIcon(String slot) {
    return RpgIcons.getEquipmentSlotIcon(slot);
  }

  Color _getRarityColor(String rarity) {
    switch (rarity.toLowerCase()) {
      case 'legendary':
        return Colors.orange;
      case 'epic':
        return Colors.purple;
      case 'rare':
        return Colors.blue;
      case 'uncommon':
        return Colors.green;
      case 'common':
      default:
        return Colors.grey;
    }
  }
}

class _InventoryGridItem extends StatelessWidget {
  final String itemId;
  final Map<String, dynamic>? itemDetails;
  final VoidCallback? onTap;

  const _InventoryGridItem({
    required this.itemId,
    this.itemDetails,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    final itemRarity = itemDetails?['Rarity'] ?? 'common';
    final itemQuantity = itemDetails?['Quantity'] ?? 1;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: _getRarityColor(itemRarity).withValues(alpha: 0.5),
            width: 2,
          ),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              _getItemIcon(itemDetails?['Type'] ?? 'item'),
              size: 24,
              color: _getRarityColor(itemRarity),
            ),
            const SizedBox(height: 4),
            if (itemQuantity > 1)
              Text(
                'x$itemQuantity',
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
          ],
        ),
      ),
    );
  }

  IconData _getItemIcon(String type) {
    return RpgIcons.getItemTypeIcon(type);
  }

  Color _getRarityColor(String rarity) {
    switch (rarity.toLowerCase()) {
      case 'legendary':
        return Colors.orange;
      case 'epic':
        return Colors.purple;
      case 'rare':
        return Colors.blue;
      case 'uncommon':
        return Colors.green;
      case 'common':
      default:
        return Colors.grey;
    }
  }
}
