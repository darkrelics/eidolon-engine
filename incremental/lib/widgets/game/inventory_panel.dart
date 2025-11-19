import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/utils/rpg_icons.dart';
import 'package:eidolon_incremental/repositories/item_repository.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:eidolon_incremental/services/base_api_service.dart';
import 'package:fluttericon/rpg_awesome_icons.dart';

/// Right panel displaying character inventory with enriched item data
class InventoryPanel extends StatefulWidget {
  final Character character;
  final Function(String itemId)? onItemTap;
  final Future<void> Function()? onRefresh;

  const InventoryPanel({
    super.key,
    required this.character,
    this.onItemTap,
    this.onRefresh,
  });

  @override
  State<InventoryPanel> createState() => _InventoryPanelState();
}

class _InventoryPanelState extends State<InventoryPanel> {
  ItemRepository? _itemRepository;
  ApiService? _apiService;
  Map<String, Map<String, dynamic>> _enrichedInventory = {};
  bool _isLoading = true;
  String? _errorMessage;
  final Set<String> _processingItems = <String>{};

  @override
  void initState() {
    super.initState();
    _initializeRepository();
  }

  void _initializeRepository() async {
    try {
      final authService = AuthService.instance;
      final apiService = ApiService(authService: authService);
      _apiService = apiService;
      _itemRepository = ItemRepository(apiService: apiService);

      // Load enriched inventory
      await _loadInventoryDetails();
    } catch (e) {
      debugPrint('InventoryPanel: Error initializing repository: $e');
      setState(() {
        _errorMessage = 'Failed to initialize inventory';
        _isLoading = false;
      });
    }
  }

  @override
  void didUpdateWidget(covariant InventoryPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!mapEquals(widget.character.inventory, oldWidget.character.inventory)) {
      _loadInventoryDetails();
    }
  }

  Future<void> _loadInventoryDetails() async {
    if (_itemRepository == null) {
      setState(() {
        _isLoading = false;
      });
      return;
    }

    try {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
      final enriched = await _itemRepository!.loadInventoryDetails(widget.character.inventory);
      setState(() {
        _enrichedInventory = enriched;
        _isLoading = false;
      });
    } catch (e) {
      debugPrint('InventoryPanel: Error loading inventory details: $e');
      setState(() {
        _errorMessage = 'Failed to load item details';
        _isLoading = false;
      });
    }
  }

  /// Extract ItemID from inventory value
  String _getItemId(dynamic value) {
    if (value is Map<String, dynamic>) {
      return value['ItemID'] as String? ?? '';
    }
    return '';
  }

  /// Get quantity from inventory value
  /// Returns the actual quantity for stackable items, or 0 for non-stackable items (no Quantity field)
  int _getQuantity(dynamic value) {
    if (value is Map<String, dynamic>) {
      // If Quantity field exists, use it (stackable item)
      // If Quantity field missing, return 0 (non-stackable item)
      return value['Quantity'] as int? ?? 0;
    }
    return 0;
  }

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
                if (_isLoading)
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        colorScheme.onPrimaryContainer,
                      ),
                    ),
                  )
                else if (widget.character.inventory.isNotEmpty)
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
                      '${widget.character.inventory.length} items',
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
            child: _isLoading
                ? _buildLoadingState(context)
                : _errorMessage != null
                    ? _buildErrorState(context)
                    : widget.character.inventory.isEmpty
                        ? _buildEmptyInventory(context)
                        : _buildInventoryGrid(context),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingState(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Loading inventory...'),
        ],
      ),
    );
  }

  Widget _buildErrorState(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.error_outline,
            size: 64,
            color: colorScheme.error,
          ),
          const SizedBox(height: 16),
          Text(
            _errorMessage ?? 'Failed to load inventory',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: colorScheme.error,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _loadInventoryDetails,
            child: const Text('Retry'),
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
    final equippedItems = <String, MapEntry<String, dynamic>>{};
    final unequippedItems = <MapEntry<String, dynamic>>[];

    for (final entry in widget.character.inventory.entries) {
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
              (equipped) {
                final itemId = _getItemId(equipped.value.value);
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _InventorySlot(
                    slot: equipped.key,
                    itemId: itemId,
                    itemDetails: _getEnrichedItemDetails(equipped.key),
                    quantity: _getQuantity(equipped.value.value),
                    isEquipped: true,
                    onTap: widget.onItemTap != null
                        ? () => widget.onItemTap!(itemId)
                        : null,
                  ),
                );
              },
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
                final itemId = _getItemId(item.value);
                final slotKey = item.key;
                final itemDetails = _getEnrichedItemDetails(slotKey);
                final isConsumable = _isConsumable(itemDetails);
                return _InventoryGridItem(
                  slot: slotKey,
                  itemId: itemId,
                  itemDetails: itemDetails,
                  quantity: _getQuantity(item.value),
                  isConsumable: isConsumable,
                  isProcessing: _isItemProcessing(itemId),
                  onUse: isConsumable ? () => _handleUseItem(slotKey, itemId) : null,
                  onTap: widget.onItemTap != null
                      ? () => widget.onItemTap!(itemId)
                      : null,
                );
              },
            ),
          ],
        ],
      ),
    );
  }

  /// Get enriched item details from loaded inventory
  Map<String, dynamic>? _getEnrichedItemDetails(String slot) {
    return _enrichedInventory[slot];
  }

  bool _isConsumable(Map<String, dynamic>? details) {
    if (details == null) {
      return false;
    }
    final consumable = details['Consumable'];
    if (consumable is bool) {
      return consumable;
    }
    return false;
  }

  bool _isItemProcessing(String itemId) => _processingItems.contains(itemId);

  void _showSnackBar(String message, {bool isError = false}) {
    if (!mounted) {
      return;
    }

    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Future<void> _handleUseItem(String slot, String itemId) async {
    if (_apiService == null || _processingItems.contains(itemId)) {
      return;
    }

    setState(() {
      _processingItems.add(itemId);
    });

    try {
      final result = await _apiService!.consumeItem(
        characterId: widget.character.id,
        itemId: itemId,
      );

      final remainingQuantity = (result['remainingQuantity'] as num?)?.toInt() ?? 0;
      final itemRemoved = result['itemRemoved'] as bool? ?? remainingQuantity <= 0;
      final message = result['message'] as String? ?? 'Item consumed.';

      final slotsToUpdate = widget.character.inventory.entries
          .where((entry) => entry.value is Map && entry.value['ItemID'] == itemId)
          .map((entry) => entry.key)
          .toList();

      if (slotsToUpdate.isEmpty) {
        slotsToUpdate.add(slot);
      }

      for (final slotKey in slotsToUpdate) {
        if (itemRemoved) {
          widget.character.inventory.remove(slotKey);
          widget.character.inventoryDetails.remove(slotKey);
          _enrichedInventory.remove(slotKey);
        } else {
          final slotValue = widget.character.inventory[slotKey];
          if (slotValue is Map<String, dynamic>) {
            slotValue['Quantity'] = remainingQuantity;
          } else {
            widget.character.inventory[slotKey] = {'ItemID': itemId, 'Quantity': remainingQuantity};
          }

          final details = _enrichedInventory[slotKey];
          if (details != null) {
            details['Quantity'] = remainingQuantity;
          }

          final detailInventory = widget.character.inventoryDetails[slotKey];
          if (detailInventory is Map<String, dynamic>) {
            detailInventory['Quantity'] = remainingQuantity;
          }
        }
      }

      if (mounted) {
        setState(() {});
        _showSnackBar(message);
      }

      if (widget.onRefresh != null) {
        await widget.onRefresh!();
      }
    } on ApiException catch (err) {
      final errorMessage = err.message.isNotEmpty ? err.message : 'Failed to consume item.';
      _showSnackBar(errorMessage, isError: true);
    } catch (err) {
      _showSnackBar('Unexpected error: $err', isError: true);
    } finally {
      if (mounted) {
        setState(() {
          _processingItems.remove(itemId);
        });
      }
    }
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
  final int quantity;
  final bool isEquipped;
  final VoidCallback? onTap;

  const _InventorySlot({
    required this.slot,
    required this.itemId,
    this.itemDetails,
    this.quantity = 1,
    this.isEquipped = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    final itemName = itemDetails?['Name'] ?? itemId;
    final itemRarity = itemDetails?['Rarity'] ?? 'common';
    final isStackable = itemDetails?['Stackable'] == true;

    // Format: "Item Name" or "Item Name x5" for stackable items
    final displayName = (isStackable && quantity > 1)
        ? '$itemName x$quantity'
        : itemName;

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
                displayName,
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
  final String slot;
  final String itemId;
  final Map<String, dynamic>? itemDetails;
  final int quantity;
  final VoidCallback? onTap;
  final VoidCallback? onUse;
  final bool isConsumable;
  final bool isProcessing;

  const _InventoryGridItem({
    required this.slot,
    required this.itemId,
    this.itemDetails,
    this.quantity = 1,
    this.onTap,
    this.onUse,
    this.isConsumable = false,
    this.isProcessing = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    final itemRarity = itemDetails?['Rarity'] ?? 'common';
    final isStackable = itemDetails?['Stackable'] == true;
    final itemName = itemDetails?['Name'] as String? ?? itemId;
    final tooltipText = slot.isNotEmpty ? '$itemName ($slot)' : itemName;

    return Tooltip(
      message: tooltipText,
      child: InkWell(
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
          child: Stack(
            children: [
              Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      _getItemIcon(itemDetails?['Type'] ?? 'item'),
                      size: 24,
                      color: _getRarityColor(itemRarity),
                    ),
                    const SizedBox(height: 4),
                    if (isStackable && quantity > 1)
                      Text(
                        'x$quantity',
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                  ],
                ),
              ),
              if (isConsumable)
                Positioned(
                  right: 0,
                  top: 0,
                  child: IconButton(
                    tooltip: 'Use $itemName',
                    onPressed: isProcessing ? null : onUse,
                    style: IconButton.styleFrom(
                      backgroundColor: colorScheme.primaryContainer,
                      foregroundColor: colorScheme.onPrimaryContainer,
                      padding: const EdgeInsets.all(4),
                      minimumSize: const Size(28, 28),
                    ),
                    icon: isProcessing
                        ? SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(
                                colorScheme.onPrimaryContainer,
                              ),
                            ),
                          )
                        : const Icon(Icons.play_arrow_rounded, size: 16),
                  ),
                ),
            ],
          ),
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
