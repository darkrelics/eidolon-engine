import 'package:amazon_cognito_identity_dart_2/cognito.dart';

class AuthService {
  late final CognitoUserPool userPool;
  CognitoUser? _currentUser;
  CognitoUserSession? _session;

  AuthService() {
    _initializeCognito();
  }

  void _initializeCognito() {
    // Get values from environment or use defaults for development
    final userPoolId = const String.fromEnvironment(
      'USER_POOL_ID',
      defaultValue:
          bool.fromEnvironment('dart.vm.product') ? '' : 'dev-user-pool-id',
    );
    final clientId = const String.fromEnvironment(
      'CLIENT_ID',
      defaultValue:
          bool.fromEnvironment('dart.vm.product') ? '' : 'dev-client-id',
    );
    final clientSecret = const String.fromEnvironment(
      'CLIENT_SECRET',
      defaultValue:
          bool.fromEnvironment('dart.vm.product') ? '' : 'dev-client-secret',
    );

    if (userPoolId.isEmpty || clientId.isEmpty || clientSecret.isEmpty) {
      throw Exception('Missing required Cognito configuration');
    }

    userPool = CognitoUserPool(
      userPoolId,
      clientId,
      clientSecret: clientSecret,
    );
  }

  Future<CognitoUserPoolData> signUp(String email, String password) async {
    try {
      final signUpResult = await userPool.signUp(
        email,
        password,
        userAttributes: [AttributeArg(name: 'email', value: email)],
      );
      return signUpResult;
    } on CognitoClientException {
      rethrow;
    }
  }

  Future<bool> confirmRegistration(String email, String code) async {
    try {
      final user = CognitoUser(email, userPool);
      return await user.confirmRegistration(code);
    } on CognitoClientException {
      rethrow;
    }
  }

  Future<CognitoUser> signIn(String email, String password) async {
    try {
      final user = CognitoUser(email, userPool);
      final authDetails = AuthenticationDetails(
        username: email,
        password: password,
      );

      _session = await user.authenticateUser(authDetails);
      _currentUser = user;
      return user;
    } on CognitoClientException {
      rethrow;
    }
  }

  Future<void> signOut() async {
    if (_currentUser != null) {
      await _currentUser?.signOut();
      _currentUser = null;
      _session = null;
    }
  }

  Future<bool> isAuthenticated() async {
    if (_currentUser == null || _session == null) return false;
    return _session!.isValid();
  }

  CognitoUser? get currentUser => _currentUser;
  CognitoUserSession? get session => _session;
}