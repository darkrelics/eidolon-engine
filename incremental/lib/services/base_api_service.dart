import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'auth_service.dart';

/// Base API service with common HTTP functionality
abstract class BaseApiService {
  final AuthService _authService;
  final http.Client _httpClient;
  final String baseUrl;

  BaseApiService({
    required AuthService authService,
    required this.baseUrl,
    http.Client? httpClient,
  }) : _authService = authService,
       _httpClient = httpClient ?? http.Client();

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

  /// Generic HTTP request handler
  Future<T> executeRequest<T>({
    required String method,
    required String endpoint,
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    T Function(Map<String, dynamic>)? parser,
    bool returnRawResponse = false,
  }) async {
    try {
      // Build URI with query parameters
      var uri = Uri.parse('$baseUrl$endpoint');
      if (queryParams != null && queryParams.isNotEmpty) {
        uri = uri.replace(queryParameters: queryParams);
      }

      debugPrint('API [$method]: $uri');

      // Get headers
      final headers = await getHeaders();

      // Make request
      http.Response response;
      switch (method.toUpperCase()) {
        case 'GET':
          response = await _httpClient.get(uri, headers: headers);
          break;
        case 'POST':
          response = await _httpClient.post(
            uri,
            headers: headers,
            body: body != null ? jsonEncode(body) : null,
          );
          break;
        case 'PUT':
          response = await _httpClient.put(
            uri,
            headers: headers,
            body: body != null ? jsonEncode(body) : null,
          );
          break;
        case 'DELETE':
          response = await _httpClient.delete(uri, headers: headers);
          break;
        case 'PATCH':
          response = await _httpClient.patch(
            uri,
            headers: headers,
            body: body != null ? jsonEncode(body) : null,
          );
          break;
        default:
          throw Exception('Unsupported HTTP method: $method');
      }

      debugPrint('API Response [${response.statusCode}]: ${response.body}');

      // Handle response
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
        // Parse error message
        String errorMessage = 'Request failed with status ${response.statusCode}';
        try {
          final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
          errorMessage = errorBody['Error'] ?? 
                        errorBody['error'] ?? 
                        errorBody['message'] ?? 
                        errorMessage;
        } catch (_) {
          // Use default error message if parsing fails
        }
        throw ApiException(errorMessage, statusCode: response.statusCode);
      }
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