# Flutter Style Guide - Eidolon Engine

This document defines the Flutter/Dart coding standards and best practices for the Eidolon Engine incremental and portal applications.

## General Guidelines

- Follow the official [Dart Style Guide](https://dart.dev/guides/language/effective-dart/style)
- Use `dart analyze` to check for issues before committing
- Maintain consistency with existing code patterns
- Prioritize readability and maintainability

## Code Organization

### File Structure

```
lib/
├── config/           # Application configuration
├── constants/        # App-wide constants
├── main.dart        # Application entry point
├── models/          # Data models
├── providers/       # State management providers
├── screens/         # Full page widgets
├── services/        # API and business logic
├── utils/           # Utility functions
└── widgets/         # Reusable UI components
```

### File Naming

- Use lowercase with underscores: `game_screen.dart`
- Match file names to class names: `GameScreen` → `game_screen.dart`
- Group related files in directories

## Dart Code Style

### Imports

```dart
// 1. Dart imports
import 'dart:async';
import 'dart:convert';

// 2. Package imports (alphabetical)
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

// 3. Project imports (alphabetical)
import '../models/character.dart';
import '../services/api_service.dart';
import '../utils/json_utils.dart';
```

### Classes and Functions

```dart
/// Service for managing character data.
/// 
/// Handles API communication and local caching.
class CharacterService {
  final ApiService _apiService;
  final _characterCache = <String, Character>{};

  CharacterService({required ApiService apiService}) 
    : _apiService = apiService;

  /// Fetches character by ID from API or cache.
  Future<Character?> getCharacter(String characterId) async {
    // Check cache first
    if (_characterCache.containsKey(characterId)) {
      return _characterCache[characterId];
    }

    // Fetch from API
    final character = await _apiService.getCharacterById(characterId);
    if (character != null) {
      _characterCache[characterId] = character;
    }
    
    return character;
  }
}
```

### Naming Conventions

- Classes: `PascalCase` (e.g., `CharacterInfo`)
- Functions/methods: `camelCase` (e.g., `getCharacter`)
- Constants: `lowerCamelCase` or `SCREAMING_CAPS` for primitive values
- Private members: prefix with underscore (e.g., `_apiService`)

### Widget Guidelines

#### Stateless Widgets

```dart
class CharacterCard extends StatelessWidget {
  final Character character;
  final VoidCallback? onTap;

  const CharacterCard({
    super.key,
    required this.character,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Text(character.name),
        ),
      ),
    );
  }
}
```

#### Stateful Widgets

```dart
class GameScreen extends StatefulWidget {
  const GameScreen({super.key});

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> {
  late final ApiService _apiService;
  Character? _character;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _apiService = ApiService(authService: AuthService.instance);
    _loadCharacter();
  }

  @override
  void dispose() {
    // Clean up resources
    super.dispose();
  }

  Future<void> _loadCharacter() async {
    // Implementation
  }

  @override
  Widget build(BuildContext context) {
    // Implementation
  }
}
```

## API Integration

### Service Layer

```dart
class ApiService {
  final AuthService _authService;
  final http.Client _httpClient;
  final String baseUrl;

  ApiService({
    required AuthService authService,
    String? baseUrl,
    http.Client? httpClient,
  }) : _authService = authService,
       _httpClient = httpClient ?? http.Client(),
       baseUrl = baseUrl ?? _defaultBaseUrl;

  Future<Map<String, String>> _getHeaders() async {
    final token = await _authService.getIdToken();
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  Future<Character?> getCharacterById(String characterId) async {
    final headers = await _getHeaders();
    final response = await _httpClient.get(
      Uri.parse('$baseUrl/character?CharacterID=$characterId'),
      headers: headers,
    );

    if (response.statusCode == 404) {
      return null;
    }

    if (response.statusCode != 200) {
      throw ApiException('Failed to get character: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return Character.fromJson(json);
  }
}
```

### Error Handling

```dart
try {
  final character = await _apiService.getCharacterById(characterId);
  setState(() {
    _character = character;
  });
} catch (e) {
  if (mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(ErrorHandler.getUserFriendlyMessage(e)),
        backgroundColor: Colors.red,
      ),
    );
  }
}
```

## JSON Handling

### Flexible Field Access

Use the `JsonUtils` utility for robust JSON parsing:

```dart
// Handle both PascalCase and camelCase field names
final characterId = JsonUtils.getFlexibleRequired<String>(
  json,
  'CharacterID',
  'characterId',
);

// Optional fields with defaults
final health = JsonUtils.getFlexible<int>(
  json,
  'Health',
  'health',
) ?? 10;
```

### Model Classes

```dart
class Character {
  final String id;
  final String name;
  final String archetypeName;
  final int health;
  final int maxHealth;

  Character({
    required this.id,
    required this.name,
    required this.archetypeName,
    required this.health,
    required this.maxHealth,
  });

  factory Character.fromJson(Map<String, dynamic> json) {
    return Character(
      id: JsonUtils.getFlexibleRequired<String>(json, 'CharacterID', 'characterId'),
      name: JsonUtils.getFlexibleRequired<String>(json, 'CharacterName', 'characterName'),
      archetypeName: JsonUtils.getFlexible<String>(json, 'ArchetypeName', 'archetypeName') ?? 'Unknown',
      health: JsonUtils.getFlexible<int>(json, 'Health', 'health') ?? 0,
      maxHealth: JsonUtils.getFlexible<int>(json, 'MaxHealth', 'maxHealth') ?? 10,
    );
  }
}
```

## State Management

### Local State

For simple component state, use `setState`:

```dart
class _MyWidgetState extends State<MyWidget> {
  bool _isLoading = false;

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
    });

    try {
      // Load data
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }
}
```

### Provider Pattern

For shared state, use Provider or similar state management:

```dart
class CharacterProvider extends ChangeNotifier {
  Character? _currentCharacter;
  
  Character? get currentCharacter => _currentCharacter;

  void setCharacter(Character character) {
    _currentCharacter = character;
    notifyListeners();
  }
}
```

## UI/UX Guidelines

### Theme Usage

Always use theme colors and text styles:

```dart
Widget build(BuildContext context) {
  final theme = Theme.of(context);
  
  return Container(
    color: theme.colorScheme.surface,
    child: Text(
      'Hello',
      style: theme.textTheme.headlineSmall,
    ),
  );
}
```

### Responsive Design

```dart
Widget build(BuildContext context) {
  return LayoutBuilder(
    builder: (context, constraints) {
      if (constraints.maxWidth > 600) {
        return _buildWideLayout();
      } else {
        return _buildNarrowLayout();
      }
    },
  );
}
```

### Loading States

```dart
if (_isLoading) {
  return const Center(
    child: CircularProgressIndicator(),
  );
}

if (_error != null) {
  return ErrorWidget(
    message: _error!,
    onRetry: _loadData,
  );
}

return _buildContent();
```

## Testing

### Widget Tests

```dart
testWidgets('CharacterCard displays character name', (tester) async {
  final character = Character(
    id: 'test-123',
    name: 'Test Character',
    // ... other required fields
  );

  await tester.pumpWidget(
    MaterialApp(
      home: CharacterCard(character: character),
    ),
  );

  expect(find.text('Test Character'), findsOneWidget);
});
```

### Unit Tests

```dart
test('Character.fromJson parses JSON correctly', () {
  final json = {
    'CharacterID': 'test-123',
    'CharacterName': 'Test Character',
    'Health': 8,
    'MaxHealth': 10,
  };

  final character = Character.fromJson(json);

  expect(character.id, 'test-123');
  expect(character.name, 'Test Character');
  expect(character.health, 8);
  expect(character.maxHealth, 10);
});
```

## Performance Best Practices

### Const Constructors

Use `const` constructors where possible:

```dart
// Good
const SizedBox(height: 16);
const EdgeInsets.all(8.0);

// Avoid
SizedBox(height: 16);
EdgeInsets.all(8.0);
```

### Keys for Lists

```dart
ListView.builder(
  itemCount: items.length,
  itemBuilder: (context, index) {
    return CharacterCard(
      key: ValueKey(items[index].id),
      character: items[index],
    );
  },
);
```

### Avoid Rebuilds

```dart
// Cache expensive computations
final _expensiveValue = useMemoized(() => computeExpensiveValue());

// Use const widgets
const _staticWidget = Text('This never changes');
```

## Security Considerations

- Never log sensitive information (tokens, passwords)
- Validate all user input
- Use HTTPS for all API calls
- Store sensitive data securely (use flutter_secure_storage)
- Clear sensitive data when logging out

## Debugging

### Debug Prints

```dart
// Use debugPrint for development
debugPrint('GameScreen: Loading character ${characterId}');

// Remove or guard production logs
if (kDebugMode) {
  print('Debug info: $data');
}
```

### Error Messages

Provide meaningful error messages:

```dart
if (response.statusCode == 403) {
  throw Exception('You do not have permission to view this character');
} else if (response.statusCode == 404) {
  throw Exception('Character not found');
} else {
  throw Exception('Failed to load character (${response.statusCode})');
}
```

## Code Review Checklist

- [ ] Code follows Dart style guide
- [ ] No analyzer warnings or errors
- [ ] Proper error handling with user-friendly messages
- [ ] Responsive design considered
- [ ] Theme colors/styles used consistently
- [ ] Loading and error states handled
- [ ] Memory leaks prevented (dispose controllers, close streams)
- [ ] Sensitive data handled securely
- [ ] Code is testable and tested
- [ ] Documentation added for complex logic