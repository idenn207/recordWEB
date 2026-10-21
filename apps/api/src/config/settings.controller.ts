import { BadRequestException, Body, Controller, Get, Post, Put } from '@nestjs/common';
import { NotifierService } from '../recorder/notifier.service.js';
import { Config } from './config.js';
import { StoreService } from './store.service.js';

interface SecretsBody {
  chzzk?: { NID_AUT?: string; NID_SES?: string };
  youtubeCookie?: string;
  telegram?: { token?: string; chatId?: string };
}

@Controller('api')
export class SettingsController {
  constructor(
    private readonly store: StoreService,
    private readonly notifier: NotifierService,
  ) {}

  @Get('config')
  config() {
    return this.store.getConfig();
  }

  @Put('config')
  save(@Body() body: Partial<Config>) {
    return this.store.setConfig(body ?? {});
  }

  /** 쿠키/토큰류. LAN 전용 단일 사용자 도구라 편집을 위해 값을 그대로 돌려준다. */
  @Get('secrets')
  secrets() {
    return { chzzk: this.store.getChzzkCookies(), youtubeCookie: this.store.getYoutubeCookieText(), telegram: this.store.getTelegram() };
  }

  @Put('secrets')
  saveSecrets(@Body() body: SecretsBody) {
    if (body.chzzk) this.store.setChzzkCookies(body.chzzk);
    if (typeof body.youtubeCookie === 'string') this.store.setYoutubeCookieText(body.youtubeCookie);
    if (body.telegram) this.store.setTelegram(body.telegram.token ?? '', body.telegram.chatId ?? '');
    return { ok: true };
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
