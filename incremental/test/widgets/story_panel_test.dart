import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/widgets/game/story_panel.dart';

void main() {
  group('StoryPanel Widget Tests', () {
    late Character mockCharacter;

    setUp(() {
      mockCharacter = Character(
        id: 'test-char-1',
        name: 'Test Hero',
        archetypeId: 'warrior',
        archetypeName: 'Warrior',
        health: 100,
        maxHealth: 100,
        essence: 50,
        maxEssence: 50,
        attributes: {'Strength': 10.0, 'Agility': 8.0, 'Intelligence': 12.0},
        skills: {},
        resources: {'gold': 100},
        inventory: {},
        inventoryDetails: {},
        progress: {},
        gameMode: 'Incremental',
        lastUpdated: DateTime.now(),
        availableStories: ['story-1', 'story-2'],
        availableStoriesDetails: [
          {
            'StoryID': 'story-1',
            'Title': 'The Beginning',
            'Description': 'Start your adventure',
            'Type': 'main',
            'Available': true,
            'CooldownRemaining': 0,
            'EstimatedDuration': 600,
          },
          {
            'StoryID': 'story-2',
            'Title': 'Daily Quest',
            'Description': 'A daily challenge',
            'Type': 'daily',
            'Available': false,
            'CooldownRemaining': 3600,
            'EstimatedDuration': 300,
          },
        ],
        completedStories: [],
        storyState: null,
      );
    });

    testWidgets('displays available stories when no active story', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: StoryPanel(character: mockCharacter)),
        ),
      );

      expect(find.text('Available Stories'), findsOneWidget);
      expect(find.text('The Beginning'), findsOneWidget);
      expect(find.text('Daily Quest'), findsOneWidget);
    });

    testWidgets('displays active story when story state exists', (
      WidgetTester tester,
    ) async {
      final characterWithStory = mockCharacter.copyWith(
        activeStoryId: 'story-1',
        storyState: {
          'Story': {
            'Title': 'Active Quest',
            'Description': 'An ongoing adventure',
            'Type': 'main',
          },
          'ActiveSegment': {
            'SegmentType': 'decision',
            'SegmentTitle': 'Choose your path',
            'SegmentActivity': 'Awaiting your decision',
            'Choices': [
              {
                'ChoiceID': 'choice-1',
                'Text': 'Go left',
                'Description': 'Take the left path',
              },
              {
                'ChoiceID': 'choice-2',
                'Text': 'Go right',
                'Description': 'Take the right path',
              },
            ],
          },
        },
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: StoryPanel(character: characterWithStory)),
        ),
      );

      await tester.pump();

      expect(find.text('Active Quest'), findsOneWidget);
      expect(find.text('Choose your path'), findsOneWidget);
    });

    testWidgets('shows loading indicator when isLoading is true', (
      WidgetTester tester,
    ) async {
      final loadingCharacter = mockCharacter.copyWith(
        availableStories: [],
        availableStoriesDetails: null,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StoryPanel(character: loadingCharacter, isLoading: true),
          ),
        ),
      );

      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('displays error message when error is provided', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StoryPanel(
              character: mockCharacter,
              error: 'Failed to load stories',
            ),
          ),
        ),
      );

      expect(find.text('Error Loading Stories'), findsOneWidget);
      expect(find.text('Failed to load stories'), findsOneWidget);
      expect(find.byIcon(Icons.error_outline), findsOneWidget);
    });

    testWidgets('calls onRefresh when refresh button is pressed', (
      WidgetTester tester,
    ) async {
      bool refreshCalled = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StoryPanel(
              character: mockCharacter,
              onRefresh: () {
                refreshCalled = true;
              },
            ),
          ),
        ),
      );

      await tester.tap(find.byIcon(Icons.refresh));
      await tester.pump();

      expect(refreshCalled, isTrue);
    });

    testWidgets('toggles between available stories and history', (
      WidgetTester tester,
    ) async {
      final characterWithHistory = mockCharacter.copyWith(
        completedStories: ['completed-story-1', 'completed-story-2'],
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: StoryPanel(character: characterWithHistory)),
        ),
      );

      // Initially shows available stories
      expect(find.text('Available Stories'), findsOneWidget);

      // Find and tap the history toggle button
      await tester.tap(find.byIcon(Icons.history));
      await tester.pumpAndSettle();

      // Should now show story history
      expect(find.text('Story History'), findsOneWidget);
    });
  });
}
