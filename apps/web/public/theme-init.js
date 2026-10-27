// 첫 화면이 그려지기 전에 저장된 테마를 적용한다 (깜빡임 방지). CSP 때문에 인라인이 아닌 별도 파일이다.
try {
  var t = localStorage.getItem('rw-theme') || 'system';
  document.documentElement.dataset.theme = t === 'system' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : t;
} catch (e) {
  document.documentElement.dataset.theme = 'dark';
}
