// Integration simulation test for pywebview telemetry subscriptions with EventDeduplicator
import assert from 'node:assert';
import { test, describe } from 'node:test';

// Mock DOM Window environment
class MockEventTarget {
  constructor() {
    this.listeners = new Map();
  }
  addEventListener(event, handler) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(handler);
  }
  removeEventListener(event, handler) {
    if (!this.listeners.has(event)) return;
    this.listeners.set(event, this.listeners.get(event).filter(h => h !== handler));
  }
  dispatchEvent(event) {
    const list = this.listeners.get(event.type) || [];
    for (const h of list) {
      h(event);
    }
  }
}

class MockCustomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.detail = init.detail;
  }
}

// Set up mock global window
const mockWindow = new MockEventTarget();
global.window = mockWindow;
global.CustomEvent = MockCustomEvent;

// Replicate EventDeduplicator and subscribe methods from frontend/src/api/pywebview.ts
class EventDeduplicator {
  constructor(windowMs = 80) {
    this.recentKeys = new Map();
    this.windowMs = windowMs;
  }
  isDuplicate(key) {
    const now = typeof performance !== 'undefined' && typeof performance.now === 'function'
      ? performance.now()
      : Date.now();
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
}

function subscribeToJobProgress(callback) {
  const dedup = new EventDeduplicator(80);
  const emit = (jobId, pct, phase) => {
    if (dedup.isDuplicate(`progress:${jobId}:${pct}:${phase}`)) return;
    callback(jobId, pct, phase);
  };
  const handler = (e) => {
    const detail = e.detail;
    if (detail) {
      emit(detail.jobId, detail.progress, detail.phase);
    }
  };
  window.addEventListener('pywebview:job-progress', handler);
  const oldFn = window.onJobProgress;
  window.onJobProgress = (jobId, pct, phase) => {
    emit(jobId, pct, phase);
    if (oldFn) oldFn(jobId, pct, phase);
  };
  return () => {
    window.removeEventListener('pywebview:job-progress', handler);
    window.onJobProgress = oldFn;
  };
}

function subscribeToJobLog(callback) {
  const dedup = new EventDeduplicator(80);
  const emit = (jobId, logLine) => {
    if (dedup.isDuplicate(`log:${jobId}:${logLine}`)) return;
    callback(jobId, logLine);
  };
  const handler = (e) => {
    const detail = e.detail;
    if (detail) {
      emit(detail.jobId, detail.logLine);
    }
  };
  window.addEventListener('pywebview:job-log', handler);
  const oldFn = window.onJobLog;
  window.onJobLog = (jobId, line) => {
    emit(jobId, line);
    if (oldFn) oldFn(jobId, line);
  };
  return () => {
    window.removeEventListener('pywebview:job-log', handler);
    window.onJobLog = oldFn;
  };
}

describe('PyWebView Telemetry Subscription Integration', () => {

  test('Dual emission from worker_manager produces exactly one log callback', () => {
    const logsReceived = [];
    const unsubscribe = subscribeToJobLog((jobId, line) => {
      logsReceived.push({ jobId, line });
    });

    // Simulate worker_manager._push_log:
    // 1. window.onJobLog(...)
    // 2. window.dispatchEvent(new CustomEvent('pywebview:job-log', { detail: ... }))
    const jobId = 'job-1';
    const line = 'Processing frame 50/100';

    // Step 1: Python worker triggers window.onJobLog
    window.onJobLog(jobId, line);
    // Step 2: In the same frame, Python worker dispatches CustomEvent
    window.dispatchEvent(new CustomEvent('pywebview:job-log', {
      detail: { jobId, logLine: line }
    }));

    assert.strictEqual(logsReceived.length, 1, 'Subscriber received duplicate log callback!');
    assert.strictEqual(logsReceived[0].jobId, 'job-1');
    assert.strictEqual(logsReceived[0].line, 'Processing frame 50/100');

    // Next unique frame log
    window.onJobLog(jobId, 'Processing frame 51/100');
    window.dispatchEvent(new CustomEvent('pywebview:job-log', {
      detail: { jobId, logLine: 'Processing frame 51/100' }
    }));

    assert.strictEqual(logsReceived.length, 2, 'Next frame log was incorrectly dropped');
    assert.strictEqual(logsReceived[1].line, 'Processing frame 51/100');

    unsubscribe();
  });

  test('Dual emission from worker_manager produces exactly one progress callback', () => {
    const progressReceived = [];
    const unsubscribe = subscribeToJobProgress((jobId, pct, phase) => {
      progressReceived.push({ jobId, pct, phase });
    });

    const jobId = 'job-progress-test';
    // Emitting both simultaneously
    window.onJobProgress(jobId, 45, 'YOLO');
    window.dispatchEvent(new CustomEvent('pywebview:job-progress', {
      detail: { jobId, progress: 45, phase: 'YOLO' }
    }));

    assert.strictEqual(progressReceived.length, 1, 'Subscriber received duplicate progress callback!');
    assert.strictEqual(progressReceived[0].pct, 45);
    assert.strictEqual(progressReceived[0].phase, 'YOLO');

    // Emitting next progress
    window.onJobProgress(jobId, 50, 'RTMLIB');
    window.dispatchEvent(new CustomEvent('pywebview:job-progress', {
      detail: { jobId, progress: 50, phase: 'RTMLIB' }
    }));

    assert.strictEqual(progressReceived.length, 2);
    assert.strictEqual(progressReceived[1].pct, 50);

    unsubscribe();
  });

  test('Unsubscribe cleanly detaches all listeners and restores previous callbacks', () => {
    let callCount = 0;
    const unsubscribe = subscribeToJobLog(() => {
      callCount++;
    });

    window.onJobLog('job-1', 'test line 1');
    assert.strictEqual(callCount, 1);

    // Unsubscribe
    unsubscribe();

    // Now events must not reach our callback
    if (typeof window.onJobLog === 'function') {
      window.onJobLog('job-1', 'test line 2');
    }
    window.dispatchEvent(new CustomEvent('pywebview:job-log', {
      detail: { jobId: 'job-1', logLine: 'test line 2' }
    }));

    assert.strictEqual(callCount, 1, 'Callback was called after unsubscribe!');
  });

});
