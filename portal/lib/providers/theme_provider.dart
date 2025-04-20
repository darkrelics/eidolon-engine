// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson
//
// Licensed under the Apache License, Version 2.0 (the “License”);
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an “AS IS” BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Manages application theme state and provides theme data
class ThemeProvider extends ChangeNotifier {
  static const String _themeKey = 'theme_mode';
  ThemeData _themeData;
  ThemeMode _themeMode;
  bool _isInitialized = false;

  /// Creates a new ThemeProvider instance
  factory ThemeProvider.create() {
    return ThemeProvider._internal();
  }

  ThemeProvider._internal()
    : _themeData = _buildDarkTheme(),
      _themeMode = ThemeMode.dark {
    _initializeTheme();
  }

  ThemeData get theme => _themeData;
  ThemeMode get themeMode => _themeMode;
  bool get isDarkMode => _themeMode == ThemeMode.dark;
  bool get isInitialized => _isInitialized;

  /// Initializes theme from shared preferences
  Future<void> _initializeTheme() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedTheme = prefs.getString(_themeKey);

      if (savedTheme != null) {
        _themeMode = ThemeMode.values.firstWhere(
          (mode) => mode.name == savedTheme,
          orElse: () => ThemeMode.dark,
        );
        _updateThemeData();
      }
    } catch (e) {
      debugPrint('Error initializing theme: $e');
    } finally {
      _isInitialized = true;
      notifyListeners();
    }
  }

  /// Updates the theme data based on the current theme mode
  void _updateThemeData() {
    switch (_themeMode) {
      case ThemeMode.dark:
        _themeData = _buildDarkTheme();
        break;
      case ThemeMode.light:
        _themeData = _buildLightTheme();
        break;
      case ThemeMode.system:
        // ThemeMode.system is handled by MaterialApp's themeMode property
        _themeData = _buildDarkTheme(); // Fallback to dark theme
        break;
    }
    _updateSystemChrome();
  }

  /// Updates system UI overlay style to match theme
  void _updateSystemChrome() {
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness:
            _themeMode == ThemeMode.dark ? Brightness.light : Brightness.dark,
        systemNavigationBarColor: _themeData.scaffoldBackgroundColor,
        systemNavigationBarIconBrightness:
            _themeMode == ThemeMode.dark ? Brightness.light : Brightness.dark,
      ),
    );
  }

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
        surface: Colors.grey[900]!,
        onSurface: Colors.white,
        error: Colors.red.shade400,
        onError: Colors.black,
        outline: Colors.white.withValues(alpha: 0.2),
      ),
      scaffoldBackgroundColor: Colors.black,
      cardTheme: CardTheme(
        elevation: 0,
        color: Colors.grey[850],
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: Colors.white.withValues(alpha: 0.1)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        labelStyle: TextStyle(color: Colors.white.withValues(alpha: 0.7)),
        floatingLabelStyle: const TextStyle(color: Colors.white),
        hintStyle: TextStyle(color: Colors.white.withValues(alpha: 0.5)),
        enabledBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.3)),
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
        filled: true,
        fillColor: Colors.black.withValues(alpha: 0.05),
      ),
      textTheme: Typography.material2021().white.copyWith(
        bodyLarge: const TextStyle(color: Colors.white),
        bodyMedium: const TextStyle(color: Colors.white),
        titleLarge: const TextStyle(color: Colors.white),
        titleMedium: const TextStyle(color: Colors.white),
        titleSmall: const TextStyle(color: Colors.white),
        labelLarge: const TextStyle(color: Colors.white),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          foregroundColor: Colors.black,
          backgroundColor: Colors.white,
          disabledForegroundColor: Colors.black54,
          disabledBackgroundColor: Colors.white30,
          minimumSize: const Size(88, 48),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: Colors.white,
          side: const BorderSide(color: Colors.white),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
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
        style: IconButton.styleFrom(foregroundColor: Colors.white),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: Colors.grey[850],
        contentTextStyle: const TextStyle(color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        behavior: SnackBarBehavior.floating,
      ),
      dividerTheme: DividerThemeData(
        color: Colors.white.withValues(alpha: 0.1),
        thickness: 1,
      ),
      switchTheme: SwitchThemeData(
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return Colors.white.withValues(alpha: 0.5);
          }
          return Colors.white.withValues(alpha: 0.2);
        }),
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return Colors.white;
          }
          return Colors.grey;
        }),
      ),
    );
  }

  /// Creates the light theme for the application
  static ThemeData _buildLightTheme() {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.black,
        primary: Colors.black,
        onPrimary: Colors.white,
        secondary: Colors.grey[800]!,
        onSecondary: Colors.white,
        surface: Colors.white,
        onSurface: Colors.black,
        error: Colors.red.shade400,
        onError: Colors.white,
        outline: Colors.black.withValues(alpha: 0.2),
      ),
      scaffoldBackgroundColor: Colors.white,
      cardTheme: CardTheme(
        elevation: 0,
        color: Colors.grey[100],
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: Colors.black.withValues(alpha: 0.1)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        labelStyle: TextStyle(color: Colors.black.withValues(alpha: 0.7)),
        floatingLabelStyle: const TextStyle(color: Colors.black),
        hintStyle: TextStyle(color: Colors.black.withValues(alpha: 0.5)),
        enabledBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.black.withValues(alpha: 0.3)),
        ),
        focusedBorder: const UnderlineInputBorder(),
        errorBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.red.shade400),
        ),
        focusedErrorBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: Colors.red.shade400),
        ),
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05),
      ),
      textTheme: Typography.material2021().black.copyWith(
        bodyLarge: const TextStyle(color: Colors.black),
        bodyMedium: const TextStyle(color: Colors.black),
        titleLarge: const TextStyle(color: Colors.black),
        titleMedium: const TextStyle(color: Colors.black),
        titleSmall: const TextStyle(color: Colors.black),
        labelLarge: const TextStyle(color: Colors.black),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          foregroundColor: Colors.white,
          backgroundColor: Colors.black,
          disabledForegroundColor: Colors.white54,
          disabledBackgroundColor: Colors.black26,
          minimumSize: const Size(88, 48),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: Colors.black,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: Colors.black,
          side: const BorderSide(),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        elevation: 0,
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: Colors.black,
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(foregroundColor: Colors.black),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: Colors.grey[850],
        contentTextStyle: const TextStyle(color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
      dividerTheme: DividerThemeData(
        color: Colors.black.withValues(alpha: 0.1),
        thickness: 1,
      ),
      switchTheme: SwitchThemeData(
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return Colors.black.withValues(alpha: 0.5);
          }
          return Colors.black.withValues(alpha: 0.2);
        }),
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return Colors.black;
          }
          return Colors.grey;
        }),
      ),
    );
  }

  /// Updates the theme mode and saves the preference
  Future<void> setThemeMode(ThemeMode mode) async {
    if (_themeMode == mode) return;

    _themeMode = mode;
    _updateThemeData();
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_themeKey, mode.name);
    } catch (e) {
      debugPrint('Error saving theme preference: $e');
    }
  }

  /// Toggles between light and dark themes
  Future<void> toggleTheme() async {
    final newMode =
        _themeMode == ThemeMode.light ? ThemeMode.dark : ThemeMode.light;
    await setThemeMode(newMode);
  }

  /// Sets theme mode to follow system settings
  Future<void> useSystemTheme() async {
    await setThemeMode(ThemeMode.system);
  }

  /// Gets theme data based on theme mode and system brightness
  ThemeData getThemeForMode(BuildContext context) {
    if (_themeMode == ThemeMode.system) {
      final brightness = MediaQuery.of(context).platformBrightness;
      return brightness == Brightness.dark
          ? _buildDarkTheme()
          : _buildLightTheme();
    }
    return _themeData;
  }
}
