import 'package:eidolon_incremental/providers/character_provider.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:flutter/foundation.dart';

class CharacterScreenController extends ChangeNotifier {
  final ApiService _apiService;
  final CharacterProvider _characterProvider;

  List<CharacterInfo>? _characters;
  bool _isLoading = true;
  String? _error;

  List<CharacterInfo>? get characters => _characters;
  bool get isLoading => _isLoading;
  String? get error => _error;

  CharacterScreenController({required ApiService apiService, required CharacterProvider characterProvider})
    : _apiService = apiService,
      _characterProvider = characterProvider {
    loadCharacters();
  }

  Future<void> loadCharacters() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final characters = await _apiService.listCharacters();
      _characters = characters;
    } catch (e) {
      _error = _getUserFriendlyErrorMessage(e);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<List<ArchetypeInfo>> getArchetypes() async {
    try {
      return await _apiService.getArchetypes();
    } catch (e) {
      debugPrint('Error loading archetypes: $e');
      return [];
    }
  }

  Future<void> createCharacter(
    String name,
    String archetype, {
    required Function(String) onSuccess,
    required Function(String) onError,
  }) async {
    _isLoading = true;
    notifyListeners();

    try {
      final result = await _apiService.addCharacter(name: name, archetype: archetype);

      final createdName = result['CharacterName'] ?? name;
      final createdArchetype = result['Archetype'] ?? archetype;

      String message = 'Created character: $createdName';
      if (createdArchetype != 'default' && createdArchetype.isNotEmpty) {
        message += ' ($createdArchetype)';
      }

      await loadCharacters();
      onSuccess(message);
    } catch (e) {
      _isLoading = false; // loadCharacters handles this usually, but if we fail before...
      notifyListeners();
      onError(_getUserFriendlyErrorMessage(e, context: 'createCharacter'));
    }
  }

  Future<void> deleteCharacter(
    CharacterInfo character, {
    required Function(String) onSuccess,
    required Function(String) onError,
  }) async {
    _isLoading = true;
    notifyListeners();

    try {
      final deleteResult = await _apiService.deleteCharacter(character.id);

      final deletedName = deleteResult['CharacterName'] ?? character.name;
      final itemsDeleted = deleteResult['ItemsDeleted'] ?? 0;
      final segmentsDeleted = deleteResult['ActiveSegmentsDeleted'] ?? 0;

      String message = 'Deleted character: $deletedName';
      if (itemsDeleted > 0 || segmentsDeleted > 0) {
        message += ' ($itemsDeleted items, $segmentsDeleted segments)';
      }

      await loadCharacters();
      onSuccess(message);
    } catch (e) {
      _isLoading = false;
      notifyListeners();
      onError(_getUserFriendlyErrorMessage(e, context: 'deleteCharacter'));
    }
  }

  Future<void> enterGame(CharacterInfo character, {required VoidCallback onSuccess, required Function(String) onError}) async {
    // Note: Loading state is handled by the UI dialog for this specific action
    // because we want to show a specific "Entering Game" dialog, not the generic screen loader.

    try {
      final fullCharacter = await _apiService.getCharacterById(character.id);

      if (fullCharacter != null) {
        await _characterProvider.updateCharacter(fullCharacter);
        onSuccess();
      } else {
        // Fallback if full load fails but we have basic info?
        // Actually getCharacterById returns null on failure usually or throws.
        // If it returns null, we probably shouldn't proceed.
        onError('Failed to load character data');
      }
    } catch (e) {
      onError(_getUserFriendlyErrorMessage(e, context: 'loading character'));
    }
  }

  String _getUserFriendlyErrorMessage(dynamic e, {String? context}) {
    final errorString = e.toString();
    if (errorString.contains('Internal server error')) {
      return 'Server error occurred. Please try again later.';
    } else if (errorString.contains('Network')) {
      return 'Connection error. Please check your internet connection.';
    } else if (errorString.contains('Player account not found')) {
      return 'We could not find your player data. Please sign out and back in.';
    } else if (errorString.contains('Character name is already taken')) {
      return 'That character name is already taken. Please choose another.';
    } else if (errorString.contains('Character limit reached')) {
      return 'You have reached the maximum number of characters.';
    } else if (errorString.contains('Character name is not available')) {
      return 'That character name is not available. Please choose another.';
    } else if (errorString.contains('Character not found')) {
      return 'Character not found';
    } else if (errorString.contains('Access denied')) {
      return 'You do not have permission to delete this character';
    }

    // Fallback to generic handler if available or simple string
    return 'An error occurred: $errorString';
  }
}
