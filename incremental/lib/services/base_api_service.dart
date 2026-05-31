import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'auth_service.dart';
import 'package:eidolon_incremental/utils/api_validation.dart';

/// Base API service with common HTTP functionality
abstract class BaseApiService {
  final AuthService _authService;
  final http.Client _httpClient;
  final String baseUrl;

  /// Maximum request body size in bytes (5MB)
  static const int maxRequestBodySize = 5 * 1024 * 1024;

  /// Maximum query parameter value length
  static const int maxQueryParamLength = 2048;

  /// Maximum number of query parameters
  static const int maxQueryParams = 50;

  BaseApiService({
    required AuthService authService,
    required this.baseUrl,
    http.Client? httpClient,
  }) : _authService = authService,
       _httpClient = httpClient ?? http.Client() {
    _validateBaseUrl(baseUrl);
  }

  /// Validate base URL format
  void _validateBaseUrl(String url) {
    if (url.isEmpty) {
      throw ArgumentError('Base URL cannot be empty');
    }

    final uri = Uri.tryParse(url);
    if (uri == null || !uri.hasScheme || !uri.hasAuthority) {
      throw ArgumentError('Invalid base URL format: $url');
    }

    if (uri.scheme != 'https' && uri.scheme != 'http') {
      throw ArgumentError('Base URL must use http or https: $url');
    }
  }

  /// Get authorization headers
  Future<Map<String, String>> getHeaders() async {
    final token = await _authService.getIdToken();
    if (token == null) {
      throw Exception('Not authenticated');
    }
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  /// Validate endpoint path
  void _validateEndpoint(String endpoint) {
    if (endpoint.isEmpty) {
      throw ArgumentError('Endpoint cannot be empty');
    }

    if (!endpoint.startsWith('/')) {
      throw ArgumentError('Endpoint must start with /: $endpoint');
    }

    // Check for invalid characters that could cause injection attacks
    if (endpoint.contains('..') || endpoint.contains('//')) {
      throw ArgumentError('Endpoint contains invalid path traversal: $endpoint');
    }

    // Ensure endpoint doesn't contain query parameters (use queryParams instead)
    if (endpoint.contains('?')) {
      throw ArgumentError('Endpoint should not contain query parameters. Use queryParams parameter instead: $endpoint');
    }
  }

  /// Validate query parameters
  void _validateQueryParams(Map<String, String>? queryParams) {
    if (queryParams == null || queryParams.isEmpty) {
      return;
    }

    if (queryParams.length > maxQueryParams) {
      throw ArgumentError('Too many query parameters (${queryParams.length}). Maximum: $maxQueryParams');
    }

    for (final entry in queryParams.entries) {
      final key = entry.key;
      final value = entry.value;

      if (key.isEmpty) {
        throw ArgumentError('Query parameter key cannot be empty');
      }

      if (value.length > maxQueryParamLength) {
        throw ArgumentError('Query parameter "$key" value too long (${value.length} chars). Maximum: $maxQueryParamLength');
      }

      // Check for null bytes or control characters that could cause issues
      if (value.contains('\u0000') || value.contains('\n') || value.contains('\r')) {
        throw ArgumentError('Query parameter "$key" contains invalid characters');
      }
    }
  }

  /// Validate and encode request body
  String? _validateAndEncodeBody(Map<String, dynamic>? body) {
    if (body == null || body.isEmpty) {
      return null;
    }

    try {
      final encoded = jsonEncode(body);
      final bodySize = encoded.length;

      if (bodySize > maxRequestBodySize) {
        throw ArgumentError(
          'Request body too large ($bodySize bytes). Maximum: $maxRequestBodySize bytes (${(maxRequestBodySize / 1024 / 1024).toStringAsFixed(1)}MB)',
        );
      }

      return encoded;
    } catch (e) {
      if (e is ArgumentError) {
        rethrow;
      }
      throw ArgumentError('Failed to encode request body: $e');
    }
  }

  /// Validate HTTP method
  void _validateMethod(String method) {
    const allowedMethods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];
    final upperMethod = method.toUpperCase();

    if (!allowedMethods.contains(upperMethod)) {
      throw ArgumentError('Unsupported HTTP method: $method. Allowed: ${allowedMethods.join(", ")}');
    }
  }

  /// Generic HTTP request handler.
  ///
  /// On a 401 response, this transparently attempts a single token refresh +
  /// retry so that mid-session expiry does not bubble up as a raw
  /// UnauthorizedException to every caller. Only one retry is attempted;
  /// persistent 401s are propagated so the auth layer can redirect to login.
  Future<T> executeRequest<T>({
    required String method,
    required String endpoint,
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
    bool returnRawResponse = false,
  }) async {
    _validateMethod(method);
    _validateEndpoint(endpoint);
    _validateQueryParams(queryParams);

    try {
      return await _sendOnce<T>(
        method: method,
        endpoint: endpoint,
        body: body,
        queryParams: queryParams,
        parser: parser,
        returnRawResponse: returnRawResponse,
      );
    } on UnauthorizedException {
      final refreshed = await _authService.forceRefreshSession();
      if (!refreshed) {
        rethrow;
      }
      return _sendOnce<T>(
        method: method,
        endpoint: endpoint,
        body: body,
        queryParams: queryParams,
        parser: parser,
        returnRawResponse: returnRawResponse,
      );
    }
  }

  Future<T> _sendOnce<T>({
    required String method,
    required String endpoint,
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
    bool returnRawResponse = false,
  }) async {
    try {
      final uri = Uri.parse('$baseUrl$endpoint').replace(
        queryParameters: queryParams != null && queryParams.isNotEmpty ? queryParams : null,
      );

      debugPrint('API [$method]: $uri');

      final encodedBody = _validateAndEncodeBody(body);
      final headers = await getHeaders();

      http.Response response;
      switch (method.toUpperCase()) {
        case 'GET':
          response = await _httpClient.get(uri, headers: headers);
          break;
        case 'POST':
          response = await _httpClient.post(uri, headers: headers, body: encodedBody);
          break;
        case 'PUT':
          response = await _httpClient.put(uri, headers: headers, body: encodedBody);
          break;
        case 'DELETE':
          response = await _httpClient.delete(uri, headers: headers);
          break;
        case 'PATCH':
          response = await _httpClient.patch(uri, headers: headers, body: encodedBody);
          break;
        default:
          throw ArgumentError('Unsupported HTTP method: $method');
      }

      debugPrint('API Response [${response.statusCode}]: ${response.body}');

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (returnRawResponse) {
          return response.body as T;
        }

        if (response.body.isEmpty) {
          return {} as T;
        }

        final json = jsonDecode(response.body) as Map<String, dynamic>;

        if (parser != null) {
          return parser(json);
        }

        return json as T;
      } else if (response.statusCode == 404) {
        throw NotFoundException('Resource not found');
      } else if (response.statusCode == 401) {
        throw UnauthorizedException('Unauthorized');
      } else {
        String errorMessage = 'Request failed with status ${response.statusCode}';
        try {
          final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
          errorMessage =
              errorBody['Error'] ??
              errorBody['error'] ??
              errorBody['message'] ??
              errorMessage;
        } catch (_) {
          // Use default error message if parsing fails
        }
        throw ApiException(errorMessage, statusCode: response.statusCode);
      }
    } on ArgumentError catch (e) {
      debugPrint('API Validation Error: $e');
      throw ValidationException(e.message);
    } catch (e) {
      if (e is ApiException) {
        rethrow;
      }
      debugPrint('API Error: $e');
      throw ApiException('Network error: $e');
    }
  }

  /// GET request helper
  Future<T> get<T>(
    String endpoint, {
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
  }) {
    return executeRequest<T>(
      method: 'GET',
      endpoint: endpoint,
      queryParams: queryParams,
      parser: parser,
    );
  }

  /// POST request helper
  Future<T> post<T>(
    String endpoint, {
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
  }) {
    return executeRequest<T>(
      method: 'POST',
      endpoint: endpoint,
      body: body,
      queryParams: queryParams,
      parser: parser,
    );
  }

  /// PUT request helper
  Future<T> put<T>(
    String endpoint, {
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
  }) {
    return executeRequest<T>(
      method: 'PUT',
      endpoint: endpoint,
      body: body,
      queryParams: queryParams,
      parser: parser,
    );
  }

  /// DELETE request helper
  Future<T> delete<T>(
    String endpoint, {
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
  }) {
    return executeRequest<T>(
      method: 'DELETE',
      endpoint: endpoint,
      queryParams: queryParams,
      parser: parser,
    );
  }

  /// PATCH request helper
  Future<T> patch<T>(
    String endpoint, {
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
  }) {
    return executeRequest<T>(
      method: 'PATCH',
      endpoint: endpoint,
      body: body,
      queryParams: queryParams,
      parser: parser,
    );
  }

  // NOTE: The http.Client is NOT disposed here intentionally.
  // If the client was provided externally (dependency injection), the caller is responsible for disposal.
  // If we created the client internally, it will be garbage collected when this service is released.
  // This follows the principle of "who creates it, disposes it" for resource management.
}

/// Custom exception classes
class ApiException implements Exception {
  final String message;
  final int? statusCode;

  ApiException(this.message, {this.statusCode});

  @override
  String toString() => message;
}

class NotFoundException extends ApiException {
  NotFoundException(super.message) : super(statusCode: 404);
}

class UnauthorizedException extends ApiException {
  UnauthorizedException(super.message) : super(statusCode: 401);
}
