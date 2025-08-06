import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Widget that handles keyboard shortcuts for the game
class GameKeyboardShortcuts extends StatelessWidget {
  final Widget child;
  final VoidCallback? onRefresh;
  final VoidCallback? onTogglePanel;
  final VoidCallback? onEscape;
  final VoidCallback? onTab;
  final List<VoidCallback?>? numberCallbacks; // For decision choices 1-9

  const GameKeyboardShortcuts({
    super.key,
    required this.child,
    this.onRefresh,
    this.onTogglePanel,
    this.onEscape,
    this.onTab,
    this.numberCallbacks,
  });

  @override
  Widget build(BuildContext context) {
    return Shortcuts(
      shortcuts: <LogicalKeySet, Intent>{
        // Refresh
        LogicalKeySet(LogicalKeyboardKey.f5): const RefreshIntent(),
        LogicalKeySet(LogicalKeyboardKey.keyR, LogicalKeyboardKey.control): 
            const RefreshIntent(),
        
        // Navigation
        LogicalKeySet(LogicalKeyboardKey.escape): const EscapeIntent(),
        LogicalKeySet(LogicalKeyboardKey.tab): const TabIntent(),
        LogicalKeySet(LogicalKeyboardKey.space): const TogglePanelIntent(),
        
        // Decision shortcuts (1-9)
        LogicalKeySet(LogicalKeyboardKey.digit1): const NumberIntent(1),
        LogicalKeySet(LogicalKeyboardKey.digit2): const NumberIntent(2),
        LogicalKeySet(LogicalKeyboardKey.digit3): const NumberIntent(3),
        LogicalKeySet(LogicalKeyboardKey.digit4): const NumberIntent(4),
        LogicalKeySet(LogicalKeyboardKey.digit5): const NumberIntent(5),
        LogicalKeySet(LogicalKeyboardKey.digit6): const NumberIntent(6),
        LogicalKeySet(LogicalKeyboardKey.digit7): const NumberIntent(7),
        LogicalKeySet(LogicalKeyboardKey.digit8): const NumberIntent(8),
        LogicalKeySet(LogicalKeyboardKey.digit9): const NumberIntent(9),
        
        // Arrow keys for panel navigation
        LogicalKeySet(LogicalKeyboardKey.arrowLeft): const NavigateIntent(-1),
        LogicalKeySet(LogicalKeyboardKey.arrowRight): const NavigateIntent(1),
      },
      child: Actions(
        actions: <Type, Action<Intent>>{
          RefreshIntent: CallbackAction<RefreshIntent>(
            onInvoke: (_) => onRefresh?.call(),
          ),
          EscapeIntent: CallbackAction<EscapeIntent>(
            onInvoke: (_) => onEscape?.call(),
          ),
          TabIntent: CallbackAction<TabIntent>(
            onInvoke: (_) => onTab?.call(),
          ),
          TogglePanelIntent: CallbackAction<TogglePanelIntent>(
            onInvoke: (_) => onTogglePanel?.call(),
          ),
          NumberIntent: CallbackAction<NumberIntent>(
            onInvoke: (NumberIntent intent) {
              if (numberCallbacks != null && 
                  intent.number > 0 && 
                  intent.number <= numberCallbacks!.length) {
                numberCallbacks![intent.number - 1]?.call();
              }
              return null;
            },
          ),
          NavigateIntent: CallbackAction<NavigateIntent>(
            onInvoke: (NavigateIntent intent) {
              // Handle arrow key navigation
              return null;
            },
          ),
        },
        child: Focus(
          autofocus: true,
          child: child,
        ),
      ),
    );
  }
}

// Intent classes
class RefreshIntent extends Intent {
  const RefreshIntent();
}

class EscapeIntent extends Intent {
  const EscapeIntent();
}

class TabIntent extends Intent {
  const TabIntent();
}

class TogglePanelIntent extends Intent {
  const TogglePanelIntent();
}

class NumberIntent extends Intent {
  final int number;
  const NumberIntent(this.number);
}

class NavigateIntent extends Intent {
  final int direction;
  const NavigateIntent(this.direction);
}

/// Keyboard shortcut help dialog
class KeyboardShortcutHelp extends StatelessWidget {
  const KeyboardShortcutHelp({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    
    return AlertDialog(
      title: Row(
        children: [
          Icon(
            Icons.keyboard,
            color: theme.colorScheme.primary,
          ),
          const SizedBox(width: 8),
          const Text('Keyboard Shortcuts'),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildShortcutSection(
              'Navigation',
              [
                _ShortcutItem('Tab', 'Switch panels'),
                _ShortcutItem('←/→', 'Navigate panels'),
                _ShortcutItem('Space', 'Toggle side panel'),
                _ShortcutItem('Esc', 'Go back'),
              ],
            ),
            const SizedBox(height: 16),
            _buildShortcutSection(
              'Actions',
              [
                _ShortcutItem('F5 / Ctrl+R', 'Refresh'),
                _ShortcutItem('1-9', 'Select decision choice'),
                _ShortcutItem('Enter', 'Confirm selection'),
                _ShortcutItem('?', 'Show this help'),
              ],
            ),
            const SizedBox(height: 16),
            _buildShortcutSection(
              'Story',
              [
                _ShortcutItem('C', 'Continue story'),
                _ShortcutItem('R', 'Rest (when available)'),
                _ShortcutItem('A', 'Abandon story'),
              ],
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _buildShortcutSection(String title, List<_ShortcutItem> items) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 8),
        ...items.map((item) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.grey.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: Colors.grey.withValues(alpha: 0.4)),
                ),
                child: Text(
                  item.key,
                  style: const TextStyle(
                    fontFamily: 'monospace',
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  item.description,
                  style: const TextStyle(fontSize: 13),
                ),
              ),
            ],
          ),
        )),
      ],
    );
  }

  static void show(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => const KeyboardShortcutHelp(),
    );
  }
}

class _ShortcutItem {
  final String key;
  final String description;

  _ShortcutItem(this.key, this.description);
}