// Eidolon Engine
//
// Copyright 2024‑2025 Jason Robinson

import 'package:flutter/material.dart';

/// A provider widget that makes a FormState accessible to descendants
class FormStateProvider extends StatefulWidget {
  final Widget child;
  final GlobalKey<FormState> formKey;
  final AutovalidateMode autovalidateMode;
  final PopInvokedWithResultCallback? onPopInvokedWithResult;

  const FormStateProvider({
    super.key,
    required this.child,
    required this.formKey,
    this.autovalidateMode = AutovalidateMode.onUserInteraction,
    this.onPopInvokedWithResult,
  });

  @override
  State<FormStateProvider> createState() => _FormStateProviderState();
}

class _FormStateProviderState extends State<FormStateProvider> {
  @override
  Widget build(BuildContext context) {
    return Form(
      key: widget.formKey,
      autovalidateMode: widget.autovalidateMode,
      onPopInvokedWithResult: widget.onPopInvokedWithResult,
      canPop: true,
      child: widget.child,
    );
  }
}

/// Utilities for accessing and validating form state
class FormStateUtil {
  // Prevent instantiation
  FormStateUtil._();

  /// Validates the form with the given key
  static bool validateForm(GlobalKey<FormState> formKey) {
    final FormState? formState = formKey.currentState;
    if (formState != null) {
      return formState.validate();
    }
    return false;
  }

  /// Saves the current form values
  static void saveForm(GlobalKey<FormState> formKey) {
    final FormState? formState = formKey.currentState;
    if (formState != null) {
      formState.save();
    }
  }

  /// Resets the form to its initial state
  static void resetForm(GlobalKey<FormState> formKey) {
    final FormState? formState = formKey.currentState;
    if (formState != null) {
      formState.reset();
    }
  }
}
