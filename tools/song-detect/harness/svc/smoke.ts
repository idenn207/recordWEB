// songd 가 떠 있을 때: node smoke.ts  (Node 24 는 타입 제거 실행). 클라이언트 경유 지연과 모드 전환을 확인한다.
import assert from 'node:assert/strict';
import { SongdClient } from './songd.client.ts';

const c = new SongdClient();
const m = await c.run<{ N_expose: number; L_loss: number; n: number }>('replay', { registry: false });
assert.equal(m.n, 191);
assert.equal(m.N_expose, 14); // 등록부 없이 N 노출 14/55 (HANDOFF 28절 기준선)
assert.equal(m.L_loss, 0);
const lat: number[] = [];
for (let i = 0; i < 30; i++) {
  const t = performance.now();
  await c.run('replay', { registry: false });
  lat.push(performance.now() - t);
}
lat.sort((a, b) => a - b);
const t = performance.now();
const r = await c.setMode('unlimited');
const h = await c.health();
console.log(JSON.stringify({ replay: m, p50_ms: +lat[15].toFixed(1), p95_ms: +lat[28].toFixed(1), mode: r, switch_ms: +(performance.now() - t).toFixed(1), health: h }));
await c.setMode('cap80');
console.log('smoke ok');
