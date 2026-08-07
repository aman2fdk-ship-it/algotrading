import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

/**
 * jsdom does not implement crypto.randomUUID (used by TradeJournalWidget).
 * Node's global crypto may or may not be shadowed by the jsdom environment,
 * so patch it only when missing.
 */
const g = globalThis as unknown as { crypto?: Crypto & { randomUUID?: () => string } };
if (!g.crypto?.randomUUID) {
  const fallbackRandomUUID = (): string =>
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  if (!g.crypto) {
    (g as Record<string, unknown>).crypto = { randomUUID: fallbackRandomUUID } as Crypto;
  } else {
    Object.defineProperty(g.crypto, 'randomUUID', { value: fallbackRandomUUID, configurable: true });
  }
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});
