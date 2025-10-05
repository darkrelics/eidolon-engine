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
    const Color darkBackground = Color(0xFF1F2224);
    const Color darkSurface = Color(0xFF2A2D31);
    const Color accentPurple = Color(0xFF818CF8);
    const Color darkTextPrimary = Color(0xFFE6E6E6);
    const Color darkTextSecondary = Color(0xFFAEAEB2);
    const Color darkDivider = Color(0xFF505050);

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: accentPurple,
        brightness: Brightness.dark,
        primary: accentPurple,
        onPrimary: Colors.white,
        secondary: accentPurple.withAlpha(230),
        onSecondary: Colors.white,
        surface: darkSurface,
        onSurface: darkTextPrimary,
        error: const Color(0xFFD32F2F),
        onError: Colors.white,
        outline: darkDivider,
      ),
      scaffoldBackgroundColor: darkBackground,
      cardTheme: CardThemeData(
        elevation: 2,
        color: darkSurface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: BorderSide(color: darkDivider.withValues(alpha: 0.3)),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        labelStyle: const TextStyle(color: darkTextSecondary),
        floatingLabelStyle: const TextStyle(color: accentPurple),
        hintStyle: TextStyle(color: darkTextSecondary.withValues(alpha: 0.7)),
        enabledBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: darkDivider),
        ),
        focusedBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: accentPurple),
        ),
        errorBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: Color(0xFFD32F2F)),
        ),
        focusedErrorBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: Color(0xFFD32F2F)),
        ),
        filled: true,
        fillColor: darkSurface.withValues(alpha: 0.5),
      ),
      textTheme: Typography.material2021().white.copyWith(
        bodyLarge: const TextStyle(color: darkTextPrimary),
        bodyMedium: const TextStyle(color: darkTextPrimary),
        titleLarge: const TextStyle(color: darkTextPrimary),
        titleMedium: const TextStyle(color: darkTextPrimary),
        titleSmall: const TextStyle(color: darkTextPrimary),
        labelLarge: const TextStyle(color: darkTextPrimary),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          foregroundColor: Colors.white,
          backgroundColor: accentPurple,
          disabledForegroundColor: Colors.white54,
          disabledBackgroundColor: accentPurple.withValues(alpha: 0.3),
          minimumSize: const Size(88, 48),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: accentPurple,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: accentPurple,
          side: const BorderSide(color: accentPurple),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: darkBackground,
        foregroundColor: darkTextPrimary,
        elevation: 0,
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: accentPurple,
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(foregroundColor: darkTextPrimary),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: accentPurple,
        foregroundColor: Colors.white,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: darkSurface,
        contentTextStyle: const TextStyle(color: darkTextPrimary),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        behavior: SnackBarBehavior.floating,
      ),
      dividerTheme: const DividerThemeData(color: darkDivider, thickness: 1),
      switchTheme: SwitchThemeData(
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return accentPurple.withValues(alpha: 0.5);
          }
          return darkDivider;
        }),
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return accentPurple;
          }
          return darkTextSecondary;
        }),
      ),
    );
  }

  /// Creates the light theme for the application
  static ThemeData _buildLightTheme() {
    const Color primaryBlue = Color(0xFF2196F3);
    const Color lightBackground = Colors.white;
    const Color lightSurface = Colors.white;
    const Color lightTextPrimary = Color(0xDE000000); // Black 87%
    const Color lightTextSecondary = Color(0x8A000000); // Black 54%
    const Color lightDivider = Color(0xFFE0E0E0);

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primaryBlue,
        primary: primaryBlue,
        onPrimary: Colors.white,
        secondary: primaryBlue.withAlpha(230),
        onSecondary: Colors.white,
        surface: lightSurface,
        onSurface: lightTextPrimary,
        error: const Color(0xFFD32F2F),
        onError: Colors.white,
        outline: lightDivider,
      ),
      scaffoldBackgroundColor: lightBackground,
      cardTheme: CardThemeData(
        elevation: 2,
        color: lightSurface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: lightDivider),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        labelStyle: const TextStyle(color: lightTextSecondary),
        floatingLabelStyle: const TextStyle(color: primaryBlue),
        hintStyle: TextStyle(color: lightTextSecondary.withValues(alpha: 0.7)),
        enabledBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: lightDivider),
        ),
        focusedBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: primaryBlue),
        ),
        errorBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: Color(0xFFD32F2F)),
        ),
        focusedErrorBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: Color(0xFFD32F2F)),
        ),
        filled: true,
        fillColor: lightSurface.withValues(alpha: 0.05),
      ),
      textTheme: Typography.material2021().black.copyWith(
        bodyLarge: const TextStyle(color: lightTextPrimary),
        bodyMedium: const TextStyle(color: lightTextPrimary),
        titleLarge: const TextStyle(color: lightTextPrimary),
        titleMedium: const TextStyle(color: lightTextPrimary),
        titleSmall: const TextStyle(color: lightTextPrimary),
        labelLarge: const TextStyle(color: lightTextPrimary),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          foregroundColor: Colors.white,
          backgroundColor: primaryBlue,
          disabledForegroundColor: Colors.white54,
          disabledBackgroundColor: primaryBlue.withValues(alpha: 0.3),
          minimumSize: const Size(88, 48),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryBlue,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: primaryBlue,
          side: const BorderSide(color: primaryBlue),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: lightBackground,
        foregroundColor: lightTextPrimary,
        elevation: 0,
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: primaryBlue,
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(foregroundColor: lightTextPrimary),
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: primaryBlue,
        foregroundColor: Colors.white,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: lightSurface,
        contentTextStyle: const TextStyle(color: lightTextPrimary),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        behavior: SnackBarBehavior.floating,
      ),
      dividerTheme: const DividerThemeData(color: lightDivider, thickness: 1),
      switchTheme: SwitchThemeData(
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return primaryBlue.withValues(alpha: 0.5);
          }
          return lightDivider;
        }),
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return primaryBlue;
          }
          return lightTextSecondary;
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
