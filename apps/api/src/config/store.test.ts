import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { expect, it, vi } from 'vitest';

it('다른 프로세스가 쓴 config.json/channels.json을 mtime으로 따라간다 (웹 역할)', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'rw-'));
  fs.mkdirSync(path.join(root, 'json'));
  vi.stubEnv('RECORDWEB_ROOT', root);
  vi.stubEnv('ROLE', 'app');
  vi.resetModules();
  const { StoreService } = await import('./store.service.js');
  const store = new StoreService();
  expect(store.getChannels()).toHaveLength(0);

  const bump = (f: string, data: unknown) => {
    const p = path.join(root, 'json', f);
    fs.writeFileSync(p, JSON.stringify(data));
    fs.utimesSync(p, new Date(), new Date(Date.now() + 5000)); // 같은 ms에 쓰여도 바뀐 것으로 보이게
  };
  bump('config.json', { autoRecordingMode: true });
  bump('channels.json', [{ platform: 'chzzk', id: 'a1', name: 'n', output_dir: 'chzzk' }]);
  expect(store.getConfig().autoRecordingMode).toBe(true);
  expect(store.getChannels().map((c) => c.id)).toEqual(['a1']);
  vi.unstubAllEnvs();
});
