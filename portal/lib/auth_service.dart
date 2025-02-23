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
    final secretKey = const String.fromEnvironment(
      'CLIENT_SECRET',
      defaultValue: bool.fromEnvironment('dart.vm.product') ? '' : 'dev-client-secret',
    );

    if (userPoolId.isEmpty || clientId.isEmpty || secretKey.isEmpty) {
      throw Exception('Missing required Cognito configuration');
    }

    userPool = CognitoUserPool(
      userPoolId,
      clientId,
      secretKey: secretKey,
    );
  }

  Future<CognitoUserPoolData> signUp(String email, String password) async {
    try {
      final secretHash = userPool.calculateAuthenticationHash(email);
      final signUpResult = await userPool.signUp(
        email,
        password,
        userAttributes: [AttributeArg(name: 'email', value: email)],
        secretHash: secretHash,
        validationData: [
          AttributeArg(name: 'email', value: email),
        ],
      );
      return signUpResult;
    } on CognitoClientException catch (e) {
      print('SignUp error: ${e.message}'); // Helpful for debugging
      rethrow;
    } catch (e) {
      print('Unexpected error during signup: $e'); // Helpful for debugging
      rethrow;
    }
  }

  Future<bool> confirmRegistration(String email, String code) async {
    try {
      final user = CognitoUser(email, userPool);
      final secretHash = userPool.calculateAuthenticationHash(email);
      return await user.confirmRegistration(
        code,
        secretHash: secretHash,
      );
    } on CognitoClientException catch (e) {
      print('Confirmation error: ${e.message}'); // Helpful for debugging
      rethrow;
    } catch (e) {
      print('Unexpected error during confirmation: $e'); // Helpful for debugging
      rethrow;
    }
  }

Future<CognitoUser> signIn(String email, String password) async {
    try {
      final user = CognitoUser(email, userPool, clientSecret: userPool.getClientSecret());
      final authDetails = AuthenticationDetails(
        username: email,
        password: password,
        authParameters: {
          'CHALLENGE_NAME': 'SRP_A',
        },
      );

      _session = await user.authenticateUser(authDetails);
      _currentUser = user;
      return user;
    } on CognitoClientException catch (e) {
      print('SignIn error: ${e.message}');
      rethrow;
    } catch (e) {
      print('Unexpected error during signin: $e');
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
      print('SignOut error: $e'); // Helpful for debugging
      rethrow;
    }
  }

  Future<bool> isAuthenticated() async {
    try {
      if (_currentUser == null || _session == null) return false;
      return _session!.isValid();
    } catch (e) {
      print('Authentication check error: $e'); // Helpful for debugging
      return false;
    }
  }

  Future<void> resendConfirmationCode(String email) async {
    try {
      final user = CognitoUser(email, userPool);
      final secretHash = userPool.calculateAuthenticationHash(email);
      await user.resendConfirmationCode(
        secretHash: secretHash,
      );
    } catch (e) {
      print('Resend confirmation code error: $e'); // Helpful for debugging
      rethrow;
    }
  }

  CognitoUser? get currentUser => _currentUser;
  CognitoUserSession? get session => _session;
}