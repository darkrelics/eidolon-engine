import 'package:flutter/material.dart';

void main() {
  runApp(const EidolonIncrementalApp());
}

class EidolonIncrementalApp extends StatelessWidget {
  const EidolonIncrementalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
        title: 'Eidolon Incremental',
        theme: ThemeData(
          brightness: Brightness.dark,
          colorScheme: ColorScheme.fromSeed(
            seedColor: Colors.deepPurple,
            brightness: Brightness.dark,
          ),
          useMaterial3: true,
        ),
        home: const MainGameScreen(),
      );
  }
}

class MainGameScreen extends StatefulWidget {
  const MainGameScreen({super.key});

  @override
  State<MainGameScreen> createState() => _MainGameScreenState();
}

class _MainGameScreenState extends State<MainGameScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.surface,
      body: SafeArea(
        child: Row(
          children: [
            // Character Panel (Left)
            Expanded(
              flex: 2,
              child: Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  border: Border(
                    right: BorderSide(
                      color: Theme.of(context).colorScheme.outline,
                      width: 1,
                    ),
                  ),
                ),
                child: const CharacterPanel(),
              ),
            ),
            
            // Action Panel (Center)
            Expanded(
              flex: 3,
              child: Container(
                color: Theme.of(context).colorScheme.surface,
                child: const ActionPanel(),
              ),
            ),
            
            // Inventory Panel (Right)
            Expanded(
              flex: 2,
              child: Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  border: Border(
                    left: BorderSide(
                      color: Theme.of(context).colorScheme.outline,
                      width: 1,
                    ),
                  ),
                ),
                child: const InventoryPanel(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class CharacterPanel extends StatelessWidget {
  const CharacterPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Character',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 16),
          // Placeholder content
          const Text('Name: Hero'),
          const Text('Class: Warrior'),
          const Text('Level: 1'),
        ],
      ),
    );
  }
}

class ActionPanel extends StatelessWidget {
  const ActionPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            'Current Action',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 32),
          // Placeholder progress bar
          LinearProgressIndicator(
            value: 0.3,
            minHeight: 20,
            backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
          ),
          const SizedBox(height: 16),
          const Text('Fighting: Giant Rat'),
        ],
      ),
    );
  }
}

class InventoryPanel extends StatelessWidget {
  const InventoryPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Inventory',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 16),
          // Placeholder content
          const Text('Gold: 0'),
          const Text('Items: None'),
        ],
      ),
    );
  }
}