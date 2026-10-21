"""Reauthorize an existing desktop OAuth client on this PC, optionally updating NAS."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ['https://www.googleapis.com/auth/youtube']
TOKEN_URI = 'https://oauth2.googleapis.com/token'


class UserError(ValueError):
    """An actionable message that contains no OAuth response or credentials."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


urlopen = build_opener(NoRedirect()).open


def client_config(data: object) -> dict:
    """Use only the desktop client ID/secret; ignore endpoints from input files."""
    if not isinstance(data, dict) or 'web' in data:
        raise UserError('기존 데스크톱 클라이언트의 JSON을 사용하세요.')
    client = data.get('installed', data)
    if not isinstance(client, dict) or any(
        not isinstance(client.get(key), str) or not client[key].strip()
        for key in ('client_id', 'client_secret')
    ):
        raise UserError('JSON에 client_id와 client_secret이 필요합니다.')
    return {'installed': {
        'client_id': client['client_id'], 'client_secret': client['client_secret'],
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': TOKEN_URI, 'redirect_uris': ['http://127.0.0.1'],
    }}


def nas_endpoint(base_url: str) -> str:
    url = urlsplit(base_url)
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username
            or url.password or url.path not in ('', '/') or url.query or url.fragment):
        raise UserError('NAS 주소는 http://192.168.0.10:5080 같은 기본 주소로 입력하세요.')
    return base_url.rstrip('/') + '/api/uploads/reauth'


def submit_to_nas(base_url: str, refresh_token: str) -> None:
    request = Request(
        nas_endpoint(base_url),
        data=json.dumps({'refresh_token': refresh_token}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urlopen(request, timeout=45) as response:
        if json.loads(response.read()).get('ok') is not True:
            raise UserError('NAS에서 재인증 성공을 확인하지 못했습니다. 결과 JSON은 보관됩니다.')


def save_result(output: Path, data: dict) -> None:
    """Replace the result file only after writing it completely; do not touch the source."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=output.name + '.', dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def reauthenticate(source: Path, output: Path, nas_url: str | None = None) -> None:
    if source.resolve() == output.resolve():
        raise UserError('원본과 결과 JSON은 다른 파일이어야 합니다.')
    if nas_url:
        nas_endpoint(nas_url)
    config = client_config(json.loads(source.read_text(encoding='utf-8-sig')))
    flow = InstalledAppFlow.from_client_config(
        config, scopes=SCOPES, autogenerate_code_verifier=True,
    )
    credentials = flow.run_local_server(
        host='127.0.0.1', bind_addr='127.0.0.1', port=0, timeout_seconds=600,
        prompt='consent',
        authorization_prompt_message='Google 로그인 창에서 업로드할 계정과 채널을 선택하세요.',
        success_message='Google authorization returned. You may close this tab and check the reauthentication window.',
    )
    if not credentials.refresh_token:
        raise UserError('새 refresh token을 받지 못했습니다. 다시 실행하고 권한에 동의하세요.')
    if credentials.granted_scopes is not None and not set(SCOPES).issubset(credentials.granted_scopes):
        raise UserError('YouTube 관리 권한에 동의해야 합니다.')
    client = config['installed']
    save_result(output, {
        'client_id': client['client_id'], 'client_secret': client['client_secret'],
        'refresh_token': credentials.refresh_token, 'token_uri': TOKEN_URI,
    })
    print(f'새 인증 정보를 저장했습니다: {output}', flush=True)
    if nas_url:
        submit_to_nas(nas_url, credentials.refresh_token)
        print('NAS 재인증 완료. 다음 업로드 확인 시 자동 재개합니다.', flush=True)
    else:
        print('NAS 업로드 설정의 인증 토큰 전체 JSON에 결과 파일 내용을 등록하세요.', flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='기존 데스크톱 OAuth 클라이언트로 YouTube 재인증')
    parser.add_argument('--client-file', type=Path, default=ROOT / 'json/yt_token.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'json/yt_token.reauthenticated.json')
    parser.add_argument('--nas-url', help='인증 완료 후 새 refresh token을 등록할 NAS 기본 주소')
    args = parser.parse_args(argv)
    try:
        print('Google 로그인 화면을 엽니다. 인증 대기 시간은 최대 10분입니다.', flush=True)
        reauthenticate(args.client_file, args.output, args.nas_url)
        return 0
    except UserError as error:
        print(str(error), flush=True)
    except FileNotFoundError:
        print('기존 인증 JSON을 찾지 못했습니다. --client-file 경로를 확인하세요.', flush=True)
    except HTTPError as error:
        print(f'NAS 등록 실패 (HTTP {error.code}). 저장된 결과 JSON을 NAS 설정에서 직접 등록하세요.', flush=True)
    except KeyboardInterrupt:
        print('취소했습니다.', flush=True)
    except Exception as error:
        # OAuth exceptions can contain codes or tokens; never print the original message.
        print(f'재인증을 완료하지 못했습니다 ({type(error).__name__}). 다시 실행하세요. '
              '결과 JSON이 저장되었다면 NAS 설정에서 직접 등록할 수 있습니다.', flush=True)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
