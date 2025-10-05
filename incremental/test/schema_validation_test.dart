import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

// Lightweight JSON Schema validator for a subset needed by our models.
// This is intentionally minimal to avoid extra dev_deps. It supports
// type checks, required, properties, items, enum, minimum/maximum.
class MiniJsonSchema {
  final Map<String, dynamic> schema;
  MiniJsonSchema(this.schema);

  void validate(dynamic data, {String path = r'$'}) {
    final type = schema['type'];
    if (type != null) {
      _checkType(type, data, path);
    }

    // Handle object properties
    if (schema['type'] == 'object') {
      final props = (schema['properties'] ?? {}) as Map<String, dynamic>;
      final required =
          (schema['required'] ?? const <dynamic>[]) as List<dynamic>;
      if (data is! Map) {
        throw TestFailure('$path: expected object');
      }
      for (final field in required) {
        if (!data.containsKey(field)) {
          throw TestFailure('$path: missing required field "$field"');
        }
      }
      data.forEach((key, value) {
        final ps = props[key];
        if (ps is Map<String, dynamic>) {
          MiniJsonSchema(ps).validate(value, path: '$path.$key');
        }
      });
    }

    // Handle arrays
    if (schema['type'] == 'array') {
      if (data is! List) {
        throw TestFailure('$path: expected array');
      }
      final items = schema['items'];
      if (items is Map<String, dynamic>) {
        for (var i = 0; i < data.length; i++) {
          MiniJsonSchema(items).validate(data[i], path: '$path[$i]');
        }
      }
    }

    // Numeric bounds
    if (data is num) {
      final min = schema['minimum'];
      final max = schema['maximum'];
      if (min is num && data < min) {
        throw TestFailure('$path: value $data < minimum $min');
      }
      if (max is num && data > max) {
        throw TestFailure('$path: value $data > maximum $max');
      }
    }

    // Enums
    final enums = schema['enum'];
    if (enums is List && !enums.contains(data)) {
      throw TestFailure('$path: value $data not in enum $enums');
    }
  }

  void _checkType(dynamic type, dynamic data, String path) {
    bool ok;
    switch (type) {
      case 'object':
        ok = data is Map;
        break;
      case 'array':
        ok = data is List;
        break;
      case 'string':
        ok = data is String;
        break;
      case 'integer':
        ok = data is int;
        break;
      case 'number':
        ok = data is num;
        break;
      case 'boolean':
        ok = data is bool;
        break;
      default:
        ok = true; // types like null/any are ignored
    }
    if (!ok) {
      throw TestFailure('$path: expected $type, got ${data.runtimeType}');
    }
  }
}

Map<String, dynamic> readSchema(String name) {
  final file = File('schemas/$name.schema.json');
  final text = file.readAsStringSync();
  return jsonDecode(text) as Map<String, dynamic>;
}

void main() {
  test('ActiveSegment schema validates a minimal successful outcome', () {
    final schema = readSchema('active-segment');

    final example = {
      'ActiveSegmentID': '550e8400-e29b-41d4-a716-446655440000',
      'CharacterID': '550e8400-e29b-41d4-a716-446655440001',
      'PlayerID': '550e8400-e29b-41d4-a716-446655440002',
      'StoryID': 'story-001',
      'SegmentID': 'seg-001',
      'StartTime': '2025-08-09T12:00:00Z',
      'EndTime': '2025-08-09T12:01:30Z',
      'Status': 'Completed',
      'Outcome': 'Success',
    };

    // Tolerate extra fields optionally; schema will enforce required basics
    MiniJsonSchema(schema).validate(example);
  });

  test('ClientEvent schema validates Narrative event', () {
    final schema = readSchema('client-event');

    final example = {
      'EventType': 'Narrative',
      'Title': 'A Twist',
      'Description': 'Something happens...',
      'Data': {'Outcome': 'Success'},
    };

    MiniJsonSchema(schema).validate(example);
  });
}
