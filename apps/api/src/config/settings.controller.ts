import { BadRequestException, Body, Controller, Get, Post, Put, Req } from '@nestjs/common';
import type { Request } from 'express';
import { AuthService, clientIp } from '../auth/auth.service.js';
import { NotifierService } from '../recorder/notifier.service.js';
import { checkX, normalizeHandle } from '../x/x.js';
import { Config } from './config.js';
import { StoreService } from './store.service.js';

interface SecretsBody {
  chzzk?: { NID_AUT?: string; NID_SES?: string };
  youtubeCookie?: string;
  xCookie?: string;
  telegram?: { token?: string; chatId?: string };
}

const MASK = '••••';
const mask = (v?: string) => (v ? MASK + v.trim().slice(-4) : '');
const isMasked = (v: unknown) => typeof v === 'string' && v.startsWith(MASK);

@Controller('api')
export class SettingsController {
  constructor(
    private readonly store: StoreService,
    private readonly notifier: NotifierService,
    private readonly auth: AuthService,
  ) {}

  @Get('config')
  config() {
    return this.store.getConfig();
  }

  @Put('config')
  save(@Body() body: Partial<Config>) {
    return this.store.setConfig(body ?? {});
  }

  /** 쿠키/토큰류. 값은 가려서 돌려주고(등록 여부와 끝 4자리만), 화면은 바꿀 때만 새 값을 보낸다. */
  @Get('secrets')
  secrets() {
    const t = this.store.getTelegram();
    const c = this.store.getChzzkCookies();
    return {
      chzzk: { NID_AUT: mask(c.NID_AUT), NID_SES: mask(c.NID_SES) },
      youtubeCookie: mask(this.store.getYoutubeCookieText()),
      xCookie: mask(this.store.getXCookies() ? this.store.getXCookieText() : ''),
      telegram: { token: mask(t.token), chatId: t.chatId },
    };
  }

  @Put('secrets')
  saveSecrets(@Body() body: SecretsBody, @Req() req: Request) {
    // 들어온 값: 없음이거나 현재 가림 값 그대로면 변경 아님, 가림 표시로 시작하는데 다르면 일부만 고친 것이라 거절, 그 외는 새 값.
    const pick = (incoming: unknown, current: string): string | undefined => {
      if (typeof incoming !== 'string' || (current && incoming === mask(current)) || (!current && incoming === '')) return undefined; // 빈 값은 등록된 값을 지우는 요청이다
      if (isMasked(incoming)) throw new BadRequestException('가려진 값은 일부만 고칠 수 없습니다. 칸을 모두 지우고 새 값을 입력하세요.');
      return incoming;
    };
    this.auth.audit('secrets', clientIp(req), Object.keys(body ?? {}).join(','));
    try {
      const curX = this.store.getXCookies() ? this.store.getXCookieText() : '';
      const x = pick(body.xCookie, curX);
      const cur = this.store.getChzzkCookies();
      const aut = pick(body.chzzk?.NID_AUT, cur.NID_AUT ?? '');
      const ses = pick(body.chzzk?.NID_SES, cur.NID_SES ?? '');
      const yt = pick(body.youtubeCookie, this.store.getYoutubeCookieText());
      const tg = this.store.getTelegram();
      const token = pick(body.telegram?.token, tg.token);
      // 모든 값을 검사한 뒤에야 저장한다. 하나라도 거절되면 아무것도 바뀌지 않는다.
      if (x !== undefined) this.store.setXCookieText(x); // 형식 검증도 여기서 한다
      if (aut !== undefined || ses !== undefined) this.store.setChzzkCookies({ NID_AUT: aut ?? cur.NID_AUT, NID_SES: ses ?? cur.NID_SES });
      if (yt !== undefined) this.store.setYoutubeCookieText(yt);
      if (token !== undefined || body.telegram?.chatId !== undefined) this.store.setTelegram(token ?? tg.token, body.telegram?.chatId ?? tg.chatId);
    } catch (e) {
      if (e instanceof BadRequestException) throw e;
      throw new BadRequestException((e as Error).message);
    }
    return { ok: true };
  }

  /** X 연결 확인: 쿠키 → 사용자 ID → 스페이스 조회를 단계별로 돌려준다. */
  @Post('x/check')
  async xCheck(@Body() body: { handle?: string; userId?: string }) {
    if (!body?.handle?.trim()) throw new BadRequestException('handle required');
    return checkX(normalizeHandle(body.handle), this.store.getXCookies(), body.userId);
  }

  @Post('telegram/test')
  async testTelegram() {
    try {
      const sent = await this.notifier.send('recordWEB 텔레그램 테스트 메시지입니다.');
      if (!sent) throw new Error('텔레그램이 꺼져 있거나 봇 토큰/채팅 ID가 비어 있습니다');
      return { ok: true };
    } catch (e) {
      throw new BadRequestException((e as Error).message);
    }
  }
}
