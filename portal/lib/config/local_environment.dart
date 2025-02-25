import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'environment_config.dart';

class DevEnvironment implements EnvironmentConfig {
  DevEnvironment() {
    dotenv.load();
  }
  
  @override
  String get userPoolId => dotenv.env['USER_POOL_ID'] ?? '';
  
  @override
  String get clientId => dotenv.env['CLIENT_ID'] ?? '';
  
  @override
  String get clientSecret => dotenv.env['CLIENT_SECRET'] ?? '';
}