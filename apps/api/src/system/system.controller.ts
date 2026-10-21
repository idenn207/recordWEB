import { Controller, Get } from '@nestjs/common';
import fs from 'node:fs';
import os from 'node:os';
import { StoreService } from '../config/store.service.js';
import { absFromRoot, normPath } from '../lib/paths.js';

let prev = os.cpus().map((c) => ({ ...c.times }));

/** 직전 호출 이후의 CPU 사용률(%). 호출 간격이 곧 측정 구간이다. */
function cpuPercent(): number {
  const cur = os.cpus().map((c) => ({ ...c.times }));
  let idle = 0;
  let total = 0;
  cur.forEach((t, i) => {
    const p = prev[i] ?? t;
    const sum = (x: typeof t) => x.user + x.nice + x.sys + x.idle + x.irq;
    idle += t.idle - p.idle;
    total += sum(t) - sum(p);
  });
  prev = cur;
  return total > 0 ? Math.round((1 - idle / total) * 100) : 0;
}

@Controller('api/system')
export class SystemController {
  constructor(private readonly store: StoreService) {}

  /** 녹화 폴더(와 이동 폴더)가 놓인 볼륨별 사용량. 파일 관리자 설정과 무관하게 대시보드에서 쓴다. */
  @Get('disks')
  disks() {
    const c = this.store.getConfig();
    const dirs = new Set(this.store.getChannels().map((ch) => normPath(absFromRoot(ch.output_dir))));
    if (c.moveAfterProcessingEnabled && c.moveAfterProcessing) dirs.add(normPath(absFromRoot(c.moveAfterProcessing)));
    const seen = new Set<string>();
    const out: { path: string; total: number; used: number; free: number; percent: number }[] = [];
    for (const d of dirs) {
      try {
        const s = fs.statfsSync(fs.existsSync(d) ? d : absFromRoot('.'));
        const total = s.bsize * s.blocks;
        const free = s.bsize * s.bavail;
        const key = `${total}:${s.bfree}`; // 같은 볼륨에 있는 폴더는 한 번만
        if (seen.has(key)) continue;
        seen.add(key);
        const used = total - s.bsize * s.bfree;
        out.push({ path: d, total, used, free, percent: total ? Math.trunc((used * 100) / total) : 0 });
      } catch {
        /* 접근 불가 볼륨은 건너뛴다 */
      }
    }
    return out;
  }

  @Get('metrics')
  metrics() {
    const total = os.totalmem();
    const free = os.freemem();
    return {
      cpu: { percent: cpuPercent(), model: os.cpus()[0]?.model ?? '', cores: os.cpus().length },
      memory: { total, used: total - free, percent: Math.round(((total - free) / total) * 100) },
      uptimeSec: Math.floor(os.uptime()),
      hostname: os.hostname(),
    };
  }
}
