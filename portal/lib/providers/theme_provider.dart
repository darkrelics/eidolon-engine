import 'package:flutter/material.dart';

/// Manages application theme state and provides theme data
class ThemeProvider extends ChangeNotifier {
  ThemeData _themeData;
  
  /// Creates a new ThemeProvider instance
  factory ThemeProvider.create() {
    return ThemeProvider._internal();
  }
  
  ThemeProvider._internal() : _themeData = _buildDarkTheme();
  
  ThemeData get theme => _themeData;
  
  /// Creates the dark theme for the application
  static ThemeData _buildDarkTheme() {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.white,
        brightness: Brightness.dark,
        primary: Colors.white,
        onPrimary: Colors.black,
        secondary: Colors.white70,
        onSecondary: Colors.black,
        surface: Colors.black,
        onSurface: Colors.white,
        error: Colors.red.shade400,
        onError: Colors.black,
      ),
      scaffoldBackgroundColor: Colors.black,
      inputDecorationTheme: InputDecorationTheme(
        labelStyle: const TextStyle(color: Colors.white70),
        floatingLabelStyle: const TextStyle(color: Colors.white),
        enabledBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.white70),
        ),
        focusedBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.white),
        ),
        errorBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.red.shade400),
        ),
        focusedErrorBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.red.shade400),
        ),
      ),
      textTheme: Typography.material2021().white.copyWith(
        bodyLarge: const TextStyle(color: Colors.white),
        bodyMedium: const TextStyle(color: Colors.white),
        titleLarge: const TextStyle(color: Colors.white),
        titleMedium: const TextStyle(color: Colors.white),
        titleSmall: const TextStyle(color: Colors.white),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          foregroundColor: Colors.black,
          backgroundColor: Colors.white,
          disabledForegroundColor: Colors.black54,
          disabledBackgroundColor: Colors.white54,
          minimumSize: const Size(88, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        elevation: 0,
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: Colors.white,
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          foregroundColor: Colors.white,
        ),
      ),
    );
  }
  
  /// Updates the theme data and notifies listeners
  void updateTheme(ThemeData newTheme) {
    _themeData = newTheme;
    notifyListeners();
  }
  
  /// For future use - could implement theme switching
  void toggleTheme() {
    // Implementation for theme switching could be added here
    // For now, we only have dark theme
  }
}