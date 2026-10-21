import { describe, expect, it } from 'vitest';
import { formatBytes, formatElapsed } from './format';

describe('formatBytes', () => {
  it('단위를 올리고 자릿수를 맞춘다', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(150 * 1024 ** 2)).toBe('150 MB');
    expect(formatBytes(2.5 * 1024 ** 4)).toBe('2.5 TB');
  });

  it('잘못된 값은 0 B', () => {
    expect(formatBytes(NaN)).toBe('0 B');
    expect(formatBytes(-1)).toBe('0 B');
  });
});

describe('formatElapsed', () => {
  it('HH:MM:SS', () => {
    expect(formatElapsed(3661)).toBe('01:01:01');
    expect(formatElapsed(59.9)).toBe('00:00:59');
    expect(formatElapsed(-3)).toBe('00:00:00');
  });
});
