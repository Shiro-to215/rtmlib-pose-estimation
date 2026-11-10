// Adversarial Empirical Stress Test Suite for EventDeduplicator
// Focus: Dual event suppression, sliding window boundary, rapid bursts, and key collisions.

import assert from 'node:assert';
import { test, describe } from 'node:test';

class EventDeduplicator {
  constructor(windowMs = 80) {
    this.recentKeys = new Map();
    this.windowMs = windowMs;
  }

  isDuplicate(key) {
    const now = typeof performance !== 'undefined' && typeof performance.now === 'function'
      ? performance.now()
      : Date.now();

    // Prune expired entries
    for (const [k, t] of this.recentKeys.entries()) {
      if (now - t > this.windowMs) {
        this.recentKeys.delete(k);
      }
    }

    if (this.recentKeys.has(key)) {
      return true;
    }
    this.recentKeys.set(key, now);
    return false;
  }

  size() {
    return this.recentKeys.size;
  }
}

describe('Adversarial EventDeduplicator Stress Suite', () => {

  test('TC-DEDUP-1: Dual and triple event delivery in identical microtask (< 1ms)', () => {
    const dedup = new EventDeduplicator(80);
    const callbackInvocations = [];

    const handleEvent = (sig) => {
      if (dedup.isDuplicate(sig)) return;
      callbackInvocations.push(sig);
    };

    const signature = 'progress:job-123:45:YOLO';

    handleEvent(signature); // Call 1 (e.g. window.onJobProgress)
    handleEvent(signature); // Call 2 (e.g. CustomEvent 'pywebview:job-progress')
    handleEvent(signature); // Call 3 (e.g. window.__onBackendEvent)

    assert.strictEqual(callbackInvocations.length, 1, 'Only exactly 1 invocation must pass');
    assert.strictEqual(callbackInvocations[0], signature);
  });

  test('TC-DEDUP-2: Distinct events within burst window must never be suppressed', () => {
    const dedup = new EventDeduplicator(80);
    const processed = [];

    // Fire 200 distinct log lines in rapid succession (< 1ms)
    for (let i = 0; i < 200; i++) {
      const sig = `log:job-abc:Frame ${i} processed bounding box [x=${i}, y=${i*2}]`;
      if (!dedup.isDuplicate(sig)) {
        processed.push(sig);
      }
    }

    assert.strictEqual(processed.length, 200, 'All 200 unique events must be delivered without loss');
    assert.strictEqual(dedup.size(), 200, 'Map holds 200 active entries');
  });

  test('TC-DEDUP-3: Boundary timing test: < 80ms suppressed, > 80ms preserved', async () => {
    const dedup = new EventDeduplicator(80);
    const events = [];

    const push = (val) => {
      if (!dedup.isDuplicate(`progress:job-1:${val}:RTMLIB`)) {
        events.push({ val, t: performance.now() });
      }
    };

    // First arrival
    const t0 = performance.now();
    push(50);
    assert.strictEqual(events.length, 1);

    // Duplicate arrival at ~25ms (< 80ms)
    await new Promise(r => setTimeout(r, 25));
    const t1 = performance.now();
    if (t1 - t0 < 80) {
      push(50);
      assert.strictEqual(events.length, 1, `Duplicate at ${t1 - t0}ms must be suppressed`);
    }

    // Wait until strictly > 80ms (e.g. total 130ms)
    while (performance.now() - t0 < 95) {
      await new Promise(r => setTimeout(r, 10));
    }
    push(50);
    assert.strictEqual(events.length, 2, `Legitimate event at ${performance.now() - t0}ms must be allowed`);
  });

  test('TC-DEDUP-4: High volume memory pruning and cleanup (500 events)', async () => {
    const dedup = new EventDeduplicator(50);

    // Inject 500 distinct items rapidly (< 2ms)
    for (let i = 0; i < 500; i++) {
      dedup.isDuplicate(`bulk-key-${i}`);
    }
    assert.strictEqual(dedup.size(), 500, 'Initial size should be 500');

    // Wait 70ms (> 50ms windowMs)
    await new Promise(r => setTimeout(r, 70));

    // Next event should trigger cleanup loop
    dedup.isDuplicate('fresh-key');

    // All 500 expired entries must be pruned, leaving only 'fresh-key'
    assert.strictEqual(dedup.size(), 1, `Expected size 1 after pruning, got ${dedup.size()}`);
  });

  test('TC-DEDUP-5: Complex unicode, emojis, and punctuation in signatures', () => {
    const dedup = new EventDeduplicator(80);
    const testKeys = [
      'log:job-1:解析完了: 出力先=C:\\テスト フォルダ\\output.mp4',
      'log:job-1:🏃‍♂️ YOLO検出率: 98.5% [閾値=0.50]',
      'log:job-2:{"nested": "json", "symbols": "<>&\'\\"\\n\\t"}',
      'queue:null:false:0:',
      'progress:uuid-1234-5678:100:RTMLIB',
    ];

    for (const key of testKeys) {
      assert.strictEqual(dedup.isDuplicate(key), false, `First call for '${key}' must pass`);
      assert.strictEqual(dedup.isDuplicate(key), true, `Second call for '${key}' must be duplicate`);
    }
  });

  test('TC-DEDUP-6: Starvation resistance: continuous duplicate delivery within window does not postpone expiration', async () => {
    const dedup = new EventDeduplicator(80);
    const key = 'heartbeat:job-1';

    const t0 = performance.now();
    // First registration
    assert.strictEqual(dedup.isDuplicate(key), false);

    // Fire duplicates while elapsed < 70ms
    while (performance.now() - t0 < 65) {
      await new Promise(r => setTimeout(r, 10));
      if (performance.now() - t0 < 75) {
        assert.strictEqual(dedup.isDuplicate(key), true, 'Intermediate call before 75ms must be duplicate');
      }
    }

    // Now wait until past 85ms from t0
    while (performance.now() - t0 < 95) {
      await new Promise(r => setTimeout(r, 10));
    }

    // Since t > 95ms > 80ms from t0, key should expire and be accepted again
    assert.strictEqual(dedup.isDuplicate(key), false, 'Must expire 80ms after initial registration');
  });

});
