import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

/// Display modes for decision widget
enum DecisionDisplayMode {
  panel, // Card-based panel display
  inline, // Inline within other content
  dialog, // Modal dialog display
}

/// Unified decision widget that can display in different modes
class DecisionWidget extends StatefulWidget {
  final Map<String, dynamic> choices;
  final Function(String) onDecisionSelected;
  final bool isLoading;
  final String? selectedChoice;
  final String? error;
  final DecisionDisplayMode displayMode;
  final String? title;
  final String? description;
  final VoidCallback? onCancel;

  const DecisionWidget({
    super.key,
    required this.choices,
    required this.onDecisionSelected,
    this.isLoading = false,
    this.selectedChoice,
    this.error,
    this.displayMode = DecisionDisplayMode.panel,
    this.title,
    this.description,
    this.onCancel,
  });

  @override
  State<DecisionWidget> createState() => _DecisionWidgetState();

  /// Show as dialog
  static Future<String?> showDialog({
    required BuildContext context,
    required Map<String, dynamic> choices,
    String? title,
    String? description,
  }) async {
    return await showGeneralDialog<String>(
      context: context,
      barrierDismissible: false,
      barrierLabel: 'Decision',
      transitionDuration: const Duration(milliseconds: 300),
      pageBuilder: (context, animation, secondaryAnimation) {
        return Center(
          child: Material(
            color: Colors.transparent,
            child: DecisionWidget(
              choices: choices,
              displayMode: DecisionDisplayMode.dialog,
              title: title,
              description: description,
              onDecisionSelected: (choice) {
                Navigator.of(context).pop(choice);
              },
              onCancel: () {
                Navigator.of(context).pop();
              },
            ),
          ),
        );
      },
      transitionBuilder: (context, animation, secondaryAnimation, child) {
        return FadeTransition(
          opacity: animation,
          child: ScaleTransition(
            scale: Tween<double>(begin: 0.9, end: 1.0).animate(
              CurvedAnimation(parent: animation, curve: Curves.easeOutCubic),
            ),
            child: child,
          ),
        );
      },
    );
  }
}

class _DecisionWidgetState extends State<DecisionWidget>
    with SingleTickerProviderStateMixin {
  String? _hoveredChoice;
  late AnimationController _animationController;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return switch (widget.displayMode) {
      DecisionDisplayMode.panel => _buildPanel(context),
      DecisionDisplayMode.inline => _buildInline(context),
      DecisionDisplayMode.dialog => _buildDialog(context),
    };
  }

  Widget _buildPanel(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
          elevation: 4,
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (widget.title != null) ...[
                  Text(
                    widget.title!,
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                ],
                if (widget.description != null) ...[
                  Text(
                    widget.description!,
                    style: theme.textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                ],
                if (widget.error != null) ...[
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.errorContainer,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      widget.error!,
                      style: TextStyle(
                        color: theme.colorScheme.onErrorContainer,
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                if (widget.isLoading)
                  const Center(child: CircularProgressIndicator())
                else
                  _buildChoicesList(context),
              ],
            ),
          ),
        )
        .animate(controller: _animationController)
        .fadeIn()
        .slideY(begin: 0.1, end: 0);
  }

  Widget _buildInline(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (widget.error != null) _buildError(context),
        if (widget.isLoading)
          const Center(child: CircularProgressIndicator())
        else
          _buildChoicesList(context),
      ],
    );
  }

  Widget _buildDialog(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
          constraints: const BoxConstraints(maxWidth: 400),
          margin: const EdgeInsets.all(24),
          child: Card(
            elevation: 8,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Header
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.1),
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(12),
                    ),
                  ),
                  child: Column(
                    children: [
                      Icon(
                        Icons.psychology,
                        size: 32,
                        color: theme.colorScheme.primary,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        widget.title ?? 'Make Your Choice',
                        style: theme.textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      if (widget.description != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          widget.description!,
                          style: theme.textTheme.bodyMedium,
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ],
                  ),
                ),
                // Content
                Flexible(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: [
                        if (widget.error != null) ...[
                          _buildError(context),
                          const SizedBox(height: 16),
                        ],
                        if (widget.isLoading)
                          const Center(child: CircularProgressIndicator())
                        else
                          _buildChoicesList(context),
                      ],
                    ),
                  ),
                ),
                // Actions
                if (widget.onCancel != null && !widget.isLoading)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: TextButton(
                      onPressed: widget.onCancel,
                      child: const Text('Cancel'),
                    ),
                  ),
              ],
            ),
          ),
        )
        .animate(controller: _animationController)
        .fadeIn()
        .scale(begin: const Offset(0.9, 0.9), end: const Offset(1, 1));
  }

  Widget _buildChoicesList(BuildContext context) {
    final theme = Theme.of(context);
    final choiceEntries = widget.choices.entries.toList();

    return Column(
      children: choiceEntries.map((entry) {
        final choiceId = entry.key;
        final choiceData = entry.value as Map<String, dynamic>?;
        final choiceText =
            choiceData?['Text'] ?? choiceData?['text'] ?? choiceId;
        final description =
            choiceData?['Description'] ?? choiceData?['description'];
        final isSelected = widget.selectedChoice == choiceId;
        final isHovered = _hoveredChoice == choiceId;

        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: MouseRegion(
            onEnter: (_) => setState(() => _hoveredChoice = choiceId),
            onExit: (_) => setState(() => _hoveredChoice = null),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: isSelected
                      ? theme.colorScheme.primary
                      : isHovered
                      ? theme.colorScheme.primary.withValues(alpha: 0.5)
                      : Colors.transparent,
                  width: isSelected ? 2 : 1,
                ),
                color: isSelected
                    ? theme.colorScheme.primary.withValues(alpha: 0.1)
                    : isHovered
                    ? theme.colorScheme.surfaceContainerHighest
                    : null,
              ),
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  borderRadius: BorderRadius.circular(8),
                  onTap: widget.isLoading
                      ? null
                      : () => widget.onDecisionSelected(choiceId),
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        if (isSelected)
                          Icon(
                            Icons.check_circle,
                            color: theme.colorScheme.primary,
                            size: 20,
                          )
                        else
                          Icon(
                            Icons.radio_button_unchecked,
                            color: theme.colorScheme.onSurfaceVariant,
                            size: 20,
                          ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                choiceText,
                                style: theme.textTheme.bodyLarge?.copyWith(
                                  fontWeight: isSelected
                                      ? FontWeight.bold
                                      : null,
                                ),
                              ),
                              if (description != null) ...[
                                const SizedBox(height: 4),
                                Text(
                                  description,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildError(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        children: [
          Icon(
            Icons.error_outline,
            color: theme.colorScheme.onErrorContainer,
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              widget.error!,
              style: TextStyle(color: theme.colorScheme.onErrorContainer),
            ),
          ),
        ],
      ),
    );
  }
}
