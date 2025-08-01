import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/active_segment.dart';
import '../providers/segment_provider.dart';
import '../services/api_service.dart';

class DecisionSegmentDisplay extends StatefulWidget {
  final ActiveSegment activeSegment;
  final String characterId;

  const DecisionSegmentDisplay({
    super.key,
    required this.activeSegment,
    required this.characterId,
  });

  @override
  State<DecisionSegmentDisplay> createState() => _DecisionSegmentDisplayState();
}

class _DecisionSegmentDisplayState extends State<DecisionSegmentDisplay> {
  String? _selectedDecision;
  bool _isSubmitting = false;
  String? _errorMessage;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final decisionOptions = widget.activeSegment.decisionOptions ?? {};
    final hasDecided = widget.activeSegment.decision != null;

    return Card(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Title
            Text(
              'Decision Required',
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            
            // Description/Status
            if (widget.activeSegment.storyTitle.isNotEmpty)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  'Story: ${widget.activeSegment.storyTitle}',
                  style: theme.textTheme.bodyLarge,
                ),
              ),
            const SizedBox(height: 16),
            
            // Decision status
            if (hasDecided) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.check_circle,
                      color: theme.colorScheme.primary,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Decision made: ${widget.activeSegment.decision}',
                      style: theme.textTheme.bodyLarge?.copyWith(
                        color: theme.colorScheme.onPrimaryContainer,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ] else ...[
              // Decision options
              Text(
                'Choose your action:',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              
              ...decisionOptions.entries.map((entry) {
                final decisionId = entry.key;
                // The value is the next segment ID, but we display the decision ID as the option
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: RadioListTile<String>(
                    title: Text(_formatDecisionText(decisionId)),
                    value: decisionId,
                    groupValue: _selectedDecision,
                    onChanged: _isSubmitting ? null : (value) {
                      setState(() {
                        _selectedDecision = value;
                        _errorMessage = null;
                      });
                    },
                    contentPadding: EdgeInsets.zero,
                  ),
                );
              }),
              
              const SizedBox(height: 16),
              
              // Error message
              if (_errorMessage != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.errorContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.error_outline,
                        color: theme.colorScheme.onErrorContainer,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _errorMessage!,
                          style: TextStyle(
                            color: theme.colorScheme.onErrorContainer,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              
              const SizedBox(height: 16),
              
              // Submit button
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _selectedDecision == null || _isSubmitting
                      ? null
                      : _submitDecision,
                  child: _isSubmitting
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Submit Decision'),
                ),
              ),
            ],
            
            // Time remaining indicator
            if (!hasDecided)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Row(
                  children: [
                    Icon(
                      Icons.timer,
                      size: 16,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      'Time remaining: ${_formatTimeRemaining()}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _formatDecisionText(String decisionId) {
    // Convert decision IDs to readable text
    // e.g., "fight_goblin" -> "Fight the goblin"
    return decisionId
        .split('_')
        .map((word) => word[0].toUpperCase() + word.substring(1))
        .join(' ');
  }

  String _formatTimeRemaining() {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final remaining = widget.activeSegment.endTime - now;
    
    if (remaining <= 0) return 'Expired';
    
    final minutes = remaining ~/ 60;
    final seconds = remaining % 60;
    
    if (minutes > 0) {
      return '$minutes:${seconds.toString().padLeft(2, '0')}';
    }
    return '${seconds}s';
  }

  Future<void> _submitDecision() async {
    if (_selectedDecision == null) return;
    
    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });
    
    try {
      final apiService = context.read<ApiService>();
      final segmentProvider = context.read<SegmentProvider>();
      
      await apiService.submitDecision(
        characterId: widget.characterId,
        decision: _selectedDecision!,
      );
      
      // Refresh segment status
      await segmentProvider.loadCurrentStory(widget.characterId);
      
    } catch (e) {
      setState(() {
        _errorMessage = 'Failed to submit decision: ${e.toString()}';
      });
    } finally {
      setState(() {
        _isSubmitting = false;
      });
    }
  }
}