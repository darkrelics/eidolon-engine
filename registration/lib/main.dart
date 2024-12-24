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
      home: const AuthScreen(), // Changed to AuthScreen
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


  CognitoUser? get currentUser => _currentUser;
  bool get isVerificationMode => _isVerificationMode;
  bool get isSignUpMode => _isSignUpMode;
  String get message => _message;
  bool get isLoading => _isLoading;
    
    late final CognitoUserPool userPool;
    
    AuthState(){
    final userPoolId = const String.fromEnvironment('USER_POOL_ID');
    final clientId = const String.fromEnvironment('CLIENT_ID');
    final clientSecret = const String.fromEnvironment('CLIENT_SECRET');

    if (userPoolId.isEmpty || clientId.isEmpty || clientSecret.isEmpty) {
      _message = 'Error: Missing required Cognito configuration';
      notifyListeners();
      return;
    }

    try {
      userPool = CognitoUserPool(
        userPoolId,
        clientId,
        clientSecret: clientSecret,
      );
    } catch (e) {
       _message = 'Error initializing Cognito: ${e.toString()}';
        notifyListeners();
    }
  }
  
  Future<void> signUp() async {
    _isLoading = true;
    notifyListeners();

    try {
      final signUpResult = await userPool.signUp(
        _emailController.text,
         _passwordController.text,
        userAttributes: [
          AttributeArg(name: 'email', value: _emailController.text),
        ],
      );
        _isLoading = false;
        if (signUpResult.userConfirmed ?? false) {
          _message = 'User registered successfully. You can now log in.';
          _isSignUpMode = false;
        } else {
         _message = 'Verification code sent. Please check your email and enter it below.';
          _isVerificationMode = true;
        }
      notifyListeners();
    } on CognitoClientException catch (e) {
         _isLoading = false;
        _message = 'Cognito Error: ${e.code} - ${e.message}';
      notifyListeners();
    } catch (e) {
        _isLoading = false;
        _message = 'An unexpected error occurred: ${e.toString()}';
        notifyListeners();
    }
  }

  Future<void> confirmRegistration() async {
    _isLoading = true;
    notifyListeners();
    try {
      final user = CognitoUser(_emailController.text, userPool);
      await user.confirmRegistration(_verificationCodeController.text);
      _isLoading = false;
      _message = 'Email confirmed successfully. You can now log in.';
        _isVerificationMode = false;
      notifyListeners();
    } on CognitoClientException catch (e) {
       _isLoading = false;
      _message = 'Cognito Error: ${e.code} - ${e.message}';
      notifyListeners();
    }
      catch (e) {
          _isLoading = false;
        _message = 'An unexpected error occurred: ${e.toString()}';
      notifyListeners();
    }
  }
  
  Future<void> signIn() async {
     _isLoading = true;
     notifyListeners();
    try {
      final user = CognitoUser(_emailController.text, userPool);
      final authDetails = AuthenticationDetails(username: _emailController.text, password: _passwordController.text);
      await user.authenticateUser(authDetails);
      _isLoading = false;
      _message = 'Login Successful!';
      _isSignUpMode = false;
        _currentUser = user;
        notifyListeners();
    } on CognitoClientException catch (e) {
        _isLoading = false;
       _message = 'Cognito Error: ${e.code} - ${e.message}';
        notifyListeners();
    } catch (e) {
        _isLoading = false;
        _message = 'An unexpected error occurred: ${e.toString()}';
      notifyListeners();
    }
  }
  
  void toggleAuthMode(){
      _message = '';
      _isSignUpMode = !_isSignUpMode;
      notifyListeners();
  }
}

class AuthScreen extends StatelessWidget {
  const AuthScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.watch<AuthState>().isSignUpMode ? 'Sign Up' : 'Sign In'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Form(
          child: Consumer<AuthState>(builder: (context, authState, child) => Column(
            children: <Widget>[
               if(authState.isSignUpMode) ...[
                    TextFormField(
                        controller: authState._emailController,
                         decoration: const InputDecoration(labelText: 'Email'),
                          validator: (value) {
                              if (value == null || value.isEmpty) {
                                   return 'Please enter your email';
                                  }
                                   return null;
                          },
                     ),
                      TextFormField(
                          controller: authState._passwordController,
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
                            onPressed: authState.isLoading ? null : () => authState.signUp(),
                            child: const Text('Sign Up'),
                        ),
                        const SizedBox(height: 20),
                         TextButton(onPressed: () => authState.toggleAuthMode(), child: const Text("Already have an account? Sign in")),
                ] else if (!authState.isVerificationMode) ...[
                   TextFormField(
                        controller: authState._emailController,
                         decoration: const InputDecoration(labelText: 'Email'),
                          validator: (value) {
                              if (value == null || value.isEmpty) {
                                   return 'Please enter your email';
                                  }
                                   return null;
                          },
                     ),
                      TextFormField(
                          controller: authState._passwordController,
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
                        onPressed: authState.isLoading ? null : () => authState.signIn(),
                         child: const Text('Sign In'),
                        ),
                       const SizedBox(height: 20),
                        TextButton(onPressed: () => authState.toggleAuthMode(), child: const Text("Need an Account? Sign up")),
                 ] else ...[
                 TextFormField(
                  controller: authState._verificationCodeController,
                   decoration: const InputDecoration(labelText: 'Verification Code'),
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                       return 'Please enter verification code';
                    }
                    return null;
                    },
                   ),
                 const SizedBox(height: 20),
                   ElevatedButton(
                    onPressed: authState.isLoading ? null : () => authState.confirmRegistration(),
                     child: const Text('Verify'),
                    ),
                ],
             const SizedBox(height: 20),
             if (authState.isLoading) const CircularProgressIndicator() else Text(authState.message),
            ],
          ),
        ),
      ),
    );
  }
}