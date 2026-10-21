import fs from 'node:fs';
import path from 'node:path';

// 도커에서는 WORKDIR=/app, 기존 compose의 볼륨(/app/json, /app/chzzk)을 그대로 쓴다.
export const ROOT = process.env.RECORDWEB_ROOT ?? process.cwd();
export const JSON_DIR = path.join(ROOT, 'json');
export const jsonPath = (name: string) => path.join(JSON_DIR, name);
export const absFromRoot = (p: string) => (path.isAbsolute(p) ? p : path.join(ROOT, p));

/** 실경로(심볼릭 링크 해석). 존재하지 않는 경로는 절대 경로로만 바꾼다. 표시와 파일 작업에 쓴다. */
export function realPath(p: string): string {
  try {
    return fs.realpathSync(p);
  } catch {
    return path.resolve(p);
  }
}

/** 비교용 정규화: 실경로 + OS 케이스 규칙. 화면에 보여 주거나 파일 작업에 넘기는 값으로 쓰지 않는다. */
export function normPath(p: string): string {
  const r = realPath(p);
  return process.platform === 'win32' ? r.toLowerCase() : r;
}
