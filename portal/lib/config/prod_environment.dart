import 'environment_config.dart';

class ProdEnvironment implements EnvironmentConfig {
  @override
  String get userPoolId => const String.fromEnvironment('USER_POOL_ID');
  
  @override
  String get clientId => const String.fromEnvironment('CLIENT_ID');
  
  @override
  String get clientSecret => const String.fromEnvironment('CLIENT_SECRET');
}