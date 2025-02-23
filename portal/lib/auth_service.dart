import 'package:amazon_cognito_identity_dart_2/cognito.dart';

class AuthService {
  late final CognitoUserPool userPool;
  CognitoUser? _currentUser;
  CognitoUserSession? _session;

  AuthService() {
    _initializeCognito();
  }

  void _initializeCognito() {
    final userPoolId = const String.fromEnvironment(
      'USER_POOL_ID',
      defaultValue: bool.fromEnvironment('dart.vm.product') ? '' : 'dev-user-pool-id',
    );
    final clientId = const String.fromEnvironment(
      'CLIENT_ID',
      defaultValue: bool.fromEnvironment('dart.vm.product') ? '' : 'dev-client-id',
    );
    final clientSecret = const String.fromEnvironment(
      'CLIENT_SECRET',
      defaultValue: bool.fromEnvironment('dart.vm.product') ? '' : 'dev-client-secret',
    );

    if (userPoolId.isEmpty || clientId.isEmpty || clientSecret.isEmpty) {
      throw Exception('Missing required Cognito configuration');
    }

    userPool = CognitoUserPool(
      userPoolId,
      clientId,
      clientSecret: clientSecret,  // Changed from secretKey to clientSecret
    );
  }

  Future<CognitoUserPoolData> signUp(String email, String password) async {
    try {
      final signUpResult = await userPool.signUp(
        email,
        password,
        userAttributes: [AttributeArg(name: 'email', value: email)],
        validationData: [
          AttributeArg(name: 'email', value: email),
        ],
      );
      return signUpResult;
    } on CognitoClientException catch (e) {
      _logError('SignUp error', e);
      rethrow;
    } catch (e) {
      _logError('Unexpected error during signup', e);
      rethrow;
    }
  }

  Future<bool> confirmRegistration(String email, String code) async {
    try {
      final user = CognitoUser(email, userPool);
      return await user.confirmRegistration(code);
    } on CognitoClientException catch (e) {
      _logError('Confirmation error', e);
      rethrow;
    } catch (e) {
      _logError('Unexpected error during confirmation', e);
      rethrow;
    }
  }

  Future<CognitoUser> signIn(String email, String password) async {
      try {
        final user = CognitoUser(email, userPool);
        final authDetails = AuthenticationDetails(
          username: email,
          password: password,
          validationData: {
            'email': email,
          },
        );

        _session = await user.authenticateUser(authDetails);
        _currentUser = user;
        return user;
      } on CognitoClientException catch (e) {
        _logError('SignIn error', e);
        rethrow;
      } catch (e) {
        _logError('Unexpected error during signin', e);
        rethrow;
      }
    }

  Future<void> signOut() async {
    try {
      if (_currentUser != null) {
        await _currentUser?.signOut();
        _currentUser = null;
        _session = null;
      }
    } catch (e) {
      _logError('SignOut error', e);
      rethrow;
    }
  }

  Future<bool> isAuthenticated() async {
    try {
      if (_currentUser == null || _session == null) return false;
      return _session!.isValid();
    } catch (e) {
      _logError('Authentication check error', e);
      return false;
    }
  }

  Future<void> resendConfirmationCode(String email) async {
    try {
      final user = CognitoUser(email, userPool);
      await user.resendConfirmationCode();
    } catch (e) {
      _logError('Resend confirmation code error', e);
      rethrow;
    }
  }

  void _logError(String message, dynamic error) {
    // TODO: Replace with proper logging framework
    // ignore: avoid_print
    print('$message: $error');
  }

  CognitoUser? get currentUser => _currentUser;
  CognitoUserSession? get session => _session;
}