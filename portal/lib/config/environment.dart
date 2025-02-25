import 'environment_config.dart';

// Import dotenv conditionally based on environment
import 'local_environment.dart'
    if (dart.library.io) 'local_environment.dart'
    if (dart.library.html) 'prod_environment.dart';

class Environment {
  static EnvironmentConfig init() {
    // Check if we're in development mode
    bool isDevelopment = const bool.fromEnvironment('dart.vm.product') == false;
    
    if (isDevelopment) {
      return DevEnvironment();
    } else {
      return ProdEnvironment();
    }
  }
  
  static late final EnvironmentConfig instance = init();
}