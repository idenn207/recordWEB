import { ChildProcess, spawn, SpawnOptions } from 'node:child_process';

const posix = process.platform !== 'win32';

/** POSIX에서는 새 프로세스 그룹으로 띄워 자식(ffmpeg 등)까지 한 번에 신호를 보낸다. */
export function spawnGroup(cmd: string, args: string[], opts: SpawnOptions = {}): ChildProcess {
  const p = spawn(cmd, args, { ...opts, detached: posix, windowsHide: true });
  // 실행 실패(ENOENT 등)가 처리되지 않은 'error' 이벤트로 서버 전체를 죽이지 않게 한다. 'close'는 그래도 발생해 exited()가 풀린다.
  p.on('error', (e) => console.error(`[spawn] ${cmd} 실행 실패: ${e.message}`));
  return p;
}

export function signalGroup(p: ChildProcess, sig: NodeJS.Signals) {
  if (!p.pid || p.exitCode !== null) return;
  try {
    if (posix) process.kill(-p.pid, sig);
    else p.kill(sig);
  } catch {
    /* 이미 종료됨 */
  }
}

export const exited = (p: ChildProcess) =>
  p.exitCode !== null || p.signalCode !== null ? Promise.resolve(p.exitCode) : new Promise<number | null>((r) => p.once('close', r));

/** 신호를 보내고 graceMs 안에 안 끝나면 SIGKILL. */
export async function terminate(p: ChildProcess, sig: NodeJS.Signals = 'SIGTERM', graceMs = 5000) {
  if (p.exitCode !== null || p.signalCode !== null) return;
  signalGroup(p, sig);
  const t = setTimeout(() => signalGroup(p, 'SIGKILL'), graceMs);
  await exited(p);
  clearTimeout(t);
}

/** 청크 경계와 상관없이 줄 단위로 받는다. */
export function onLines(stream: NodeJS.ReadableStream | null | undefined, cb: (line: string) => void) {
  let buf = '';
  stream?.on('data', (d: Buffer) => {
    buf += d.toString('utf8');
    const parts = buf.split(/\r?\n|\r/);
    buf = parts.pop() ?? '';
    parts.forEach(cb);
  });
}
