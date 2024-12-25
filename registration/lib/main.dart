import 'package:flutter/material.dart';
import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:provider/provider.dart';

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (context) => AuthState(),
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cognito Email Verification',
      theme: ThemeData(
        primarySwatch: Colors.blue,
      ),
      home: const AuthScreen(),
    );
  }
}

class AuthState extends ChangeNotifier {
  final _emailController = TextEditingController();
  final _verificationCodeController = TextEditingController();
  final _passwordController = TextEditingController();
  String _message = '';
  bool _isLoading = false;
  bool _isVerificationMode = false;
  bool _isSignUpMode = true;
  CognitoUser? _currentUser;
  late final CognitoUserPool userPool;

  // Getters for controllers
  TextEditingController get emailController => _emailController;
  TextEditingController get verificationCodeController =>
      _verificationCodeController;
  TextEditingController get passwordController => _passwordController;

  // Public getters for state
  CognitoUser? get currentUser => _currentUser;
  bool get isVerificationMode => _isVerificationMode;
  bool get isSignUpMode => _isSignUpMode;
  String get message => _message;
  bool get isLoading => _isLoading;

  AuthState() {
    _initializeCognito();
  }

  void _initializeCognito() {
    final userPoolId = const String.fromEnvironment('USER_POOL_ID');
    final clientId = const String.fromEnvironment('CLIENT_ID');
    final clientSecret = const String.fromEnvironment('CLIENT_SECRET');

    if (userPoolId.isEmpty || clientId.isEmpty || clientSecret.isEmpty) {
      _updateMessage('Error: Missing required Cognito configuration');
      return;
    }

    try {
      userPool = CognitoUserPool(
        userPoolId,
        clientId,
        clientSecret: clientSecret,
      );
    } catch (e) {
      _updateMessage('Error initializing Cognito: ${e.toString()}');
    }
  }

  void _updateMessage(String message) {
    _message = message;
    notifyListeners();
  }

  void _setLoading(bool loading) {
    _isLoading = loading;
    notifyListeners();
  }

  Future<void> signUp() async {
    if (!_validateInputs()) return;

    _setLoading(true);
    try {
      final signUpResult = await userPool.signUp(
        _emailController.text,
        _passwordController.text,
        userAttributes: [
          AttributeArg(name: 'email', value: _emailController.text),
        ],
      );

      if (signUpResult.userConfirmed ?? false) {
        _updateMessage('User registered successfully. You can now log in.');
        _isSignUpMode = false;
      } else {
        _updateMessage(
            'Verification code sent. Please check your email and enter it below.');
        _isVerificationMode = true;
      }
    } on CognitoClientException catch (e) {
      _updateMessage('Cognito Error: ${e.code} - ${e.message}');
    } catch (e) {
      _updateMessage('An unexpected error occurred: ${e.toString()}');
    } finally {
      _setLoading(false);
    }
  }

  Future<void> confirmRegistration() async {
    if (_verificationCodeController.text.isEmpty) {
      _updateMessage('Please enter the verification code');
      return;
    }

    _setLoading(true);
    try {
      final user = CognitoUser(_emailController.text, userPool);
      await user.confirmRegistration(_verificationCodeController.text);
      _updateMessage('Email confirmed successfully. You can now log in.');
      _isVerificationMode = false;
    } on CognitoClientException catch (e) {
      _updateMessage('Cognito Error: ${e.code} - ${e.message}');
    } catch (e) {
      _updateMessage('An unexpected error occurred: ${e.toString()}');
    } finally {
      _setLoading(false);
    }
  }

  Future<void> signIn() async {
    if (!_validateInputs()) return;

    _setLoading(true);
    try {
      final user = CognitoUser(_emailController.text, userPool);
      final authDetails = AuthenticationDetails(
        username: _emailController.text,
        password: _passwordController.text,
      );

      await user.authenticateUser(authDetails);
      _currentUser = user;
      _updateMessage('Login Successful!');
      _isSignUpMode = false;
    } on CognitoClientException catch (e) {
      _updateMessage('Cognito Error: ${e.code} - ${e.message}');
    } catch (e) {
      _updateMessage('An unexpected error occurred: ${e.toString()}');
    } finally {
      _setLoading(false);
    }
  }

  bool _validateInputs() {
    if (_emailController.text.isEmpty || _passwordController.text.isEmpty) {
      _updateMessage('Please fill in all fields');
      return false;
    }
    return true;
  }

  void toggleAuthMode() {
    _message = '';
    _isSignUpMode = !_isSignUpMode;
    notifyListeners();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _verificationCodeController.dispose();
    _passwordController.dispose();
    super.dispose();
  }
}

class AuthScreen extends StatelessWidget {
  const AuthScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
            context.watch<AuthState>().isSignUpMode ? 'Sign Up' : 'Sign In'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Form(
          child: Consumer<AuthState>(
            builder: (context, authState, child) => Column(
              children: <Widget>[
                if (authState.isSignUpMode) ...[
                  TextFormField(
                    controller: authState.emailController,
                    decoration: const InputDecoration(labelText: 'Email'),
                    keyboardType: TextInputType.emailAddress,
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your email';
                      }
                      return null;
                    },
                  ),
                  TextFormField(
                    controller: authState.passwordController,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'Password'),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your password';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed:
                        authState.isLoading ? null : () => authState.signUp(),
                    child: const Text('Sign Up'),
                  ),
                  const SizedBox(height: 20),
                  TextButton(
                    onPressed: () => authState.toggleAuthMode(),
                    child: const Text('Already have an account? Sign in'),
                  ),
                ] else if (!authState.isVerificationMode) ...[
                  TextFormField(
                    controller: authState.emailController,
                    decoration: const InputDecoration(labelText: 'Email'),
                    keyboardType: TextInputType.emailAddress,
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your email';
                      }
                      return null;
                    },
                  ),
                  TextFormField(
                    controller: authState.passwordController,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'Password'),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter your password';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed:
                        authState.isLoading ? null : () => authState.signIn(),
                    child: const Text('Sign In'),
                  ),
                  const SizedBox(height: 20),
                  TextButton(
                    onPressed: () => authState.toggleAuthMode(),
                    child: const Text('Need an Account? Sign up'),
                  ),
                ] else ...[
                  TextFormField(
                    controller: authState.verificationCodeController,
                    decoration:
                        const InputDecoration(labelText: 'Verification Code'),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Please enter verification code';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed: authState.isLoading
                        ? null
                        : () => authState.confirmRegistration(),
                    child: const Text('Verify'),
                  ),
                ],
                const SizedBox(height: 20),
                if (authState.isLoading)
                  const CircularProgressIndicator()
                else if (authState.message.isNotEmpty)
                  Text(
                    authState.message,
                    style: TextStyle(
                      color: authState.message.toLowerCase().contains('error')
                          ? Colors.red
                          : Colors.green,
                    ),
                    textAlign: TextAlign.center,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
