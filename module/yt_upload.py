"""치지직 녹화본 YouTube 자동 업로드 (NAS 배치 upload.py를 앱 안으로 이식, stdlib 전용).

백그라운드 스레드가 주기적으로 채널 폴더를 훑어 업로드할 파일을 고른다.
- 자동: 채널의 yt_auto_upload가 켜져 있고 녹화일이 auto_since 이후인 파일
- 수동: enqueue()로 state에 path가 기록된 파일
상태(세션 URL, video_id)는 json/yt_upload_state.json에 남아 재시작해도 이어서 올린다.
"""
import http.client, json, math, os, re, subprocess, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from module.data_manager import base_directory, readJsonSafe, writeJsonSafe, getFFmpeg, sendTelegram
from module.file_manager import normPath, isLocked

JDIR = os.path.join(base_directory, 'json')
TOKEN = os.path.join(JDIR, 'yt_token.json')
STATE = os.path.join(JDIR, 'yt_upload_state.json')
SETTINGS = os.path.join(JDIR, 'yt_upload.json')
EXTS = {'.ts': 'video/mp2t', '.mp4': 'video/mp4'}

DEFAULTS = {
    'pool': 3, 'rate_mbps': 120, 'scan_interval_sec': 300, 'stable_sec': 300,
    'max_sec': 12 * 3600 - 600,  # YouTube 길이 상한 12시간 (여유 10분)
    'privacy': 'unlisted', 'tags': ['#스텔라이브'],
    'description': ('스텔라이브 개인용 다시보기 채널입니다.\n\n[유니버스]\n아카네 리제 : https://www.youtube.com/@akanelize'
                    '\n\n[클리셰]\n하나코 나나 : https://www.youtube.com/@hanako_nana'),
}
SETTING_KEYS = set(DEFAULTS) | {'auto_since'}

lock = threading.RLock()
state = {}        # 파일명 -> {path?, session, video_id, privacy, playlisted}
info = {}         # 파일명 -> {state, msg}  (UI 표시용, 메모리만)
active = {}       # 파일명 -> 전체 경로  (지금 업로드 중)
retry_at = {}     # 파일명 -> 이 시각 전에는 다시 시도하지 않음
fails = {}
flags = {'auth_error': ''}
gate = [0.0]      # 이 시각 전에는 새 업로드 세션을 만들지 않는다
create_lock = threading.Lock()
_tok = {'at': None, 'exp': 0}
sent = [0]


class Fatal(Exception):
    pass


class LimitHit(Exception):
    pass


def log(*a):
    print('[YT]', time.strftime('%m-%d %H:%M:%S'), *a, flush=True)


def cfg():
    c = dict(DEFAULTS, **readJsonSafe(SETTINGS, {}))
    if not c.get('auto_since'):  # 기능을 처음 켠 날부터 자동 대상 — 밀린 파일은 수동으로 고른다
        c['auto_since'] = date.today().isoformat()
        writeJsonSafe(SETTINGS, {**readJsonSafe(SETTINGS, {}), 'auto_since': c['auto_since']})
    return c


def save_settings(new: dict):
    cur = readJsonSafe(SETTINGS, {})
    cur.update({k: v for k, v in new.items() if k in SETTING_KEYS})
    writeJsonSafe(SETTINGS, cur)


def save_token(text: str):
    t = json.loads(text)
    missing = {'refresh_token', 'client_id', 'client_secret', 'token_uri'} - set(t)
    if missing:
        raise ValueError(f'토큰 JSON에 키가 없습니다: {sorted(missing)}')
    os.makedirs(JDIR, exist_ok=True)
    with open(TOKEN, 'w', encoding='utf-8') as f:
        json.dump(t, f)
    try:
        os.chmod(TOKEN, 0o600)
    except OSError:
        pass
    with lock:
        _tok.update(at=None, exp=0)
        flags['auth_error'] = ''


def save():
    with lock:
        writeJsonSafe(STATE, state)


def token(force=False):
    with lock:
        if force or time.time() > _tok['exp']:
            if not os.path.exists(TOKEN):
                raise Fatal('yt_token.json 이 없습니다 — 업로드 화면에서 토큰을 등록하세요')
            t = json.load(open(TOKEN, encoding='utf-8'))
            body = urllib.parse.urlencode(dict(refresh_token=t['refresh_token'], client_id=t['client_id'],
                                               client_secret=t['client_secret'], grant_type='refresh_token'))
            try:
                r = json.load(urllib.request.urlopen(t['token_uri'], body.encode(), timeout=60))
            except urllib.error.HTTPError as e:
                if 'invalid_grant' in e.read().decode():
                    raise Fatal('refresh token 만료 — 재인증 필요 (토큰을 다시 등록하세요)')
                raise
            _tok.update(at=r['access_token'], exp=time.time() + r['expires_in'] - 300)
        return _tok['at']


def api(method, url, body=None, headers=None):
    """JSON API 호출. (status, headers, json) 반환. 401 은 토큰 갱신 후 1회 재시도."""
    for attempt in (0, 1):
        h = {'Authorization': 'Bearer ' + token(force=attempt == 1), 'Content-Type': 'application/json; charset=UTF-8'}
        h.update(headers or {})
        req = urllib.request.Request(url, json.dumps(body).encode() if body else None, h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                txt = r.read().decode()
                return r.status, r.headers, json.loads(txt) if txt else {}
        except urllib.error.HTTPError as e:
            txt = e.read().decode()
            if e.code == 401 and attempt == 0:
                continue
            return e.code, e.headers, json.loads(txt) if txt.startswith('{') else {'raw': txt}


def is_quota(j):
    return any(x in json.dumps(j) for x in ('quotaExceeded', 'uploadLimitExceeded', 'rateLimitExceeded'))


def split_name(fn):
    """('fixed_' 접두사, 이름, 확장자)"""
    stem, ext = os.path.splitext(fn)
    pre = 'fixed_' if stem.startswith('fixed_') else ''
    return pre, stem[len(pre):], ext


def title_of(fn, names):
    pre, name, ext = split_name(fn)
    part = ''
    m = re.match(r'(.*) \((\d+)\)$', name)
    if m:  # 'X (1)' 은 X 다음 조각 → 2부
        name, part = m.group(1), f' ({int(m.group(2)) + 1}부)'
    elif f'{pre}{name} (1){ext}' in names:
        part = ' (1부)'
    d = re.match(r'\[(\d{4})-(\d\d)-(\d\d)\] (.*)', name)
    t = (f'{d[1]} {d[2]} {d[3]} {d[4]}' if d else name) + part
    t = t.replace('<', '').replace('>', '')
    return t if len(t) <= 100 else t[:99] + '…'


def rec_date(fn):
    m = re.search(r'\[(\d{4}-\d\d-\d\d)\]', fn)
    return m[1] if m else None


class Counting:
    """전송 바이트를 세고, 모든 스트림 합산 속도를 rate_mbps 로 제한하는 파일 래퍼."""
    next_t = [0.0]

    def __init__(self, f, rate):
        self.f, self.rate = f, rate

    def read(self, n=-1):
        b = self.f.read(n)
        with lock:
            sent[0] += len(b)
            now = time.monotonic()
            start = max(Counting.next_t[0], now)
            Counting.next_t[0] = start + len(b) * 8 / (self.rate * 1e6)
        time.sleep(start - now)
        return b


def duration(path):
    err = subprocess.run([getFFmpeg(), '-hide_banner', '-i', path], capture_output=True, text=True).stderr
    h, m, s = re.search(r'Duration: (\d+):(\d+):([\d.]+)', err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def split_long(path, c):
    """12시간 초과 파일을 N등분해 'X.ts', 'X (1).ts' … 로 바꾸고 원본은 _over12h/ 로 옮긴다 (재인코딩 없음).
    분할했으면 새 파일 경로 목록을, 아니면 None 을 반환한다."""
    d = duration(path)
    if d <= c['max_sec']:
        return None
    src_dir, fn = os.path.split(path)
    pre, name, ext = split_name(fn)
    n, base = math.ceil(d / c['max_sec']), os.path.splitext(fn)[0]
    outs = [fn] + [f'{pre}{name} ({i}){ext}' for i in range(1, n)]
    if any(os.path.exists(os.path.join(src_dir, o)) for o in outs[1:]):
        raise RuntimeError(f'분할 이름 충돌 — 직접 처리 필요: {fn}')
    log(f'분할 {d / 3600:.1f}h → {n}개: {fn}')
    hold = os.path.join(src_dir, '_over12h')
    os.makedirs(hold, exist_ok=True)
    subprocess.run([getFFmpeg(), '-hide_banner', '-loglevel', 'error', '-y', '-i', path, '-map', '0', '-c', 'copy',
                    '-f', 'segment', '-reset_timestamps', '1',
                    '-segment_times', ','.join(str(int(d * i / n)) for i in range(1, n)),
                    os.path.join(hold, f'{base}.part%d{ext}')], check=True)
    os.replace(path, os.path.join(hold, fn))
    for i, o in enumerate(outs):
        os.replace(os.path.join(hold, f'{base}.part{i}{ext}'), os.path.join(src_dir, o))
    return [os.path.join(src_dir, o) for o in outs]


def playlist_of(fn, channels):
    return next((c.get('yt_playlist_id') for c in channels if c.get('name') and c['name'] in fn), None)


def is_done(fn, channels):
    st = state.get(fn, {})
    return bool(st.get('video_id')) and (st.get('playlisted') or not playlist_of(fn, channels))


def upload(path, channels, c):
    fn = os.path.basename(path)
    size = os.path.getsize(path)
    names = set(os.listdir(os.path.dirname(path)))
    with lock:
        st = state.setdefault(fn, {})
    pl = playlist_of(fn, channels)
    while 'video_id' not in st:
        if 'session' not in st:
            meta = {'snippet': {'title': title_of(fn, names), 'description': c['description'], 'tags': c['tags'], 'categoryId': '22'},
                    'status': {'privacyStatus': c['privacy'], 'selfDeclaredMadeForKids': False}}
            # 실패한 insert 도 일일 할당량을 쓴다 → 세션 생성은 한 번에 하나, 한도에 걸리면 전체가 1시간 대기
            with create_lock:
                time.sleep(max(0, gate[0] - time.time()))
                code, h, j = api('POST', 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                                 meta, {'X-Upload-Content-Length': str(size), 'X-Upload-Content-Type': EXTS[os.path.splitext(fn)[1].lower()]})
                if code == 429 or (code != 200 and is_quota(j)):
                    gate[0] = time.time() + 3600
                    raise LimitHit(f'한도 {code} → {time.strftime("%H:%M", time.localtime(gate[0]))} 까지 전체 대기')
            if code != 200:
                raise RuntimeError(f'세션 생성 실패 {code} {j}')
            st['session'] = h['Location']
            save()
        # 서버가 받은 위치 확인 후 이어서 PUT
        u = urllib.parse.urlsplit(st['session'])
        conn = http.client.HTTPSConnection(u.netloc, timeout=300, blocksize=1 << 20)
        try:
            conn.request('PUT', u.path + '?' + u.query, headers={'Authorization': 'Bearer ' + token(), 'Content-Length': '0',
                                                                  'Content-Range': f'bytes */{size}'})
            r = conn.getresponse(); body = r.read().decode()
            if r.status in (200, 201):
                j = json.loads(body); st['video_id'], st['privacy'] = j['id'], j['status']['privacyStatus']; break
            if r.status in (404, 410):  # 세션 만료 → 처음부터
                st.pop('session'); save(); continue
            if r.status != 308:
                raise RuntimeError(f'오프셋 조회 실패 {r.status} {body[:300]}')
            rng = r.getheader('Range')
            off = int(rng.split('-')[1]) + 1 if rng else 0
            with open(path, 'rb') as f:
                f.seek(off)
                conn.request('PUT', u.path + '?' + u.query, body=Counting(f, c['rate_mbps']), headers={
                    'Authorization': 'Bearer ' + token(), 'Content-Length': str(size - off),
                    'Content-Range': f'bytes {off}-{size - 1}/{size}'})
                r = conn.getresponse(); body = r.read().decode()
            if r.status in (200, 201):
                j = json.loads(body)
                st['video_id'], st['privacy'] = j['id'], j['status']['privacyStatus']
            elif is_quota(body):
                raise RuntimeError('quota ' + body[:200])
            elif r.status < 500 and r.status != 308:
                raise RuntimeError(f'업로드 실패 {r.status} {body[:300]}')
        finally:
            conn.close()
    save()
    if pl and not st.get('playlisted'):
        code, _, j = api('POST', 'https://www.googleapis.com/youtube/v3/playlistItems?part=snippet',
                         {'snippet': {'playlistId': pl, 'resourceId': {'kind': 'youtube#video', 'videoId': st['video_id']}}})
        if code != 200:
            raise RuntimeError(f'재생목록 추가 실패 {code} {j}')
        st['playlisted'] = True
        save()
    log(f'완료 [{st["privacy"]}] https://youtu.be/{st["video_id"]}  {fn}')


def worker(path, channels, c):
    fn = os.path.basename(path)
    try:
        if 'video_id' not in state.get(fn, {}) and 'session' not in state.get(fn, {}):  # 세션이 열린 파일은 자르지 않는다
            parts = split_long(path, c)
            if parts:  # 조각은 다음 스캔에서 개별 파일로 올라간다
                with lock:
                    state.pop(fn, None)
                    for p in parts:
                        state[os.path.basename(p)] = {'path': p}
                save()
                return
        info[fn] = {'state': 'uploading', 'msg': ''}
        upload(path, channels, c)
        info[fn] = {'state': 'done', 'msg': ''}
        fails.pop(fn, None)
    except Fatal as e:
        if not flags['auth_error']:
            sendTelegram(f'[YouTube 업로드] 중단: {e}')
        flags['auth_error'] = str(e)
        info[fn] = {'state': 'error', 'msg': str(e)}
    except LimitHit as e:
        info[fn] = {'state': 'waiting', 'msg': str(e)}
        retry_at[fn] = gate[0]
    except Exception as e:
        n = fails[fn] = fails.get(fn, 0) + 1
        wait = 3600 if 'quota' in str(e) else min(30 * 2 ** (n - 1), 1800)
        log(f'오류 → {wait}s 후 재시도: {fn}: {str(e)[:300]}')
        info[fn] = {'state': 'error', 'msg': str(e)[:300]}
        retry_at[fn] = time.time() + wait
    finally:
        active.pop(fn, None)


def candidates(channels, busy, c):
    """이번 스캔에서 올릴 파일 {전체경로}."""
    now, out = time.time(), set()

    def ok(p):
        return os.path.isfile(p) and not isLocked(p, busy) and now - os.path.getmtime(p) >= c['stable_sec']

    for ch in channels:
        if ch.get('platform') != 'chzzk' or not ch.get('yt_auto_upload'):
            continue
        d = os.path.join(base_directory, ch.get('output_dir', ''))
        if not os.path.isdir(d):
            continue
        names = set(os.listdir(d))
        for fn in names:
            pre, name, ext = split_name(fn)
            if ext.lower() not in EXTS or fn.startswith('_') or ch['name'] not in fn:
                continue
            if not pre and 'fixed_' + fn in names:  # fixed_ 변환본이 있으면 그쪽만 올린다
                continue
            if (rec_date(fn) or '') >= c['auto_since'] and ok(os.path.join(d, fn)):
                out.add(os.path.join(d, fn))
    for fn, st in list(state.items()):  # 수동 큐
        if st.get('path') and not st.get('video_id') and ok(st['path']):
            out.add(st['path'])
    return out


def enqueue(path):
    path = os.path.abspath(path)
    fn = os.path.basename(path)
    if not os.path.isfile(path) or os.path.splitext(fn)[1].lower() not in EXTS:
        raise ValueError('.ts / .mp4 파일만 업로드할 수 있습니다')
    with lock:
        st = state.setdefault(fn, {})
        if st.get('video_id'):
            raise ValueError('이미 업로드된 파일입니다')
        st['path'] = path
    retry_at.pop(fn, None)
    save()


def active_paths():
    return [normPath(p) for p in list(active.values())]


def snapshot():
    rows = []
    for fn, st in state.items():
        i = info.get(fn, {})
        s = 'done' if st.get('video_id') else i.get('state', 'queued')
        rows.append({'name': fn, 'state': s, 'msg': i.get('msg', ''), 'video_id': st.get('video_id'),
                     'privacy': st.get('privacy')})
    order = {'uploading': 0, 'waiting': 1, 'error': 2, 'queued': 3, 'done': 4}
    rows.sort(key=lambda r: (order[r['state']], r['name']))
    return {'auth_error': flags['auth_error'], 'has_token': os.path.exists(TOKEN), 'settings': cfg(), 'items': rows}


def _loop(get_ctx):
    state.update(readJsonSafe(STATE, {}))
    pool = ThreadPoolExecutor(cfg()['pool'])  # shortcut: pool 변경은 재시작 후 반영, 필요하면 동적 조정으로 교체
    while True:
        c = cfg()
        try:
            if not flags['auth_error']:
                channels, busy = get_ctx()
                for p in candidates(channels, busy, c):
                    fn = os.path.basename(p)
                    if fn in active or is_done(fn, channels) or retry_at.get(fn, 0) > time.time():
                        continue
                    active[fn] = p
                    info.setdefault(fn, {'state': 'queued', 'msg': ''})
                    pool.submit(worker, p, channels, c)
        except Exception as e:
            log(f'스캔 오류: {e}')
        time.sleep(c['scan_interval_sec'])


def start(get_ctx):
    """get_ctx() -> (channels, busy_paths). 데몬 스레드라 앱 종료 시 같이 끝나며, 세션은 state 에 남아 이어 올린다."""
    threading.Thread(target=_loop, args=(get_ctx,), daemon=True, name='yt-upload').start()
