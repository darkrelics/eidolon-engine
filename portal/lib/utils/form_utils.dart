// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson

import 'package:flutter/material.dart';

/// Utilities for form handling with better null safety
class FormUtils {
  // Prevent instantiation
  FormUtils._();

  /// Safely validates a form, handling null cases
  static bool validateForm(BuildContext context) {
    try {
      // Check if context is mounted before accessing Form
      if (!context.mounted) {
        debugPrint('Context is not mounted, skipping form validation');
        return false;
      }

      bool foundForm = false;
      bool isValid = false;

      // Visit ancestor elements to find Form
      Element? rootElement = context as Element?;
      if (rootElement != null) {
        rootElement.visitAncestorElements((element) {
          if (element.widget is Form) {
            foundForm = true;

            // Get the FormState directly
            try {
              final formState = Form.of(context);
              isValid = formState.validate();
            } catch (e) {
              debugPrint('Error accessing form state: $e');
            }

            return false; // Stop traversal
          }
          return true; // Continue traversal
        });
      }

      if (!foundForm) {
        debugPrint('No Form widget found in the widget tree');
      }

      return isValid;
    } catch (e) {
      debugPrint('Error validating form: $e');
      return false;
    }
  }
}
