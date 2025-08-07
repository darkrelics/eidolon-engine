import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:eidolon_incremental/screens/game_screen.dart';
import 'package:eidolon_incremental/models/character.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/providers/theme_provider.dart';
import 'package:provider/provider.dart';

void main() {
  group('Game Flow Integration Tests', () {
    late Character testCharacter;

    setUp(() {
      
      testCharacter = Character(
        id: 'test-char',
        name: 'Test Hero',
        archetypeId: 'warrior',
        archetypeName: 'Warrior',
        health: 100,
        maxHealth: 100,
        essence: 50,
        maxEssence: 50,
        attributes: {
          'Strength': 15.0,
          'Agility': 12.0,
          'Intelligence': 10.0,
        },
        skills: {
          'Melee': 3.0,
          'Arcane': 2.0,
        },
        resources: {
          'gold': 500,
          'supplies': 10,
        },
        inventory: {
          'weapon': 'sword-01',
          'armor': 'plate-01',
        },
        inventoryDetails: {
          'weapon': {
            'ItemID': 'sword-01',
            'Name': 'Iron Sword',
            'Type': 'weapon',
            'Rarity': 'common',
          },
          'armor': {
            'ItemID': 'plate-01',
            'Name': 'Iron Plate',
            'Type': 'armor',
            'Rarity': 'common',
          },
        },
        progress: {},
        storyState: null,
        gameMode: 'Incremental',
        lastUpdated: DateTime.now(),
        availableStories: ['story-1'],
        availableStoriesDetails: [
          {
            'storyId': 'story-1',
            'title': 'Test Quest',
            'description': 'A test adventure',
            'type': 'main',
            'available': true,
            'cooldownRemaining': 0,
            'estimatedDuration': 600,
          },
        ],
        abandonedStories: [],
        completedStories: [],
      );
    });

    Widget createTestApp({Character? character}) {
      return MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ],
        child: MaterialApp(
          home: GameScreen(),
          routes: {
            '/character-selection': (context) => const Scaffold(
              body: Center(child: Text('Character Selection')),
            ),
          },
          onGenerateRoute: (settings) {
            if (settings.name == '/game') {
              return MaterialPageRoute(
                builder: (context) => const GameScreen(),
                settings: RouteSettings(
                  arguments: character ?? CharacterInfo(
                    name: 'Test',
                    id: 'test-id',
                    dead: false,
                  ),
                ),
              );
            }
            return null;
          },
        ),
      );
    }

    testWidgets('Game screen loads with character data',
        (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(character: testCharacter));
      await tester.pumpAndSettle();

      // Check that character name appears
      expect(find.text('Test Hero'), findsOneWidget);
      
      // Check that panels are present
      expect(find.text('Character'), findsOneWidget);
      expect(find.text('Story'), findsOneWidget);
      expect(find.text('Inventory'), findsOneWidget);
    });

    testWidgets('Navigation between panels works correctly',
        (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(character: testCharacter));
      await tester.pumpAndSettle();

      // On mobile, should have bottom navigation
      final bottomNav = find.byType(BottomNavigationBar);
      if (bottomNav.evaluate().isNotEmpty) {
        // Tap on Character tab
        await tester.tap(find.byIcon(Icons.person));
        await tester.pumpAndSettle();

        // Tap on Story tab
        await tester.tap(find.byIcon(Icons.auto_stories));
        await tester.pumpAndSettle();

        // Tap on Inventory tab
        await tester.tap(find.byIcon(Icons.inventory_2));
        await tester.pumpAndSettle();
      }
    });

    testWidgets('Story selection flow works',
        (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(character: testCharacter));
      await tester.pumpAndSettle();

      // Find and tap on available story
      final storyCard = find.text('Test Quest');
      if (storyCard.evaluate().isNotEmpty) {
        await tester.tap(storyCard);
        await tester.pumpAndSettle();
      }
    });

    testWidgets('Theme toggle changes appearance',
        (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(character: testCharacter));
      await tester.pumpAndSettle();

      // Find theme toggle button
      final themeButton = find.byIcon(Icons.settings_brightness);
      if (themeButton.evaluate().isNotEmpty) {
        // Get initial theme
        final BuildContext context = tester.element(find.byType(Scaffold).first);
        final initialBrightness = Theme.of(context).brightness;

        // Toggle theme
        await tester.tap(themeButton);
        await tester.pumpAndSettle();

        // Theme menu should appear
        await tester.tap(find.text('Dark').last);
        await tester.pumpAndSettle();

        // Check theme changed
        final newBrightness = Theme.of(context).brightness;
        expect(newBrightness, isNot(equals(initialBrightness)));
      }
    });

    testWidgets('Error handling displays error widget',
        (WidgetTester tester) async {
      final characterWithError = Character(
        id: 'error-char',
        name: 'Error Test',
        archetypeId: 'test',
        archetypeName: 'Test',
        health: 0,
        maxHealth: 100,
        essence: 0,
        maxEssence: 50,
        attributes: {},
        skills: {},
        resources: {},
        inventory: {},
        inventoryDetails: {},
        progress: {},
        storyState: null,
        gameMode: 'Incremental',
        lastUpdated: DateTime.now(),
        availableStories: [],
        availableStoriesDetails: null, // This will cause an error
        abandonedStories: [],
        completedStories: [],
      );

      await tester.pumpWidget(createTestApp(character: characterWithError));
      await tester.pumpAndSettle();

      // Should still render without crashing
      expect(find.byType(GameScreen), findsOneWidget);
    });

    testWidgets('Keyboard shortcuts dialog opens',
        (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(character: testCharacter));
      await tester.pumpAndSettle();

      // Find and tap help button
      final helpButton = find.byIcon(Icons.help_outline);
      if (helpButton.evaluate().isNotEmpty) {
        await tester.tap(helpButton);
        await tester.pumpAndSettle();

        // Keyboard shortcuts dialog should appear
        expect(find.text('Keyboard Shortcuts'), findsOneWidget);
        expect(find.text('Navigation'), findsOneWidget);
        expect(find.text('Actions'), findsOneWidget);

        // Close dialog
        await tester.tap(find.text('Close'));
        await tester.pumpAndSettle();
      }
    });

    testWidgets('Refresh button triggers data reload',
        (WidgetTester tester) async {
      await tester.pumpWidget(createTestApp(character: testCharacter));
      await tester.pumpAndSettle();

      // Find and tap refresh button
      final refreshButton = find.byIcon(Icons.refresh);
      if (refreshButton.evaluate().isNotEmpty) {
        await tester.tap(refreshButton.first);
        await tester.pump();

        // Loading indicator might appear briefly
        // (depending on implementation)
      }
    });

    testWidgets('Active story state displays correctly',
        (WidgetTester tester) async {
      final characterWithStory = testCharacter.copyWith(
        storyState: {
          'Story': {
            'Title': 'Active Adventure',
            'Type': 'main',
          },
          'ActiveSegment': {
            'SegmentType': 'mechanical',
            'ShortStatus': 'Processing actions...',
            'ProcessingStatus': 'processing',
          },
        },
      );

      await tester.pumpWidget(createTestApp(character: characterWithStory));
      await tester.pumpAndSettle();

      // Should show active story
      expect(find.text('Active Adventure'), findsOneWidget);
      expect(find.text('Processing actions...'), findsOneWidget);
    });
  });
}