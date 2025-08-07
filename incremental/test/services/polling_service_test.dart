import 'package:flutter_test/flutter_test.dart';
import 'package:eidolon_incremental/services/polling_service.dart';

void main() {
  group('PollingService Tests', () {
    late PollingService pollingService;

    setUp(() {
      pollingService = PollingService();
    });

    tearDown(() {
      pollingService.dispose();
    });

    test('startPolling creates periodic stream', () async {
      final events = <void>[];
      final stream = pollingService.startPolling(
        'test_key',
        interval: const Duration(milliseconds: 100),
        immediate: true,
      );

      final subscription = stream.listen((event) {
        events.add(event);
      });

      // Wait for multiple events
      await Future.delayed(const Duration(milliseconds: 350));
      subscription.cancel();

      // Should have immediate event + 3 periodic events
      expect(events.length, greaterThanOrEqualTo(3));
    });

    test('startPolling with immediate false delays first event', () async {
      final events = <void>[];
      final stream = pollingService.startPolling(
        'test_key',
        interval: const Duration(milliseconds: 100),
        immediate: false,
      );

      final subscription = stream.listen((event) {
        events.add(event);
      });

      // Check immediately - should have no events
      expect(events.length, equals(0));

      // Wait for first event
      await Future.delayed(const Duration(milliseconds: 150));
      subscription.cancel();

      // Should have 1 event after interval
      expect(events.length, equals(1));
    });

    test('stopPolling cancels active timer', () async {
      final events = <void>[];
      final stream = pollingService.startPolling(
        'test_key',
        interval: const Duration(milliseconds: 100),
      );

      final subscription = stream.listen((event) {
        events.add(event);
      });

      await Future.delayed(const Duration(milliseconds: 150));
      pollingService.stopPolling('test_key');
      
      final eventCount = events.length;
      await Future.delayed(const Duration(milliseconds: 200));
      
      subscription.cancel();

      // Event count should not increase after stopping
      expect(events.length, equals(eventCount));
    });

    test('isPollingActive returns correct status', () {
      expect(pollingService.isPollingActive('test_key'), isFalse);

      pollingService.startPolling('test_key');
      expect(pollingService.isPollingActive('test_key'), isTrue);

      pollingService.stopPolling('test_key');
      expect(pollingService.isPollingActive('test_key'), isFalse);
    });

    test('handlePollingError retries up to max attempts', () async {
      int retryCount = 0;
      
      // Create a more realistic test without blocking delays
      final shouldRetry1 = pollingService.handlePollingError(
        'test_key',
        () => retryCount++,
      );
      final shouldRetry2 = pollingService.handlePollingError(
        'test_key',
        () => retryCount++,
      );
      final shouldRetry3 = pollingService.handlePollingError(
        'test_key',
        () => retryCount++,
      );
      final shouldRetry4 = pollingService.handlePollingError(
        'test_key',
        () => retryCount++,
      );
      
      // Check results after all are complete
      expect(await shouldRetry1, isTrue);
      expect(await shouldRetry2, isTrue);
      expect(await shouldRetry3, isTrue);
      expect(await shouldRetry4, isFalse);
      
      // Retries only happen when shouldRetry returns true
      expect(retryCount, equals(3));
    });

    test('resetRetryCounter resets retry attempts', () async {
      // Use up retries (do them concurrently to avoid timeout)
      final futures = <Future<bool>>[];
      for (int i = 0; i < 3; i++) {
        futures.add(pollingService.handlePollingError('test_key2', () {}));
      }
      await Future.wait(futures);
      
      // Should not retry (max reached)
      var shouldRetry = await pollingService.handlePollingError('test_key2', () {});
      expect(shouldRetry, isFalse);
      
      // Reset counter
      pollingService.resetRetryCounter('test_key2');
      
      // Should retry again
      shouldRetry = await pollingService.handlePollingError('test_key2', () {});
      expect(shouldRetry, isTrue);
    });

    test('mechanical polling uses correct interval', () async {
      final events = <void>[];
      final stream = pollingService.startMechanicalPolling('char_123');
      
      final subscription = stream.listen((event) {
        events.add(event);
      });
      
      // Should have immediate event
      await Future.delayed(const Duration(milliseconds: 500));
      expect(events.length, greaterThanOrEqualTo(1));
      
      subscription.cancel();
      pollingService.stopPolling('mechanical_char_123');
    });

    test('story polling uses correct interval', () async {
      final events = <void>[];
      final stream = pollingService.startStoryPolling('char_123');
      
      final subscription = stream.listen((event) {
        events.add(event);
      });
      
      // Should NOT have immediate event
      await Future.delayed(const Duration(milliseconds: 100));
      expect(events.length, equals(0));
      
      subscription.cancel();
      pollingService.stopPolling('story_char_123');
    });

    test('stopAllPolling cancels all active timers', () async {
      // Start multiple polling operations
      pollingService.startPolling('key1');
      pollingService.startPolling('key2');
      pollingService.startPolling('key3');
      
      expect(pollingService.isPollingActive('key1'), isTrue);
      expect(pollingService.isPollingActive('key2'), isTrue);
      expect(pollingService.isPollingActive('key3'), isTrue);
      
      pollingService.stopAllPolling();
      
      expect(pollingService.isPollingActive('key1'), isFalse);
      expect(pollingService.isPollingActive('key2'), isFalse);
      expect(pollingService.isPollingActive('key3'), isFalse);
    });
  });

  group('PollingManager Singleton Tests', () {
    test('PollingManager returns same instance', () {
      final manager1 = PollingManager();
      final manager2 = PollingManager();
      
      expect(identical(manager1, manager2), isTrue);
    });

    test('PollingManager delegates to service correctly', () async {
      final manager = PollingManager();
      
      final stream = manager.startMechanicalPolling('test_char');
      expect(stream, isNotNull);
      
      expect(manager.isActive('mechanical_test_char'), isTrue);
      
      manager.stopPolling('mechanical_test_char');
      expect(manager.isActive('mechanical_test_char'), isFalse);
      
      manager.dispose();
    });
  });
}