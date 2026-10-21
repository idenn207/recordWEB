import { ForbiddenException, HttpException, Injectable, NotFoundException } from '@nestjs/common';
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';
import { StoreService } from '../config/store.service.js';
import { bin } from '../lib/bin.js';
import { absFromRoot, normPath, realPath } from '../lib/paths.js';
import { RecorderService } from '../recorder/recorder.service.js';
import { YtUploadService } from '../uploads/yt-upload.service.js';

const execFileP = promisify(execFile);

export interface FileItem {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: string;
  ext: string;
  locked?: boolean;
}

const HIDDEN = new Set(['system volume information', '$recycle.bin', 'recycler', 'pagefile.sys', 'hiberfil.sys', 'swapfile.sys', 'config.msi', 'msocache', 'recovery', 'desktop.ini', 'thumbs.db']);
const isHidden = (name: string) => name.startsWith('.') || HIDDEN.has(name.toLowerCase());

export function isDeniedPath(p: string): boolean {
  const rp = path.resolve(p);
  if (process.platform === 'win32') {
    const low = rp.toLowerCase();
    return ['c:\\windows', 'c:\\program files', 'c:\\program files (x86)', 'c:\\programdata', 'c:\\users\\public'].some((d) => low === d || low.startsWith(d + '\\'));
  }
  return ['/', '/bin', '/sbin', '/etc', '/proc', '/sys', '/dev', '/run', '/var', '/usr'].some((d) => rp === d || (d !== '/' && rp.startsWith(d + '/')));
}

const PSEUDO_FS = new Set(['proc', 'sysfs', 'tmpfs', 'devtmpfs', 'devpts', 'cgroup', 'cgroup2', 'mqueue', 'overlay', 'squashfs', 'autofs', 'fusectl', 'securityfs', 'debugfs']);

export function listMountRoots(): string[] {
  const roots = new Set<string>();
  if (process.platform === 'win32') {
    for (let c = 65; c <= 90; c++) {
      const d = `${String.fromCharCode(c)}:\\`;
      if (fs.existsSync(d)) roots.add(d);
    }
  } else {
    try {
      for (const line of fs.readFileSync('/proc/mounts', 'utf8').split('\n')) {
        const [src, mp, type] = line.split(' ');
        const mount = mp?.replace(/\\040/g, ' ');
        if (src?.startsWith('/') && mount && !PSEUDO_FS.has(type) && !isDeniedPath(mount) && fs.existsSync(mount)) roots.add(mount);
      }
    } catch {
      /* /proc 없음 */
    }
  }
  return [...roots].sort();
}

@Injectable()
export class FilesService {
  constructor(
    private readonly store: StoreService,
    private readonly recorder: RecorderService,
    private readonly uploads: YtUploadService,
  ) {}

  private cfg() {
    const c = this.store.getConfig();
    if (!c.fileManagerEnabled) throw new ForbiddenException('File manager disabled');
    return c;
  }

  private writable() {
    if (this.cfg().fileManagerReadOnly) throw new ForbiddenException('Read-only mode');
  }

  /** blacklist 모드는 ['*'] (시스템 경로만 거부), whitelist는 채널 출력 폴더 + 이동 폴더 + 설정한 루트. */
  allowedRoots(): string[] {
    const c = this.cfg();
    if (c.fileManagerMode === 'blacklist') return ['*'];
    const roots = new Set<string>();
    for (const ch of this.store.getChannels()) if (ch.output_dir) roots.add(normPath(absFromRoot(ch.output_dir)));
    if (c.moveAfterProcessingEnabled && c.moveAfterProcessing) roots.add(normPath(absFromRoot(c.moveAfterProcessing)));
    for (const r of c.fileManagerRoots) roots.add(normPath(r));
    return [...roots].sort();
  }

  ensureInRoots(p: string): string {
    const roots = this.allowedRoots();
    const real = realPath(p); // 호출자에게 돌려주는 값은 원래 대소문자를 유지한다
    if (roots[0] === '*') {
      if (isDeniedPath(real)) throw new ForbiddenException('Path is denied by system blacklist');
      return real;
    }
    const rp = normPath(p);
    if (roots.some((r) => rp === r || rp.startsWith(r + path.sep))) return real;
    throw new ForbiddenException('outside allowed roots');
  }

  private busy(): string[] {
    return [...this.recorder.busyPaths(), ...this.uploads.activePaths()].map(normPath);
  }

  /** 파일은 그 파일 자신이 녹화/업로드 중일 때만, 폴더는 그 안에 활성 파일이 있을 때 잠근다. */
  isLocked(p: string, busy = this.busy()): boolean {
    const rp = normPath(p);
    const isDir = fs.existsSync(rp) && fs.statSync(rp).isDirectory();
    return busy.some((b) => (isDir ? b === rp || b.startsWith(rp + path.sep) : b === rp));
  }

  private assertUnlocked(p: string, busy = this.busy()) {
    if (this.isLocked(p, busy)) throw new HttpException(`Locked: ${p}`, 423);
  }

  roots() {
    const roots = this.allowedRoots();
    const list = roots[0] === '*' ? listMountRoots() : roots;
    return { roots: list, default: list[0] ?? null };
  }

  ls(p: string, showHidden: boolean): { path: string; items: FileItem[] } {
    const rp = this.ensureInRoots(p);
    if (!fs.existsSync(rp) || !fs.statSync(rp).isDirectory()) throw new NotFoundException('path not found');
    const busy = this.busy();
    const items: FileItem[] = [];
    try {
      for (const e of fs.readdirSync(rp, { withFileTypes: true })) {
        if (!showHidden && isHidden(e.name)) continue;
        const full = path.join(rp, e.name);
        let st: fs.Stats;
        try {
          st = fs.lstatSync(full);
        } catch {
          continue;
        }
        const isDir = e.isDirectory();
        items.push({
          name: e.name,
          path: full,
          is_dir: isDir,
          size: isDir ? 0 : st.size,
          mtime: new Date(st.mtimeMs - new Date(st.mtimeMs).getTimezoneOffset() * 60000).toISOString().slice(0, 19).replace('T', ' '),
          ext: isDir ? '폴더' : path.extname(e.name).slice(1).toLowerCase() || '파일',
          locked: this.isLocked(full, busy),
        });
      }
    } catch {
      throw new ForbiddenException('permission denied');
    }
    items.sort((a, b) => Number(b.is_dir) - Number(a.is_dir) || a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
    return { path: rp, items };
  }

  diskUsage(paths?: string[]) {
    const list = paths?.length ? paths.filter((p) => fs.existsSync(p) && fs.statSync(p).isDirectory()) : this.roots().roots;
    const out: { path: string; label: string; total: number; used: number; free: number; percent: number }[] = [];
    for (const p of list) {
      try {
        const s = fs.statfsSync(p);
        const total = s.bsize * s.blocks;
        const free = s.bsize * s.bavail;
        const used = total - s.bsize * s.bfree;
        out.push({ path: p, label: p, total, used, free, percent: total ? Math.trunc((used * 100) / total) : 0 });
      } catch {
        /* 접근 불가 볼륨은 건너뛴다 */
      }
    }
    return out;
  }

  downloadPath(p: string): string {
    const rp = this.ensureInRoots(p);
    if (!fs.existsSync(rp) || !fs.statSync(rp).isFile()) throw new NotFoundException('File not found');
    return rp;
  }

  mkdir(parent: string, name: string) {
    this.writable();
    const created = path.join(this.ensureInRoots(parent), name);
    fs.mkdirSync(created, { recursive: true });
    return created;
  }

  rename(src: string, newName: string) {
    this.writable();
    const s = this.ensureInRoots(src);
    this.assertUnlocked(s);
    const dst = path.join(path.dirname(s), newName);
    fs.renameSync(s, dst);
    return dst;
  }

  move(srcs: string[], dstDir: string) {
    this.writable();
    const dst = this.ensureInRoots(dstDir);
    const busy = this.busy();
    const resolved = srcs.map((s) => this.ensureInRoots(s));
    resolved.forEach((s) => this.assertUnlocked(s, busy));
    fs.mkdirSync(dst, { recursive: true });
    return resolved.map((s) => {
      const to = path.join(dst, path.basename(s));
      try {
        fs.renameSync(s, to);
      } catch {
        fs.cpSync(s, to, { recursive: true }); // 다른 볼륨 간 이동
        fs.rmSync(s, { recursive: true });
      }
      return to;
    });
  }

  remove(paths: string[], hard: boolean) {
    this.writable();
    const c = this.cfg();
    const busy = this.busy();
    const resolved = paths.map((p) => this.ensureInRoots(p));
    resolved.forEach((p) => this.assertUnlocked(p, busy));
    return resolved.map((rp) => {
      if (hard || !c.trashEnabled) {
        fs.rmSync(rp, { recursive: true });
        return rp;
      }
      const trash = path.join(path.dirname(rp), '.trash');
      fs.mkdirSync(trash, { recursive: true });
      const d = new Date();
      const p2 = (n: number) => String(n).padStart(2, '0');
      const to = path.join(trash, `${path.basename(rp)}.${d.getFullYear()}${p2(d.getMonth() + 1)}${p2(d.getDate())}_${p2(d.getHours())}${p2(d.getMinutes())}${p2(d.getSeconds())}`);
      fs.renameSync(rp, to);
      return to;
    });
  }

  async streamCopy(paths: string[]) {
    this.writable();
    const busy = this.busy();
    const results: { src: string; dst?: string; ok: boolean; error?: string }[] = [];
    for (const s of paths) {
      try {
        const rp = this.ensureInRoots(s);
        if (!fs.existsSync(rp) || !fs.statSync(rp).isFile()) throw new NotFoundException(`Not a file: ${rp}`);
        this.assertUnlocked(rp, busy);
        const dst = path.join(path.dirname(rp), `fixed_${path.basename(rp)}`);
        await execFileP(bin('ffmpeg'), ['-hide_banner', '-loglevel', 'error', '-y', '-i', rp, '-c', 'copy', '-map', '0', dst]);
        results.push({ src: rp, dst, ok: true });
      } catch (e) {
        results.push({ src: s, ok: false, error: e instanceof HttpException ? String(e.message) : (e as Error).message });
      }
    }
    return results;
  }
}
