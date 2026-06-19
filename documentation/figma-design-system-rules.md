# Figma Design System Rules - Eidolon Engine

This document provides comprehensive rules for integrating Figma designs into the Eidolon Engine project using the Model Context Protocol (MCP). These rules help maintain consistency when translating Figma designs to code.

## Project Overview

**Project Type**: Multi-mode game engine with Flutter web frontends
**Primary Applications**:

- Incremental RPG (story-driven gameplay)
- MUD Portal (traditional multi-user dungeon interface)

**Technology Stack**:

- Frontend: Flutter 3.32+ (Web)
- Language: Dart 3.9+
- State Management: Provider pattern
- Backend: AWS Lambda (Python 3.12)

## 1. Design Token Definitions

### Color System

Design tokens are defined programmatically in Flutter ThemeData. Color values are hardcoded constants within theme provider classes.

**Location**: `incremental/lib/providers/theme_provider.dart`, `portal/lib/providers/theme_provider.dart`

#### Dark Theme Colors (Default)

```dart
// Primary Colors
const Color darkBackground = Color(0xFF1F2224);
const Color darkSurface = Color(0xFF2A2D31);
const Color accentPurple = Color(0xFF818CF8);

// Text Colors
const Color darkTextPrimary = Color(0xFFE6E6E6);
const Color darkTextSecondary = Color(0xFFAEAEB2);

// UI Elements
const Color darkDivider = Color(0xFF505050);
const Color errorColor = Color(0xFFD32F2F);
```

#### Light Theme Colors

```dart
// Primary Colors
const Color primaryBlue = Color(0xFF2196F3);
const Color lightBackground = Colors.white;
const Color lightSurface = Colors.white;

// Text Colors
const Color lightTextPrimary = Color(0xDE000000); // Black 87%
const Color lightTextSecondary = Color(0x8A000000); // Black 54%

// UI Elements
const Color lightDivider = Color(0xFFE0E0E0);
```

#### Semantic Colors

Semantic colors for game mechanics are defined in utility files:

**Location**: `incremental/lib/utils/outcome_colors.dart`

```dart
// Outcome-based colors (game mechanics)
Death: Colors.black
Failure: theme.colorScheme.error
Minimal: Colors.amber.shade600
Normal: Colors.green.shade600
Exceptional: Colors.blue.shade500

// Resource bar colors (hardcoded)
Health: Colors.red
Essence: Colors.blue
Wounds: Colors.orange
```

### Typography

Typography uses Material Design 2021 baseline with theme-specific color overrides.

```dart
textTheme: Typography.material2021().white.copyWith(
  bodyLarge: const TextStyle(color: darkTextPrimary),
  bodyMedium: const TextStyle(color: darkTextPrimary),
  titleLarge: const TextStyle(color: darkTextPrimary),
  titleMedium: const TextStyle(color: darkTextPrimary),
  titleSmall: const TextStyle(color: darkTextPrimary),
  labelLarge: const TextStyle(color: darkTextPrimary),
)
```

**Font Family**: System default (no custom fonts)
**Line Length**: Maximum 132 characters (project standard)

### Spacing System

Spacing values are hardcoded using Flutter's EdgeInsets. Common values:

```dart
// Standard spacing increments (multiples of 4)
4.0, 8.0, 12.0, 16.0, 20.0, 24.0

// Responsive padding (defined in ResponsivePadding widget)
Mobile: EdgeInsets.all(8.0)
Tablet: EdgeInsets.all(16.0)
Desktop: EdgeInsets.all(24.0)
```

### Border Radius

Consistent border radius values:

```dart
// Standard radius
BorderRadius.circular(8)  // Cards, buttons, inputs

// Badges and small elements
BorderRadius.circular(12)

// Conditional (partial radius for headers)
BorderRadius.only(
  topLeft: Radius.circular(12),
  topRight: Radius.circular(12),
)
```

### Elevation

Material Design elevation values:

```dart
CardTheme: elevation: 2
AppBarTheme: elevation: 0
```

## 2. Component Library

### Component Organization

Components are organized by function and scope:

```
lib/
├── screens/          # Full-page views (routes)
├── widgets/
│   ├── game/        # Game-specific panels (character, story, inventory)
│   ├── shared/      # Reusable UI components
│   ├── story/       # Story-specific widgets
│   └── unified/     # Cross-feature components
└── providers/       # State management (ChangeNotifier pattern)
```

### Component Architecture

**Pattern**: Stateless widgets for presentation, Stateful for data/interaction
**State Management**: Provider pattern with ChangeNotifier
**Composition**: Favor composition over inheritance

#### Component Types

1. **Screen Components** (`screens/`)
   - Full-page routes
   - Scaffold-based layouts
   - Consume providers for state
   - Example: `GameScreen`, `LoginScreen`

2. **Panel Components** (`widgets/game/`)
   - Major UI sections (left/center/right panels)
   - Composite widgets
   - Example: `CharacterPanel`, `StoryPanel`, `InventoryPanel`

3. **Shared Components** (`widgets/shared/`)
   - Reusable across screens
   - Generic functionality
   - Example: `ResponsiveLayout`, `LoadingOverlay`, `ErrorBoundary`

### Key Component Patterns

#### Panel Structure (3-column layout)

```dart
// Desktop: 3 panels side-by-side
Row(
  children: [
    Expanded(flex: 2, child: CharacterPanel()),  // Left
    Expanded(flex: 3, child: StoryPanel()),      // Center
    Expanded(flex: 2, child: InventoryPanel()),  // Right
  ],
)

// Mobile: Bottom navigation between panels
BottomNavigationBar(
  currentIndex: _selectedPanelIndex,
  items: [Character, Story, Inventory],
)
```

#### Card-based Information Display

```dart
Card(
  margin: const EdgeInsets.all(8),
  child: Column(
    children: [
      // Header with colored background
      Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: colorScheme.primaryContainer,
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(12),
            topRight: Radius.circular(12),
          ),
        ),
        child: HeaderContent(),
      ),
      // Scrollable content
      Expanded(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: ContentBody(),
        ),
      ),
    ],
  ),
)
```

#### Stat Display Pattern

```dart
// Stat row with icon, label, and value badge
Row(
  children: [
    Icon(icon, size: 16),
    const SizedBox(width: 8),
    Expanded(child: Text(label)),
    Container(
      padding: EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: theme.colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(value),
    ),
  ],
)
```

#### Progress Bar Pattern

```dart
// Linear progress bar with label and current/max values
Column(
  children: [
    Row(
      children: [
        Icon(icon, size: 16, color: color),
        Text(label),
        Spacer(),
        Text('$current / $max'),
      ],
    ),
    LinearProgressIndicator(
      value: current / max,
      backgroundColor: color.withValues(alpha: 0.2),
      valueColor: AlwaysStoppedAnimation<Color>(color),
      minHeight: 8,
    ),
  ],
)
```

## 3. Frameworks and Libraries

### UI Framework

**Framework**: Flutter (Material Design 3)
**Version**: 3.32+
**Material Design**: useMaterial3: true

### Key Dependencies

```yaml
# State Management
provider: ^6.1.2

# AWS Integration
amazon_cognito_identity_dart_2: ^3.6.4

# HTTP Requests
http: ^1.2.2

# Local Storage
shared_preferences: ^2.3.4
flutter_secure_storage: ^9.2.4
idb_shim: ^2.6.7

# Animations
flutter_animate: ^4.5.0

# Utilities
intl: ^0.20.2
uuid: ^4.5.1
```

### Build System

**Build Tool**: Flutter CLI
**Target**: Web (CanvasKit renderer)
**Output**: JavaScript + WebAssembly
**Configuration**: `pubspec.yaml`, `analysis_options.yaml`

### Linting

```bash
# Run before committing
flutter analyze
```

## 4. Asset Management

### Asset Location

```
incremental/assets/
└── images/
    └── background.jpg

portal/assets/
└── images/
    └── background.jpg
```

### Asset Declaration

Assets are declared in `pubspec.yaml`:

```yaml
flutter:
  uses-material-design: true
  assets:
    - assets/images/
```

### Asset Access

```dart
// Loading images
Image.asset('assets/images/background.jpg')

// Background image usage
DecorationImage(
  image: AssetImage('assets/images/background.jpg'),
  fit: BoxFit.cover,
)
```

### Asset Optimization

- Images stored as JPEG for photographs
- No CDN configuration (served via Flutter web)
- Assets bundled in compiled web app
- Background color (`#1F2224`) shown while loading

### Web-Specific Assets

**Location**: `incremental/web/`, `portal/web/`

```
web/
├── favicon.png
├── icons/Icon-192.png
├── index.html
└── manifest.json
```

## 5. Icon System

### Icon Library

**Primary Source**: Material Icons (included with Flutter)
**Usage**: Icons class from `package:flutter/material.dart`

### Icon Implementation

```dart
// Material icons (no import needed beyond material.dart)
Icon(Icons.person)           // Character
Icon(Icons.favorite)         // Health
Icon(Icons.water_drop)       // Essence
Icon(Icons.fitness_center)   // Strength
Icon(Icons.psychology)       // Intelligence
Icon(Icons.auto_stories)     // Story mode
Icon(Icons.terminal)         // MUD mode
```

### Icon Mapping Conventions

**Character Attributes**:

```dart
strength: Icons.fitness_center
agility: Icons.speed
intelligence: Icons.psychology
wisdom: Icons.auto_awesome
charisma: Icons.star
constitution: Icons.shield
```

**Skills**:

```dart
melee: Icons.sports_martial_arts
ranged: Icons.gps_fixed
magic: Icons.auto_fix_high
stealth: Icons.visibility_off
perception: Icons.visibility
crafting: Icons.build
```

**Resources**:

```dart
gold/coins: Icons.monetization_on
experience/xp: Icons.trending_up
reputation: Icons.military_tech
```

**UI Actions**:

```dart
refresh: Icons.refresh
settings: Icons.settings
logout: Icons.exit_to_app
theme: Icons.light_mode / Icons.dark_mode
```

### Icon Styling

```dart
// Standard icon with theme color
Icon(
  Icons.icon_name,
  size: 16,  // or 20, 24 depending on context
  color: theme.colorScheme.onSurfaceVariant,
)

// Semantic colored icon
Icon(
  Icons.favorite,
  size: 16,
  color: Colors.red,  // Health-specific
)
```

### Icon Sizing Standards

- Small (contextual): 12-16px
- Default (body): 20-24px
- Large (emphasis): 32-48px

## 6. Styling Approach

### CSS Methodology

**Approach**: No CSS - pure Flutter widgets with Material Design theming
**Styling Method**: ThemeData + inline widget styling
**Global Styles**: Defined in ThemeProvider
**Component Styles**: Inline using theme references

### Theme-Based Styling

All styling references theme values:

```dart
// Always access theme first
final theme = Theme.of(context);
final colorScheme = theme.colorScheme;

// Use theme colors
Container(
  color: colorScheme.surface,
  child: Text(
    'Content',
    style: theme.textTheme.bodyMedium,
  ),
)
```

### Widget Theming

Global widget themes defined in ThemeProvider:

```dart
ThemeData(
  // Card styling
  cardTheme: CardThemeData(
    elevation: 2,
    color: darkSurface,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(8),
      side: BorderSide(color: darkDivider.withValues(alpha: 0.3)),
    ),
  ),

  // Button styling
  elevatedButtonTheme: ElevatedButtonThemeData(
    style: ElevatedButton.styleFrom(
      foregroundColor: Colors.white,
      backgroundColor: accentPurple,
      minimumSize: const Size(88, 48),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8)
      ),
    ),
  ),

  // Input styling
  inputDecorationTheme: InputDecorationTheme(
    labelStyle: const TextStyle(color: darkTextSecondary),
    floatingLabelStyle: const TextStyle(color: accentPurple),
    filled: true,
    fillColor: darkSurface.withValues(alpha: 0.5),
    enabledBorder: UnderlineInputBorder(
      borderSide: BorderSide(color: darkDivider),
    ),
    focusedBorder: UnderlineInputBorder(
      borderSide: BorderSide(color: accentPurple),
    ),
  ),
)
```

### Responsive Design

**Methodology**: Breakpoint-based with dedicated responsive widgets

**Location**: `incremental/lib/widgets/shared/responsive_layout.dart`

#### Breakpoints

```dart
class Breakpoints {
  static const double mobile = 768;
  static const double tablet = 1200;
}
```

#### Responsive Widgets

```dart
// Layout switching
ResponsiveLayout(
  mobile: MobileLayout(),
  tablet: TabletLayout(),    // Optional, falls back to desktop
  desktop: DesktopLayout(),
)

// Responsive padding
ResponsivePadding(
  mobilePadding: EdgeInsets.all(8.0),
  tabletPadding: EdgeInsets.all(16.0),
  desktopPadding: EdgeInsets.all(24.0),
  child: Content(),
)

// Responsive constraints
ResponsiveConstraints(
  tabletMaxWidth: 800,
  desktopMaxWidth: 1400,
  child: Content(),
)

// Responsive grid
ResponsiveGrid(
  mobileColumns: 1,
  tabletColumns: 2,
  desktopColumns: 3,
  spacing: 16.0,
  children: [widgets],
)
```

#### Device Type Detection

```dart
// Check device type
final deviceType = ResponsiveLayout.getDeviceType(context);

// Boolean helpers
if (ResponsiveLayout.isMobile(context)) {
  // Mobile-specific code
}
```

### Color Usage Patterns

#### State-based Colors

```dart
// Use WidgetState (formerly MaterialState) for interactive elements
WidgetStateProperty.resolveWith((states) {
  if (states.contains(WidgetState.selected)) {
    return accentPurple;
  }
  return darkDivider;
})
```

#### Transparency/Opacity

```dart
// Modern Flutter syntax
color.withValues(alpha: 0.1)   // 10% opacity
color.withValues(alpha: 0.5)   // 50% opacity

// Do not use deprecated withOpacity()
```

### Animation

**Library**: flutter_animate
**Usage**: Minimal - primarily for loading states and transitions
**Performance**: Prefer implicit animations over explicit

## 7. Project Structure

### Root Organization

```
eidolon-engine/
├── incremental/          # Flutter incremental RPG app
├── portal/              # Flutter MUD portal app
├── server/              # Go SSH MUD server
├── lambda/              # Python Lambda functions
├── eidolon/             # Shared Python libraries
├── scripts/             # Deployment orchestration (eidolon_deployment.py)
├── scripts_lua/         # Game logic scripts
├── documentation/       # All documentation
├── data/               # Game configuration
├── cf/                 # CloudFormation templates
└── buildspec/          # CodeBuild specifications
```

### Flutter App Structure

```
incremental/lib/
├── main.dart                    # App entry point
├── config/                      # App configuration
├── constants/                   # App-wide constants (navigation, etc.)
├── models/                      # Data models (Character, Story, etc.)
├── providers/                   # State management (Provider pattern)
│   ├── auth_provider.dart
│   ├── character_provider.dart
│   ├── theme_provider.dart
│   └── timer_provider.dart
├── screens/                     # Full-page routes
│   ├── login_screen.dart
│   ├── character_screen.dart
│   └── game_screen.dart
├── services/                    # Business logic and API
│   ├── auth_service.dart
│   ├── api_service.dart
│   ├── cache_service.dart
│   └── story_polling_service.dart
├── utils/                       # Utility functions
│   ├── error_handler.dart
│   ├── outcome_colors.dart
│   └── time_utils.dart
└── widgets/                     # Reusable components
    ├── game/                   # Game-specific panels
    │   ├── character_panel.dart
    │   ├── story_panel.dart
    │   └── inventory_panel.dart
    ├── shared/                 # Cross-app components
    │   ├── responsive_layout.dart
    │   ├── loading_overlay.dart
    │   └── error_boundary.dart
    ├── story/                  # Story feature widgets
    └── unified/                # Cross-feature components
```

### Feature Organization Patterns

**Pattern**: Feature folders within category folders
**Example**: Game features in `widgets/game/`, story features in `widgets/story/`

**Separation of Concerns**:

- **Screens**: Route-level composition, provider consumption
- **Widgets**: Presentation and UI logic
- **Providers**: State management, business logic orchestration
- **Services**: API calls, data fetching, external integrations
- **Utils**: Pure functions, helpers, formatters

### Naming Conventions

**Files**: `snake_case.dart`
**Classes**: `PascalCase`
**Functions/Variables**: `camelCase`
**Private Members**: `_prefixWithUnderscore`
**Constants**: `lowerCamelCase` or `SCREAMING_CAPS`

## Figma Integration Guidelines

### When Converting Figma Designs to Code

1. **Extract Colors**: Map Figma color values to nearest theme color constants
2. **Typography**: Use Material typography scale, not exact Figma text styles
3. **Spacing**: Round to nearest 4px increment (4, 8, 12, 16, 24)
4. **Icons**: Replace with Material Icons equivalents
5. **Components**: Match to existing component patterns (panels, cards, stat rows)
6. **Responsive**: Design mobile-first, then tablet/desktop variants
7. **State**: Consider loading, error, empty states for all data-driven UI

### Code Generation Preferences

```dart
// Prefer theme references over hardcoded values
// Bad
Container(color: Color(0xFF818CF8))

// Good
Container(color: theme.colorScheme.primary)

// Use const constructors
const SizedBox(height: 16)
const EdgeInsets.all(8)

// Always specify keys for list items
ListView.builder(
  itemBuilder: (context, index) => Widget(
    key: ValueKey(items[index].id),
    // ...
  ),
)
```

### Component Reuse Priority

When implementing Figma designs:

1. **First**: Check for existing widgets in `widgets/shared/`
2. **Second**: Extend or compose existing game/story widgets
3. **Third**: Create new widget following established patterns
4. **Always**: Use ThemeProvider colors, not hardcoded values

### API Integration Pattern

All data from Figma designs must integrate with existing API patterns:

```dart
// Service layer handles API calls
class ApiService {
  Future<Character?> getCharacterById(String characterId) async {
    // API call implementation
  }
}

// Provider layer manages state
class CharacterProvider extends ChangeNotifier {
  Character? _currentCharacter;

  Future<void> loadCharacter(String id) async {
    _currentCharacter = await _apiService.getCharacterById(id);
    notifyListeners();
  }
}

// Widget layer consumes via Provider
class MyWidget extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<CharacterProvider>(
      builder: (context, provider, child) {
        if (provider.currentCharacter == null) {
          return CircularProgressIndicator();
        }
        return CharacterDisplay(character: provider.currentCharacter!);
      },
    );
  }
}
```

## Design System Constraints

### No Custom Fonts

- Use system default fonts only
- Typography scale from Material Design 2021

### No External CSS

- All styling via Flutter widgets
- No separate CSS files or inline styles

### No Custom Icon Sets

- Material Icons only (included with Flutter)
- SVG icons only if absolutely necessary (rare)

### Limited Asset Usage

- Minimal image assets (primarily backgrounds)
- No icon fonts beyond Material Icons
- No sprite sheets or icon sets

### Color Limitations

- All colors defined in theme provider
- No dynamic color generation
- Theme switching between light/dark only

### Responsive Strategy

- Breakpoint-based responsive design
- Mobile-first approach
- 3 breakpoints: mobile (< 768), tablet (768-1200), desktop (> 1200)

## Code Style Requirements

All generated code must follow project coding standards:

**Reference**: `documentation/flutter-style.md`

**Key Rules**:

- Maximum line length: 132 characters
- No private methods (use public or package-private)
- Prefer const constructors
- Always use theme colors via `Theme.of(context)`
- Provider pattern for state management
- PascalCase for JSON field names (API integration)
- Spread syntax for conditional widget lists: `if (condition) ...[widgets]`

## Testing Considerations

When implementing Figma designs, ensure:

- Widget tests for new components
- Responsive behavior verification at all breakpoints
- Theme switching (light/dark) visual testing
- Loading/error state variations
- Accessibility (semantic labels, contrast ratios)

## Performance Guidelines

- Use const constructors wherever possible
- Avoid rebuilding entire widget trees
- Cache expensive computations
- Lazy-load data with pagination
- Use keys for list items to optimize rebuilds
- Profile frame rendering for smooth 60fps

## Accessibility

- Minimum touch target: 48x48 logical pixels
- Color contrast ratios: AA compliance
- Semantic labels for screen readers
- Keyboard navigation support (via `KeyboardShortcuts` widget)
- Focus indicators for interactive elements

## Deployment Context

Generated code will be deployed as:

- Flutter web application (JavaScript + WebAssembly)
- Served via AWS CloudFront CDN
- Integrated with AWS Lambda backend
- Authentication via AWS Cognito
- Target browsers: Modern evergreen browsers with WebGL support

## Summary Checklist

When converting Figma designs:

- [ ] Colors mapped to theme constants
- [ ] Typography uses Material Design scale
- [ ] Spacing in 4px increments
- [ ] Icons from Material Icons library
- [ ] Components follow existing patterns
- [ ] Responsive at mobile/tablet/desktop breakpoints
- [ ] Theme-aware (light/dark mode)
- [ ] State management via Provider
- [ ] API integration following service pattern
- [ ] const constructors used
- [ ] Keys on list items
- [ ] Accessibility considerations
- [ ] Performance optimizations
- [ ] Code follows Flutter style guide
- [ ] Maximum 132 character lines
