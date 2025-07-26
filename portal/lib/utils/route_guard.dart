// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson

/// Route guard utility for protecting sensitive routes
class RouteGuard {
  // Private constructor to prevent instantiation
  RouteGuard._();

  // List of routes that require authentication
  static const Set<String> _protectedRoutes = {
    '/character-management',
    '/character-creation',
    '/inventory',
    '/profile',
    '/settings',
    '/account-settings',
    '/quests',
    '/guild',
    '/achievements',
  };

  // List of public routes that don't require authentication
  static const Set<String> _publicRoutes = {'/', '/login', '/register', '/forgot-password', '/terms', '/privacy', '/about'};

  /// Checks if a route is protected
  static bool isProtectedRoute(String? routeName) {
    if (routeName == null) return false;
    return _protectedRoutes.contains(routeName);
  }

  /// Checks if a route is public
  static bool isPublicRoute(String? routeName) {
    if (routeName == null) return false;
    return _publicRoutes.contains(routeName);
  }

  /// Gets the appropriate redirect route based on authentication state
  static String getRedirectRoute(bool isAuthenticated, String? currentRoute) {
    if (isAuthenticated) {
      // If authenticated and on a public route, go to character management
      if (currentRoute != null && _publicRoutes.contains(currentRoute)) {
        return '/character-management';
      }
      // Otherwise, stay on current route
      return currentRoute ?? '/character-management';
    } else {
      // If not authenticated and on a protected route, go to login
      if (currentRoute != null && isProtectedRoute(currentRoute)) {
        return '/login';
      }
      // Otherwise, stay on current route or go to splash
      return currentRoute ?? '/';
    }
  }

  /// Validates the security level required for a route
  static bool validateSecurityLevel(String? routeName, int userLevel) {
    // Example: Different routes might require different security levels
    switch (routeName) {
      case '/admin':
        return userLevel >= 3; // Admin level
      case '/moderator':
        return userLevel >= 2; // Moderator level
      default:
        return userLevel >= 1; // Regular user level
    }
  }
}
