import fs from 'node:fs';
import path from 'node:path';

// 기존 Python 앱의 readJsonSafe/writeJsonSafe와 같은 규칙: 손상되면 .bak에서 복구, 같은 내용이면 쓰지 않고, tmp→rename으로 원자적 저장.
export function readJson<T>(file: string, fallback: T): T {
  const parse = (f: string) => JSON.parse(fs.readFileSync(f, 'utf8'));
  try {
    if (!fs.existsSync(file)) return fallback;
    return parse(file);
  } catch {
    try {
      const v = parse(file + '.bak');
      writeJson(file, v);
      return v;
    } catch {
      return fallback;
    }
  }
}

export function writeJson(file: string, data: unknown): boolean {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const text = JSON.stringify(data, null, 4);
  if (fs.existsSync(file)) {
    try {
      if (fs.readFileSync(file, 'utf8') === text) return false;
    } catch {
      /* 읽기 실패는 덮어쓴다 */
    }
    fs.copyFileSync(file, file + '.bak');
  }
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, text, 'utf8');
  fs.renameSync(tmp, file);
  return true;
}
