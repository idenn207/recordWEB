// UX 상호작용 검수. 실행 중인 웹(기본 http://localhost:5174)을 실제로 조작해 숫자로 판정한다.
//   pnpm --filter web ux            (UX_BASE, UX_USER, UX_PASS, UX_BROWSER 로 바꿀 수 있다)
// 판정 기준은 "눌러 둔 자리가 움직이지 않는다"이다. CLS 는 입력 직후 이동을 제외하므로 쓰지 않고 좌표를 직접 비교한다.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright-core';

const BASE = process.env.UX_BASE ?? 'http://localhost:5174';
const USER = process.env.UX_USER ?? 'owner';
const PASS = process.env.UX_PASS ?? 'longenough1';
const VIEWPORTS = [
  [390, 844],
  [820, 1000],
  [1440, 900],
];
const THEMES = ['light', 'dark'];
const ROUTES = ['/', '/channels', '/files', '/uploads', '/settings', '/profile'];

function findChromium() {
  if (process.env.UX_BROWSER) return process.env.UX_BROWSER;
  const root = path.join(process.env.LOCALAPPDATA ?? path.join(os.homedir(), '.cache'), 'ms-playwright');
  if (!fs.existsSync(root)) return undefined;
  for (const d of fs.readdirSync(root).filter((n) => /^chromium-\d+$/.test(n)).sort().reverse()) {
    for (const sub of ['chrome-win64/chrome.exe', 'chrome-win/chrome.exe', 'chrome-linux/chrome', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium']) {
      const p = path.join(root, d, sub);
      if (fs.existsSync(p)) return p;
    }
  }
}

const fails = [];
const check = (name, ok, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
  if (!ok) fails.push(name);
};

// 헤드리스는 기본으로 스크롤바를 숨기고 오버레이로 그려 폭 변화가 보이지 않는다. 실제 사용자처럼 폭을 차지하는 스크롤바로 검사한다.
const browser = await chromium.launch({ executablePath: findChromium(), ignoreDefaultArgs: ['--hide-scrollbars'], args: ['--disable-features=OverlayScrollbar'] });
const ctx = await browser.newContext();
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).slice(0, 120)));

async function login() {
  await page.goto(BASE + '/');
  if (await page.getByLabel('아이디').count()) {
    await page.getByLabel('아이디').fill(USER);
    await page.getByLabel('비밀번호').fill(PASS);
    await page.getByRole('button', { name: /로그인|계정 만들고 시작/ }).click();
    await page.waitForTimeout(1200);
  }
  // 로그인에 실패했는데 로그인 화면만 검사하고 통과하는 일이 없게, 로그인 확인 실패는 바로 중단한다.
  if (await page.getByLabel('아이디').count()) {
    console.log('FAIL  로그인하지 못했습니다. UX_USER, UX_PASS 를 확인하세요.');
    await browser.close();
    process.exit(2);
  }
}
async function open(route, w, h, theme) {
  await page.setViewportSize({ width: w, height: h });
  await page.goto(BASE + route);
  await page.evaluate((t) => { localStorage.setItem('rw-theme', t); document.documentElement.dataset.theme = t; }, theme);
  await page.waitForFunction(() => !document.querySelector('[role="status"][aria-label="불러오는 중"]'), null, { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(500);
}
const rects = (sel) => page.locator(sel).evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)].join(','); }));

await login();

// 1-0. 파일 도구 줄: 선택 상자의 글자와 화살표가 겹치지 않고, 컨트롤끼리 교차하지 않으며, 경로 입력칸을 열고 닫아도 주변이 움직이지 않는다.
for (const theme of THEMES) {
  for (const [w, h] of VIEWPORTS) {
    await open('/files', w, h, theme);
    const tag = `files ${w}px ${theme}`;
    // (a) 가장 긴 루트 이름을 넣어도 글자 오른쪽 끝과 화살표 왼쪽 끝 사이가 8px 이상
    const gap = await page.evaluate(() => {
      const t = document.querySelector('[aria-label="루트 선택"]');
      const txt = t?.querySelector('[data-pill-text]');
      const svg = t?.querySelector('svg');
      if (!txt || !svg) return null;
      const measure = () => Math.round((svg.getBoundingClientRect().left - txt.getBoundingClientRect().right) * 10) / 10;
      const normal = measure();
      const keep = txt.textContent;
      txt.textContent = '/app/xspaces/아주아주/긴/폴더/이름이/들어간/루트/경로/예시/입니다';
      const long = measure();
      txt.textContent = keep;
      return { normal, long };
    });
    check(`${tag} 루트 선택: 글자와 화살표 간격 8px 이상(긴 이름 포함)`, !!gap && gap.normal >= 8 && gap.long >= 8, JSON.stringify(gap));
    // (b) 도구 줄 컨트롤 쌍의 직사각형이 교차하지 않는다
    const hit = await page.evaluate(() => {
      const els = [...document.querySelectorAll('[data-file-toolbar] [data-ctl]')];
      const rs = els.map((e) => e.getBoundingClientRect());
      const bad = [];
      for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
        const a = rs[i], b = rs[j];
        if (a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5) bad.push(`${i}x${j}`);
      }
      return { n: els.length, bad };
    });
    check(`${tag} 도구 줄 컨트롤이 서로 겹치지 않는다`, hit.n >= 5 && !hit.bad.length, `${hit.n}개 ${hit.bad.join(',')}`);
    // (c) 경로 입력칸을 열고 닫아도 주변 요소 좌표 불변
    const around = '[data-file-toolbar] [data-ctl], thead th';
    const before = await rects(around);
    await page.getByRole('button', { name: '경로 직접 입력' }).click();
    await page.waitForTimeout(150);
    const opened = (await page.getByRole('textbox', { name: '경로' }).count()) === 1;
    const during = await rects(around);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(150);
    const closed = (await page.getByRole('textbox', { name: '경로' }).count()) === 0;
    const after = await rects(around);
    check(`${tag} 경로 입력칸 열기와 닫기: 주변 좌표 불변`, opened && closed && JSON.stringify(before) === JSON.stringify(during) && JSON.stringify(before) === JSON.stringify(after), opened ? '' : '입력칸이 열리지 않음');
  }
}

// 1. 파일 표: 선택해도 아무것도 움직이지 않고, 같은 자리를 다시 누르면 같은 체크박스가 꺼진다.
for (const [w, h] of VIEWPORTS) {
  await open('/files', w, h, 'dark');
  const sel = 'tbody tr input[type=checkbox]';
  const n = await page.locator(sel).count();
  if (!n) { check(`files ${w}px 행이 있다`, false); continue; }
  for (const idx of [0, n - 1]) {
    const box = page.locator(sel).nth(idx);
    await box.scrollIntoViewIfNeeded();
    const before = await rects(sel);
    const pos = await box.evaluate((e) => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
    await page.mouse.click(pos.x, pos.y);
    await page.waitForTimeout(250);
    const after = await rects(sel);
    // 나타나야 할 작업 영역이 실제로 눈에 보이는가(다른 요소에 가려지지 않는가). 좌표 불변만으로는 숨은 UI를 못 잡는다.
    const visible = await page.evaluate(() => { const r = document.querySelector('[aria-label="선택한 항목 작업"]'); if (!r) return false; const bs = [r, ...r.querySelectorAll('button')]; return bs.every((n) => { const b = n.getBoundingClientRect(); const v = b.left >= 0 && b.right <= innerWidth && b.top >= 0 && b.bottom <= innerHeight; return v && [0.15, 0.5, 0.85].every((fx) => { const el = document.elementFromPoint(b.x + b.width * fx, b.y + b.height / 2); return !!el && n.contains(el); }); }); });
    check(`files ${w}px 행${idx === 0 ? '(첫)' : '(끝)'} 선택 시 작업 영역이 보인다`, visible);
    check(`files ${w}px 행${idx === 0 ? '(첫)' : '(끝)'} 선택 후 체크박스 좌표 불변`, JSON.stringify(before) === JSON.stringify(after));
    await page.mouse.click(pos.x, pos.y); // 같은 자리 재클릭
    await page.waitForTimeout(250);
    const states = await page.locator(sel).evaluateAll((els) => els.map((e) => e.checked));
    check(`files ${w}px 행${idx === 0 ? '(첫)' : '(끝)'} 같은 자리 재클릭 시 해제`, states.every((c) => !c), `checked=${states.filter(Boolean).length}`);
  }
}

// 1-1. 녹화 화면: 갤러리는 모든 카드가 같은 크기, 리스트는 모든 행이 같은 높이. 보기를 바꿔도 보기 방식은 유지된다.
for (const [w, h] of VIEWPORTS) {
  await open('/', w, h, 'dark');
  const size = (sel) => page.locator(sel).evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)].join('x'); }));
  await page.getByRole('radio', { name: '갤러리로 보기' }).click();
  await page.waitForTimeout(200);
  const cards = await size('main ul.grid > li > article');
  check(`녹화 ${w}px 갤러리 카드가 있다`, cards.length > 0);
  const spread = (a) => (a.length ? Math.max(...a) - Math.min(...a) : 0); // 소수점 반올림 1px 은 눈에 보이지 않는다
  check(`녹화 ${w}px 갤러리 카드 크기 동일(상태, 이미지 유무와 무관)`, spread(cards.map((c) => +c.split('x')[1])) <= 1 && spread(cards.map((c) => +c.split('x')[0])) <= 1, [...new Set(cards)].join(' / '));
  await page.getByRole('radio', { name: '리스트로 보기' }).click();
  await page.waitForTimeout(200);
  const rows = await size('main ul > li[class*="border-b"]');
  check(`녹화 ${w}px 리스트 행이 있다`, rows.length > 0);
  check(`녹화 ${w}px 리스트 행 크기 동일`, spread(rows.map((c) => +c.split('x')[1])) <= 1, [...new Set(rows)].join(' / '));
  await page.getByPlaceholder('채널 검색').fill('토아');
  await page.waitForTimeout(200);
  check(`녹화 ${w}px 검색하면 일치하는 채널만 남는다`, (await page.locator('main ul > li[class*="border-b"]').count()) === 1);
  await page.getByPlaceholder('채널 검색').fill('');
  await page.reload();
  await page.waitForTimeout(600);
  check(`녹화 ${w}px 보기 방식이 새로고침 뒤에도 유지된다`, (await page.getByRole('radio', { name: '리스트로 보기' }).getAttribute('aria-checked')) === 'true');
}

// 1-1b. 플랫폼 토글: 치지직과 스페이스의 채널이 섞이지 않고, 바꿔도 탭 위치가 움직이지 않으며, URL 로 기억된다.
for (const [w, h] of VIEWPORTS) {
  await open('/', w, h, 'dark');
  await page.getByRole('radio', { name: /^치지직/ }).click();
  await page.waitForTimeout(250);
  const marks = () => page.evaluate(() => ({ chzzk: document.querySelectorAll('main img[src*="chzzk_icon"]').length, x: document.querySelectorAll('main span[title="X 스페이스"]').length }));
  const pos = () => page.evaluate(() => { const e = document.querySelector('[role=tablist]'); const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y)].join(','); });
  const before = await pos();
  await page.getByRole('radio', { name: /^스페이스/ }).click();
  await page.waitForTimeout(300);
  const m = await marks();
  check(`녹화 ${w}px 스페이스 토글: 치지직 채널이 섞이지 않는다`, m.x > 0 && m.chzzk === 0, JSON.stringify(m));
  check(`녹화 ${w}px 플랫폼 토글: 탭 위치 불변`, (await pos()) === before);
  check(`녹화 ${w}px 플랫폼 선택이 URL 에 저장된다`, page.url().includes('platform=x'));
}

// 1-2. 탭을 바꿔 내용 길이가 달라져 스크롤바가 생기거나 사라져도 화면이 가로로 움직이지 않는다.
for (const [w, h] of VIEWPORTS) {
  await open('/', w, 560, 'dark');
  const probe = () => page.evaluate(() => { const e = document.querySelector('[role=tablist]'); const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.width)].join(','); });
  const tabs = page.getByRole('tab');
  const before = await probe();
  const seen = new Set([before]);
  for (const name of [/^녹화 중/, /^오류/, /^꺼짐/, /^전체/]) {
    await tabs.filter({ hasText: name }).first().click();
    await page.waitForTimeout(250);
    seen.add(await probe());
  }
  check(`녹화 ${w}px 탭을 바꿔도 가로 위치와 폭 불변(스크롤바 유무와 무관)`, seen.size === 1, [...seen].join(' / '));
}

// 1-3. 파일 화면: 모든 행의 높이가 같다(긴 이름, 녹화 중 배지가 있어도 두 줄로 꺾이지 않는다).
for (const [w, h] of VIEWPORTS) {
  await open('/files', w, h, 'dark');
  const hs = await page.locator('tbody tr').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  check(`files ${w}px 행 높이가 모두 같다`, hs.length > 0 && Math.max(...hs) - Math.min(...hs) <= 1, hs.join(','));
}

// 2. 설정: 값을 바꿔 변경 상태가 되어도 폼 요소가 움직이지 않는다.
for (const [w, h] of VIEWPORTS) {
  await open('/settings', w, h, 'dark');
  const sel = 'main input, main button[role=tab], main h1';
  const before = await rects(sel);
  const field = page.locator('main input[type=number]').first();
  check(`settings ${w}px 숫자 입력칸이 있다`, (await field.count()) > 0);
  if (await field.count()) {
    await field.fill('45');
    await page.waitForTimeout(300);
    const after = await rects(sel);
    check(`settings ${w}px 변경 시 요소 좌표 불변`, JSON.stringify(before) === JSON.stringify(after));
  }
}

// 3. 모든 화면: 가로 스크롤, 12px 미만 글자, 대비, 24px 미만 클릭 대상, 표 머리글 줄바꿈, 콘솔 오류.
const audit = () => {
  const parse = (c) => { const m = c.match(/[\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m[3] ?? 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bg = getComputedStyle(document.body).backgroundColor;
  const bgOf = (el) => { const st = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c.a > 0) { st.push(c); if (c.a >= 1) break; } } let o = parse(bg); for (const c of st.reverse()) o = { r: c.r * c.a + o.r * (1 - c.a), g: c.g * c.a + o.g * (1 - c.a), b: c.b * c.a + o.b * (1 - c.a) }; return o; };
  const low = [], small = [], tiny = [], wrapped = [];
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    if ([...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) {
      const a = lum(parse(cs.color)), b = lum(bgOf(el));
      if ((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) < 4.5) low.push(el.textContent.trim().slice(0, 18));
      if (parseFloat(cs.fontSize) < 12) small.push(el.textContent.trim().slice(0, 18));
    }
    if (['BUTTON', 'A', 'INPUT'].includes(el.tagName) && (r.height < 24 || r.width < 24) && el.type !== 'checkbox' && !(el.type === 'hidden') && el.getAttribute('aria-hidden') !== 'true') tiny.push(`${el.tagName} ${Math.round(r.width)}x${Math.round(r.height)} ${(el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 12)}`);
    if (el.tagName === 'TH' && el.textContent.trim()) { const rg = document.createRange(); rg.selectNodeContents(el); const tops = [...rg.getClientRects()].filter((q) => q.width > 0).map((q) => q.top).sort((x, y) => x - y); if (tops.length && tops.at(-1) - tops[0] > 12) wrapped.push(el.textContent.trim().slice(0, 12)); }
  }
  return { hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth, low: [...new Set(low)], small: [...new Set(small)], tiny: [...new Set(tiny)], wrapped };
};
for (const theme of THEMES) {
  for (const [w, h] of VIEWPORTS) {
    for (const route of ROUTES) {
      errors.length = 0;
      await open(route, w, h, theme);
      const a = await page.evaluate(audit);
      const tag = `${route} ${w}px ${theme}`;
      check(`${tag} 가로 스크롤 없음`, !a.hscroll);
      check(`${tag} 대비 4.5:1 이상`, !a.low.length, a.low.slice(0, 3).join(' | '));
      check(`${tag} 12px 미만 글자 없음`, !a.small.length, a.small.slice(0, 3).join(' | '));
      check(`${tag} 24px 미만 클릭 대상 없음`, !a.tiny.length, a.tiny.slice(0, 3).join(' | '));
      check(`${tag} 표 머리글 한 줄`, !a.wrapped.length, a.wrapped.join(' | '));
      check(`${tag} 페이지 오류 없음`, !errors.length, errors[0] ?? '');
    }
  }
}

await browser.close();
console.log(`\n${fails.length ? `실패 ${fails.length}건` : '모두 통과'}`);
process.exit(fails.length ? 1 : 0);
