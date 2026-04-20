import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/utils/json_parser.dart';
import 'package:eidolon_incremental/utils/rpg_icons.dart';
import 'package:eidolon_incremental/repositories/item_repository.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/services/auth_service.dart';
import 'package:eidolon_incremental/services/base_api_service.dart';
import 'package:fluttericon/rpg_awesome_icons.dart';

/// Right-hand panel showing the character's carried items.
///
/// Data model: the character is the base container. Its `contents` list holds
/// ItemIDs the character carries directly; each container item carries its
/// own `Contents` list. This widget renders an Equipped section, one section
/// per container (recursively for nested containers), and a Loose section
/// for remaining leaf items at the character root.
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
    if (!listEquals(widget.character.contents, oldWidget.character.contents)) {
      _loadInventoryDetails();
    }
  }

  Future<void> _loadInventoryDetails() async {
    if (_itemRepository == null) {
      setState(() => _isLoading = false);
      return;
    }

    try {
      setState(() {
        _isLoading = true;
        _errorMessage = null;
      });
      final enriched = await _itemRepository!.loadInventoryDetails(widget.character.contents);
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

  bool _isWorn(Map<String, dynamic>? details) {
    if (details == null) return false;
    final worn = details['IsWorn'] ?? details['Equipped'];
    return worn == true;
  }

  bool _isContainer(Map<String, dynamic>? details) {
    if (details == null) return false;
    return details['Container'] == true;
  }

  bool _isConsumable(Map<String, dynamic>? details) {
    if (details == null) return false;
    final consumable = details['Consumable'];
    return consumable is bool ? consumable : false;
  }

  int _quantity(Map<String, dynamic>? details) {
    if (details == null) return 0;
    return JsonParser.getInt(details, 'Quantity');
  }

  bool _isItemProcessing(String itemId) => _processingItems.contains(itemId);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Card(
      margin: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
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
                else if (widget.character.contents.isNotEmpty) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: colorScheme.onPrimaryContainer.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${widget.character.contents.length} items',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: colorScheme.onPrimaryContainer,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton(
                    icon: const Icon(Icons.compress),
                    iconSize: 18,
                    tooltip: 'Consolidate stacks',
                    style: IconButton.styleFrom(
                      foregroundColor: colorScheme.onPrimaryContainer,
                      padding: const EdgeInsets.all(4),
                      minimumSize: const Size(28, 28),
                    ),
                    onPressed: _handleConsolidateStacks,
                  ),
                ],
              ],
            ),
          ),
          Expanded(
            child: _isLoading
                ? _buildLoadingState(context)
                : _errorMessage != null
                    ? _buildErrorState(context)
                    : widget.character.contents.isEmpty
                        ? _buildEmptyInventory(context)
                        : _buildInventoryBody(context),
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
          Icon(Icons.error_outline, size: 64, color: colorScheme.error),
          const SizedBox(height: 16),
          Text(
            _errorMessage ?? 'Failed to load inventory',
            style: theme.textTheme.bodyMedium?.copyWith(color: colorScheme.error),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          ElevatedButton(onPressed: _loadInventoryDetails, child: const Text('Retry')),
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
          Text('No Items',
              style: theme.textTheme.titleMedium?.copyWith(color: colorScheme.onSurfaceVariant)),
          const SizedBox(height: 8),
          Text('Items you acquire will appear here',
              style: theme.textTheme.bodySmall?.copyWith(color: colorScheme.onSurfaceVariant)),
        ],
      ),
    );
  }

  Widget _buildInventoryBody(BuildContext context) {
    final equippedIds = <String>[];
    final containerIds = <String>[];
    final looseIds = <String>[];

    for (final itemId in widget.character.contents) {
      final details = _enrichedInventory[itemId];
      if (_isWorn(details)) {
        equippedIds.add(itemId);
      } else if (_isContainer(details)) {
        containerIds.add(itemId);
      } else {
        looseIds.add(itemId);
      }
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (equippedIds.isNotEmpty) ...[
            _SectionHeader(title: 'Equipped'),
            const SizedBox(height: 12),
            for (final itemId in equippedIds)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: _InventorySlot(
                  itemId: itemId,
                  itemDetails: _enrichedInventory[itemId],
                  quantity: _quantity(_enrichedInventory[itemId]),
                  isEquipped: true,
                  onTap: widget.onItemTap != null ? () => widget.onItemTap!(itemId) : null,
                ),
              ),
            const SizedBox(height: 20),
          ],
          for (final containerId in containerIds) ...[
            _buildContainerSection(context, containerId, depth: 0, visited: const <String>{}),
            const SizedBox(height: 20),
          ],
          if (looseIds.isNotEmpty) ...[
            _SectionHeader(title: 'Loose'),
            const SizedBox(height: 12),
            _buildItemGrid(context, looseIds),
          ],
        ],
      ),
    );
  }

  /// Render a container and its Contents. Nested containers are rendered
  /// recursively with increasing left indentation. ``visited`` guards against
  /// cycles; the container id is added before recursing into children.
  Widget _buildContainerSection(
    BuildContext context,
    String containerId, {
    required int depth,
    required Set<String> visited,
  }) {
    if (visited.contains(containerId)) {
      return const SizedBox.shrink();
    }
    final nextVisited = <String>{...visited, containerId};

    final details = _enrichedInventory[containerId];
    final containerName = details?['Name'] as String? ?? 'Container';
    final contents = details?['Contents'];
    final childLeafIds = <String>[];
    final childContainerIds = <String>[];
    if (contents is List) {
      for (final x in contents) {
        if (x is String && _enrichedInventory.containsKey(x)) {
          final childDetails = _enrichedInventory[x];
          if (_isContainer(childDetails)) {
            childContainerIds.add(x);
          } else {
            childLeafIds.add(x);
          }
        }
      }
    }

    final theme = Theme.of(context);
    final isNested = depth > 0;

    final sectionContent = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SectionHeader(title: containerName),
        const SizedBox(height: 12),
        if (childLeafIds.isEmpty && childContainerIds.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
            child: Text(
              'Empty',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                fontStyle: FontStyle.italic,
              ),
            ),
          )
        else ...[
          if (childLeafIds.isNotEmpty) _buildItemGrid(context, childLeafIds),
          for (final nestedId in childContainerIds) ...[
            const SizedBox(height: 16),
            _buildContainerSection(
              context,
              nestedId,
              depth: depth + 1,
              visited: nextVisited,
            ),
          ],
        ],
      ],
    );

    if (!isNested) return sectionContent;

    return Padding(
      padding: const EdgeInsets.only(left: 12),
      child: Container(
        padding: const EdgeInsets.only(left: 8),
        decoration: BoxDecoration(
          border: Border(
            left: BorderSide(
              color: theme.colorScheme.primary.withValues(alpha: 0.3),
              width: 2,
            ),
          ),
        ),
        child: sectionContent,
      ),
    );
  }

  Widget _buildItemGrid(BuildContext context, List<String> itemIds) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 4,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
        childAspectRatio: 0.85,
      ),
      itemCount: itemIds.length,
      itemBuilder: (context, index) {
        final itemId = itemIds[index];
        final details = _enrichedInventory[itemId];
        final qty = _quantity(details);
        final isStackable = details?['Stackable'] == true;
        final isConsumable = _isConsumable(details);
        final itemName = details?['Name'] as String? ?? 'Item';

        return _InventoryGridItem(
          itemId: itemId,
          itemDetails: details,
          quantity: qty,
          isConsumable: isConsumable,
          isStackable: isStackable,
          isProcessing: _isItemProcessing(itemId),
          onUse: isConsumable ? () => _handleUseItem(itemId) : null,
          onDiscard: () => _showDiscardDialog(itemId, itemName, qty, isStackable),
          onSplit: isStackable && qty > 1 ? () => _showSplitDialog(itemId, itemName, qty) : null,
          onTap: widget.onItemTap != null ? () => widget.onItemTap!(itemId) : null,
        );
      },
    );
  }

  void _showSnackBar(String message, {bool isError = false}) {
    if (!mounted) return;
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

  Future<void> _handleUseItem(String itemId) async {
    if (_apiService == null || _processingItems.contains(itemId)) return;
    setState(() => _processingItems.add(itemId));

    try {
      final result = await _apiService!.consumeItem(
        characterId: widget.character.id,
        itemId: itemId,
      );

      final remainingQuantity = JsonParser.getInt(result, 'remainingQuantity');
      final itemRemoved = JsonParser.getBool(result, 'itemRemoved', defaultValue: remainingQuantity <= 0);
      final message = JsonParser.getString(result, 'message', defaultValue: 'Item consumed.');

      if (itemRemoved) {
        widget.character.contents.remove(itemId);
        _enrichedInventory.remove(itemId);
        _removeFromContainerContents(itemId);
      } else {
        final details = _enrichedInventory[itemId];
        if (details != null) details['Quantity'] = remainingQuantity;
      }

      if (mounted) {
        setState(() {});
        _showSnackBar(message);
      }
      if (widget.onRefresh != null) await widget.onRefresh!();
    } on ApiException catch (err) {
      final errorMessage = err.message.isNotEmpty ? err.message : 'Failed to consume item.';
      _showSnackBar(errorMessage, isError: true);
      if (err.statusCode == 409 && widget.onRefresh != null) await widget.onRefresh!();
    } catch (err) {
      _showSnackBar('Unexpected error: $err', isError: true);
    } finally {
      if (mounted) setState(() => _processingItems.remove(itemId));
    }
  }

  Future<void> _handleDiscardItem(String itemId, {int? quantity}) async {
    if (_apiService == null || _processingItems.contains(itemId)) return;
    setState(() => _processingItems.add(itemId));

    try {
      final result = await _apiService!.discardItem(
        characterId: widget.character.id,
        itemId: itemId,
        quantity: quantity,
      );

      final itemFullyDiscarded = JsonParser.getBool(result, 'ItemFullyDiscarded', defaultValue: true);
      final remainingQuantity = JsonParser.getInt(result, 'RemainingQuantity');
      final quantityDiscarded = JsonParser.getInt(result, 'QuantityDiscarded', defaultValue: quantity ?? 1);

      if (itemFullyDiscarded) {
        widget.character.contents.remove(itemId);
        _enrichedInventory.remove(itemId);
        _removeFromContainerContents(itemId);
      } else {
        final details = _enrichedInventory[itemId];
        if (details != null) details['Quantity'] = remainingQuantity;
      }

      if (mounted) {
        setState(() {});
        _showSnackBar('Discarded $quantityDiscarded item(s)');
      }
      if (widget.onRefresh != null) await widget.onRefresh!();
    } on ApiException catch (err) {
      final errorMessage = err.message.isNotEmpty ? err.message : 'Failed to discard item.';
      _showSnackBar(errorMessage, isError: true);
      if (err.statusCode == 409 && widget.onRefresh != null) await widget.onRefresh!();
    } catch (err) {
      _showSnackBar('Unexpected error: $err', isError: true);
    } finally {
      if (mounted) setState(() => _processingItems.remove(itemId));
    }
  }

  /// Drop ``itemId`` from any container's cached Contents so the UI doesn't
  /// keep rendering a discarded item until the next full refresh.
  void _removeFromContainerContents(String itemId) {
    for (final entry in _enrichedInventory.values) {
      final contents = entry['Contents'];
      if (contents is List) {
        contents.remove(itemId);
      }
    }
  }

  Future<void> _handleConsolidateStacks() async {
    if (_apiService == null) return;
    setState(() => _isLoading = true);
    try {
      final result = await _apiService!.consolidateStacks(
        characterId: widget.character.id,
        consolidateAll: true,
      );
      final totalStacksRemoved = JsonParser.getInt(result, 'TotalStacksRemoved');
      final message = JsonParser.getString(
        result,
        'Message',
        defaultValue: totalStacksRemoved > 0
            ? 'Consolidated $totalStacksRemoved stack(s)'
            : 'Nothing to consolidate',
      );
      if (mounted) _showSnackBar(message);
      if (widget.onRefresh != null) await widget.onRefresh!();
    } on ApiException catch (err) {
      final errorMessage = err.message.isNotEmpty ? err.message : 'Failed to consolidate stacks.';
      _showSnackBar(errorMessage, isError: true);
      if (err.statusCode == 409 && widget.onRefresh != null) await widget.onRefresh!();
    } catch (err) {
      _showSnackBar('Unexpected error: $err', isError: true);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showDiscardDialog(String itemId, String itemName, int quantity, bool isStackable) {
    if (!isStackable || quantity <= 1) {
      showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Discard Item'),
          content: Text('Discard $itemName?'),
          actions: [
            TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
            TextButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Discard')),
          ],
        ),
      ).then((confirmed) {
        if (confirmed == true) _handleDiscardItem(itemId);
      });
      return;
    }

    int discardQuantity = 1;
    showDialog<int>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Discard Items'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('How many $itemName to discard?'),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: discardQuantity > 1 ? () => setDialogState(() => discardQuantity--) : null,
                    icon: const Icon(Icons.remove),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      border: Border.all(color: Theme.of(context).colorScheme.outline),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text('$discardQuantity', style: Theme.of(context).textTheme.titleLarge),
                  ),
                  IconButton(
                    onPressed: discardQuantity < quantity ? () => setDialogState(() => discardQuantity++) : null,
                    icon: const Icon(Icons.add),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => setDialogState(() => discardQuantity = quantity),
                child: const Text('Discard All'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context).pop(null), child: const Text('Cancel')),
            TextButton(
              onPressed: () => Navigator.of(context).pop(discardQuantity),
              child: const Text('Discard'),
            ),
          ],
        ),
      ),
    ).then((qty) {
      if (qty != null && qty > 0) _handleDiscardItem(itemId, quantity: qty);
    });
  }

  Future<void> _handleSplitStack(String itemId, int quantity) async {
    if (_apiService == null || _processingItems.contains(itemId)) return;
    setState(() => _processingItems.add(itemId));

    try {
      final result = await _apiService!.splitStack(
        characterId: widget.character.id,
        itemId: itemId,
        quantity: quantity,
      );

      final originalStack = result['OriginalStack'] as Map<String, dynamic>?;
      final newStack = result['NewStack'] as Map<String, dynamic>?;

      if (originalStack != null) {
        final remainingQty = JsonParser.getInt(originalStack, 'RemainingQuantity');
        final details = _enrichedInventory[itemId];
        if (details != null) details['Quantity'] = remainingQty;
      }

      if (newStack != null) {
        final newItemId = newStack['ItemID'] as String?;
        if (newItemId != null && widget.onRefresh != null) {
          // Full refresh is the simplest way to surface the new stack and its
          // parent Contents; avoids duplicating the backend's placement logic.
          await widget.onRefresh!();
        }
      }

      if (mounted) {
        setState(() {});
        _showSnackBar('Split $quantity items into new stack');
      }
    } on ApiException catch (err) {
      final errorMessage = err.message.isNotEmpty ? err.message : 'Failed to split stack.';
      _showSnackBar(errorMessage, isError: true);
      if (err.statusCode == 409 && widget.onRefresh != null) await widget.onRefresh!();
    } catch (err) {
      _showSnackBar('Unexpected error: $err', isError: true);
    } finally {
      if (mounted) setState(() => _processingItems.remove(itemId));
    }
  }

  void _showSplitDialog(String itemId, String itemName, int quantity) {
    if (quantity <= 1) {
      _showSnackBar('Cannot split a stack with only 1 item');
      return;
    }

    int splitQuantity = 1;
    final maxSplit = quantity - 1;

    showDialog<int>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Split Stack'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('How many $itemName to split off?'),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: splitQuantity > 1 ? () => setDialogState(() => splitQuantity--) : null,
                    icon: const Icon(Icons.remove),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      border: Border.all(color: Theme.of(context).colorScheme.outline),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text('$splitQuantity', style: Theme.of(context).textTheme.titleLarge),
                  ),
                  IconButton(
                    onPressed: splitQuantity < maxSplit ? () => setDialogState(() => splitQuantity++) : null,
                    icon: const Icon(Icons.add),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text('Original stack will have ${quantity - splitQuantity} items',
                  style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => setDialogState(() => splitQuantity = maxSplit),
                child: const Text('Split Half'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context).pop(null), child: const Text('Cancel')),
            TextButton(
              onPressed: () => Navigator.of(context).pop(splitQuantity),
              child: const Text('Split'),
            ),
          ],
        ),
      ),
    ).then((qty) {
      if (qty != null && qty > 0) _handleSplitStack(itemId, qty);
    });
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
        border: Border(bottom: BorderSide(color: theme.colorScheme.primary, width: 2)),
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
  final String itemId;
  final Map<String, dynamic>? itemDetails;
  final int quantity;
  final bool isEquipped;
  final VoidCallback? onTap;

  const _InventorySlot({
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
    final slotLabel = _wornOnLabel(itemDetails);
    final displayName = (isStackable && quantity > 1) ? '$itemName x$quantity' : itemName;

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
            color: _rarityColor(itemRarity).withValues(alpha: 0.5),
            width: 2,
          ),
        ),
        child: Row(
          children: [
            Icon(RpgIcons.getEquipmentSlotIcon(slotLabel), size: 20, color: colorScheme.onSurfaceVariant),
            const SizedBox(width: 8),
            Text(
              _titleCase(slotLabel),
              style: theme.textTheme.bodySmall?.copyWith(color: colorScheme.onSurfaceVariant),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                displayName,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: _rarityColor(itemRarity),
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

  String _wornOnLabel(Map<String, dynamic>? details) {
    final wornOn = details?['WornOn'];
    if (wornOn is List && wornOn.isNotEmpty) {
      final first = wornOn.first;
      if (first is String && first.isNotEmpty) return first;
    }
    if (wornOn is String && wornOn.isNotEmpty) return wornOn;
    return '';
  }

  String _titleCase(String value) {
    if (value.isEmpty) return '';
    return value
        .replaceAll('_', ' ')
        .split(' ')
        .where((w) => w.isNotEmpty)
        .map((w) => w[0].toUpperCase() + w.substring(1))
        .join(' ');
  }
}

class _InventoryGridItem extends StatelessWidget {
  final String itemId;
  final Map<String, dynamic>? itemDetails;
  final int quantity;
  final VoidCallback? onTap;
  final VoidCallback? onUse;
  final VoidCallback? onDiscard;
  final VoidCallback? onSplit;
  final bool isConsumable;
  final bool isProcessing;
  final bool isStackable;

  const _InventoryGridItem({
    required this.itemId,
    this.itemDetails,
    this.quantity = 1,
    this.onTap,
    this.onUse,
    this.onDiscard,
    this.onSplit,
    this.isConsumable = false,
    this.isProcessing = false,
    this.isStackable = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    final itemRarity = itemDetails?['Rarity'] ?? 'common';
    final effectiveStackable = itemDetails?['Stackable'] == true;
    final itemName = itemDetails?['Name'] as String? ?? itemId;
    final displayName = (effectiveStackable && quantity > 1) ? '$itemName x$quantity' : itemName;

    return Tooltip(
      message: itemName,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: _rarityColor(itemRarity).withValues(alpha: 0.5),
              width: 2,
            ),
          ),
          child: Stack(
            children: [
              Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Icon(
                      RpgIcons.getItemTypeIcon(itemDetails?['Type'] ?? 'item'),
                      size: 28,
                      color: _rarityColor(itemRarity),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      displayName,
                      style: theme.textTheme.bodySmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: _rarityColor(itemRarity),
                      ),
                      maxLines: 2,
                      textAlign: TextAlign.center,
                      overflow: TextOverflow.ellipsis,
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
              if (onSplit != null && isStackable && quantity > 1)
                Positioned(
                  left: 0,
                  bottom: 0,
                  child: IconButton(
                    tooltip: 'Split stack',
                    onPressed: isProcessing ? null : onSplit,
                    style: IconButton.styleFrom(
                      backgroundColor: colorScheme.secondaryContainer,
                      foregroundColor: colorScheme.onSecondaryContainer,
                      padding: const EdgeInsets.all(4),
                      minimumSize: const Size(28, 28),
                    ),
                    icon: const Icon(Icons.call_split, size: 16),
                  ),
                ),
              if (onDiscard != null)
                Positioned(
                  right: 0,
                  bottom: 0,
                  child: IconButton(
                    tooltip: 'Discard $itemName',
                    onPressed: isProcessing ? null : onDiscard,
                    style: IconButton.styleFrom(
                      backgroundColor: colorScheme.errorContainer,
                      foregroundColor: colorScheme.onErrorContainer,
                      padding: const EdgeInsets.all(4),
                      minimumSize: const Size(28, 28),
                    ),
                    icon: const Icon(Icons.delete_outline, size: 16),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

Color _rarityColor(String rarity) {
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
