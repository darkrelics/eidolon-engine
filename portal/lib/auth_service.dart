import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:amazon_cognito_identity_dart_2/cognito.dart';

import 'config/environment.dart';

class AuthService {
  late final CognitoUserPool userPool;
  CognitoUser? _currentUser;
  CognitoUserSession? _session;

  AuthService() {
    _initializeCognito();
  }

  void _initializeCognito() {
    final config = Environment.instance;
    
    final userPoolId = config.userPoolId;
    final clientId = config.clientId;
    final clientSecret = config.clientSecret;

    _logError('Cognito Configuration Status', {
      'poolIdPresent': userPoolId.isNotEmpty,
      'clientIdPresent': clientId.isNotEmpty,
      'secretPresent': clientSecret.isNotEmpty,
    });

    if (userPoolId.isEmpty || clientId.isEmpty || clientSecret.isEmpty) {
      throw Exception('Missing required Cognito configuration');
    }

    _clientId = clientId;
    _clientSecret = clientSecret;

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
        authParameters: [
          AttributeArg(name: 'SECRET_HASH', value: _computeSecretHash(email)),
        ],
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

  String _computeSecretHash(String username) {
    final key = utf8.encode(const String.fromEnvironment('CLIENT_SECRET'));
    final message = utf8.encode(
      username +
          const String.fromEnvironment('CLIENT_ID') +
          const String.fromEnvironment('CLIENT_SECRET'),
    );
    final hmac = Hmac(sha256, key);
    final digest = hmac.convert(message);
    return base64.encode(digest.bytes);
  }

  CognitoUser? get currentUser => _currentUser;
  CognitoUserSession? get session => _session;
}
