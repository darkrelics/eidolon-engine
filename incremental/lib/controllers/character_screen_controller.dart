import 'package:eidolon_incremental/providers/character_provider.dart';
import 'package:eidolon_incremental/services/api_service.dart';
import 'package:eidolon_incremental/utils/error_handler.dart';
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

  CharacterScreenController({
    required ApiService apiService,
    required CharacterProvider characterProvider,
  }) : _apiService = apiService,
       _characterProvider = characterProvider;

  bool _loadInProgress = false;

  Future<void> loadCharacters() async {
    // Prevent duplicate concurrent loads
    if (_loadInProgress) {
      return;
    }
    _loadInProgress = true;
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final characters = await _apiService.listCharacters();
      _characters = characters;
    } catch (e) {
      _error = ErrorHandler.getUserFriendlyMessage(
        e,
        context: 'loading characters',
      );
    } finally {
      _loadInProgress = false;
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<List<ArchetypeInfo>> getArchetypes() async {
    try {
      return await _apiService.getArchetypes();
    } catch (e) {
      debugPrint('Error loading archetypes: $e');
      rethrow;
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
      final result = await _apiService.addCharacter(
        name: name,
        archetype: archetype,
      );

      final createdName = result['CharacterName'] ?? name;
      final createdArchetype = result['Archetype'] ?? archetype;

      String message = 'Created character: $createdName';
      if (createdArchetype != 'default' && createdArchetype.isNotEmpty) {
        message += ' ($createdArchetype)';
      }

      await loadCharacters();
      onSuccess(message);
    } catch (e) {
      _isLoading = false;
      notifyListeners();
      onError(
        ErrorHandler.getUserFriendlyMessage(e, context: 'creating character'),
      );
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
      onError(
        ErrorHandler.getUserFriendlyMessage(e, context: 'deleting character'),
      );
    }
  }

  Future<void> enterGame(
    CharacterInfo character, {
    required VoidCallback onSuccess,
    required Function(String) onError,
  }) async {
    try {
      final fullCharacter = await _apiService.getCharacterById(character.id);

      if (fullCharacter != null) {
        await _characterProvider.updateCharacter(fullCharacter);
        onSuccess();
      } else {
        onError('Failed to load character data');
      }
    } catch (e) {
      onError(
        ErrorHandler.getUserFriendlyMessage(e, context: 'loading character'),
      );
    }
  }
}
