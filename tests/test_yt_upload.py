"""python tests/test_yt_upload.py  (프로젝트 루트에서 실행, 외부 의존성 없음)"""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from module import yt_upload as y


def test_title_of():
    assert y.title_of('fixed_[2026-09-09] 하나코 나나 게임.ts', set()) == '2026 09 09 하나코 나나 게임'
    names = {'[2026-01-02] t.ts', '[2026-01-02] t (1).ts'}  # 분할 조각: 원본은 1부, 'X (1)' 은 2부
    assert y.title_of('[2026-01-02] t.ts', names) == '2026 01 02 t (1부)'
    assert y.title_of('[2026-01-02] t (1).ts', names) == '2026 01 02 t (2부)'
    assert len(y.title_of('[2026-01-02] ' + 'ㅋ' * 300 + '.ts', set())) == 100


def test_candidates():
    with tempfile.TemporaryDirectory() as root:
        y.base_directory = root
        d = os.path.join(root, 'chzzk'); os.makedirs(os.path.join(d, '_over12h'))
        old = time.time() - 3600

        def mk(name, aged=True):
            p = os.path.join(d, name)
            open(p, 'wb').write(b'x')
            if aged:
                os.utime(p, (old, old))
            return p
        want = mk('fixed_[2026-10-22] 유니 방송.ts')
        mk('[2026-10-22] 유니 방송.ts')           # fixed_ 변환본이 있으므로 제외
        mk('fixed_[2026-09-01] 유니 옛날.ts')      # auto_since 이전
        mk('fixed_[2026-10-23] 다른사람 방송.ts')   # 채널명 불일치
        mk('fixed_[2026-10-24] 유니 방금.ts', aged=False)  # mtime 불안정(후처리 중일 수 있음)
        ch = [{'platform': 'chzzk', 'name': '유니', 'output_dir': 'chzzk', 'yt_auto_upload': True}]
        c = dict(y.DEFAULTS, auto_since='2026-10-01')
        y.state.clear()
        assert y.candidates(ch, [], c) == {want}
        assert y.candidates([dict(ch[0], yt_auto_upload=False)], [], c) == set()  # 꺼진 채널은 자동 대상 아님
        assert y.candidates(ch, [y.normPath(want)], c) == set()                   # 녹화/업로드 중 잠금
        y.state['x.ts'] = {'path': mk('수동.ts')}                                   # 수동 큐는 채널 설정과 무관
        assert os.path.join(d, '수동.ts') in y.candidates([], [], c)


def test_enqueue_and_done():
    with tempfile.TemporaryDirectory() as root:
        p = os.path.join(root, 'a.ts'); open(p, 'wb').write(b'x')
        y.state.clear(); y.save = lambda: None
        y.enqueue(p)
        assert y.state['a.ts']['path'] == p
        y.state['a.ts']['video_id'] = 'abc'
        assert y.is_done('a.ts', [])  # 재생목록 없는 채널은 video_id 만으로 완료
        assert not y.is_done('a.ts', [{'name': 'a', 'yt_playlist_id': 'PL1'}])
        try:
            y.enqueue(p); assert False
        except ValueError:
            pass  # 이미 올린 파일은 거부


if __name__ == '__main__':
    for n, f in list(globals().items()):
        if n.startswith('test_'):
            f(); print('ok', n)
