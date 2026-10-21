import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { readJson, writeJson } from './json-store.js';
import { exited, spawnGroup } from './proc.js';
import { fmtDuration, formatPattern, jitteredWaitMs, safeTitle, uniqueFilename } from './text.js';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'rw-'));

describe('text', () => {
  it('formatPattern은 알려진 키만 치환한다', () => {
    expect(formatPattern('[{start_time}] {x} {name}', { start_time: '2026-10-22', name: 'a' })).toBe('[2026-10-22] {x} a');
  });

  it('safeTitle은 금칙문자를 바꾸고 55자로 자른다', () => {
    expect(safeTitle('a/b:c*d\n')).toBe('a_b_c_d');
    expect(safeTitle('ㅋ'.repeat(100))).toHaveLength(55);
  });

  it('uniqueFilename은 번호를 붙인다', () => {
    const d = tmp();
    fs.writeFileSync(path.join(d, 'a.ts'), '');
    fs.writeFileSync(path.join(d, 'a (1).ts'), '');
    expect(uniqueFilename(d, 'a.ts')).toBe('a (2).ts');
    expect(uniqueFilename(d, 'b.ts')).toBe('b.ts');
  });

  it('fmtDuration', () => {
    expect(fmtDuration(3661)).toBe('01:01:01');
    expect(fmtDuration(-5)).toBe('00:00:00');
  });

  it('jitteredWaitMs는 채널마다 결정적이고 주기 안에 든다', () => {
    const a = jitteredWaitMs('chA', 60, 1_000_000, 0);
    expect(jitteredWaitMs('chA', 60, 1_000_000, 0)).toBe(a);
    for (const id of ['chA', 'chB', 'chC']) {
      const w = jitteredWaitMs(id, 60, 1_000_000, 0);
      expect(w).toBeGreaterThanOrEqual(1000);
      expect(w).toBeLessThanOrEqual(60_000);
    }
  });
});

describe('json-store', () => {
  it('같은 내용이면 쓰지 않고, 손상되면 .bak에서 복구한다', () => {
    const f = path.join(tmp(), 'x.json');
    expect(writeJson(f, { a: 1 })).toBe(true);
    expect(writeJson(f, { a: 1 })).toBe(false);
    expect(writeJson(f, { a: 2 })).toBe(true); // 이전 값이 .bak로 남는다
    fs.writeFileSync(f, '{broken');
    expect(readJson(f, null)).toEqual({ a: 1 });
    expect(readJson(path.join(tmp(), 'none.json'), 'fallback')).toBe('fallback');
  });
});

describe('proc', () => {
  it('존재하지 않는 바이너리를 실행해도 프로세스가 죽지 않고 exited가 풀린다', async () => {
    const p = spawnGroup('definitely-not-a-real-binary-xyz', []);
    await expect(exited(p)).resolves.toBeDefined();
  });
});
