// 목업 공통: 아이콘(apps/web/src/shared/ui/icon.tsx 와 같은 경로), 테마 전환, 상태 전환(#해시).
const PATHS = {
  rec: 'M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0M12 3v2M12 19v2M3 12h2M19 12h2',
  channels: 'M4 6h16v10H4zM8 20h8M12 16v4',
  files: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  upload: 'M12 16V5M7.5 9.5L12 5l4.5 4.5M5 19h14',
  download: 'M12 5v11M7.5 11.5L12 16l4.5-4.5M5 19h14',
  settings: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 4v6M9 14v6',
  play: 'M8 5.5v13l10-6.5z',
  stop: 'M7 7h10v10H7z',
  more: 'M12 6h.01M12 12h.01M12 18h.01',
  refresh: 'M20 12a8 8 0 1 1-2.5-5.8M20 4v4h-4',
  up: 'M12 19V6M6.5 11.5L12 6l5.5 5.5',
  edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  trash: 'M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12M10 11v5M14 11v5',
  move: 'M3 12h14M13 7l5 5-5 5M21 5v14',
  copy: 'M9 9h10v10H9zM5 15V5h10',
  folderPlus: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM12 10v5M9.5 12.5h5',
  file: 'M7 3h7l4 4v14H7zM14 3v4h4',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  lock: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  alert: 'M12 4l9 16H3zM12 10v4.5M12 17.5h.01',
  x: 'M6 6l12 12M18 6L6 18',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
};
export const ic = (n, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true"${n === 'more' ? ' style="stroke-width:3.4"' : ''}><path d="${PATHS[n]}"/></svg>`;

export const NAV = [
  ['index', 'dashboard.html', 'rec', '녹화 현황', '현황'],
  ['channels', '#', 'channels', '채널 관리', '채널'],
  ['files', 'files.html', 'files', '파일 관리', '파일'],
  ['uploads', '#', 'upload', 'YouTube 업로드', '업로드'],
  ['settings', '#', 'settings', '설정', '설정'],
];

export function shell(active, recordingCount, content) {
  return `<div class="shell">
  <aside class="side">
    <div class="brand"><b>recordWEB</b><span>녹화 서버</span></div>
    <nav class="nav" aria-label="주 메뉴">
      ${NAV.map(([k, href, icon, full, short]) => `<a href="${href}" ${k === active ? 'aria-current="page"' : ''}>${ic(icon)}<span class="full">${full}</span><span class="short">${short}</span>${k === 'index' && recordingCount ? `<span class="count" aria-label="${recordingCount}개 채널 녹화 중"><span class="d"></span><span class="tnum">${recordingCount}</span></span>` : ''}</a>`).join('')}
    </nav>
  </aside>
  <main>${content}</main>
</div>`;
}

/** 목업 도구 줄. 상태 버튼은 #해시로 바뀌므로 링크로 공유할 수 있다. */
export function mockbar(title, states, current, onChange) {
  const el = document.createElement('div');
  el.className = 'mockbar';
  el.innerHTML = `<strong>목업 · ${title}</strong>` + states.map(([k, label]) => `<button type="button" data-k="${k}" aria-pressed="${k === current}">${label}</button>`).join('') + `<span class="sp"></span><button type="button" data-theme-toggle>테마: 시스템</button>`;
  el.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.k) { location.hash = b.dataset.k; }
    if (b.hasAttribute('data-theme-toggle')) {
      const r = document.documentElement;
      const next = r.dataset.theme === 'dark' ? 'light' : r.dataset.theme === 'light' ? '' : 'dark';
      if (next) r.dataset.theme = next; else delete r.dataset.theme;
      b.textContent = '테마: ' + (next === 'dark' ? '어두움' : next === 'light' ? '밝음' : '시스템');
    }
  });
  document.body.prepend(el);
  const sync = () => {
    const k = location.hash.slice(1) || states[0][0];
    el.querySelectorAll('[data-k]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.k === k)));
    onChange(k);
  };
  addEventListener('hashchange', sync);
  sync();
}
