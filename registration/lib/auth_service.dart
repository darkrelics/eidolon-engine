import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:amazon_cognito_identity_dart_2/cognito.dart';

class AuthService {
  late final CognitoUserPool userPool;
  CognitoUser? _currentUser;

  AuthService() {
    _initializeCognito();
  }

  void _initializeCognito() {
    final userPoolId = const String.fromEnvironment('USER_POOL_ID');
    final clientId = const String.fromEnvironment('CLIENT_ID');
    final clientSecret = const String.fromEnvironment('CLIENT_SECRET');

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
  final signUpResult = await userPool.signUp(
    email,
    password,
    userAttributes: [
      AttributeArg(name: 'email', value: email),
    ],
  );
  return signUpResult;
}

  Future<bool> confirmRegistration(String email, String code) async {
    final user = CognitoUser(email, userPool);
    await user.confirmRegistration(code);
    return true;
  }

Future<CognitoUser> signIn(String email, String password) async {
  final user = CognitoUser(email, userPool);
  final authDetails = AuthenticationDetails(
    username: email,
    password: password,
    validationData: {
      'SecretHash': _computeSecretHash(email),
    },
  );

  await user.authenticateUser(authDetails);
  _currentUser = user;
  return user;
}

String _computeSecretHash(String username) {
  final key = utf8.encode(const String.fromEnvironment('CLIENT_SECRET'));
  final message = utf8.encode(username + const String.fromEnvironment('CLIENT_ID'));
  final hmac = Hmac(sha256, key);
  final digest = hmac.convert(message);
  return base64.encode(digest.bytes);
}

  CognitoUser? get currentUser => _currentUser;
}