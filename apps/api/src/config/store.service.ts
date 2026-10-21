import { Injectable } from '@nestjs/common';
import fs from 'node:fs';
import { jsonPath } from '../lib/paths.js';
import { readJson, writeJson } from '../lib/json-store.js';
import { normalizeXCookieInput, parseXCookies, XCookies } from '../x/x.js';
import { Channel, Config, normalizeChannel, normalizeChannels, normalizeConfig } from './config.js';

const CONFIG = jsonPath('config.json');
const CHANNELS = jsonPath('channels.json');
const COOKIE = jsonPath('cookie.json');
const YCOOKIE = jsonPath('ycookie.txt');
const TELEGRAM = jsonPath('telegram.json');
const XCOOKIE = jsonPath('xcookie.txt');

export interface ChzzkCookies {
  NID_AUT?: string;
  NID_SES?: string;
}

/** 설정/채널/쿠키의 메모리 사본과 JSON 파일 저장을 한곳에서 맡는다. */
@Injectable()
export class StoreService {
  private config = normalizeConfig(readJson(CONFIG, {}));
  private channels = normalizeChannels(readJson(CHANNELS, []));

  getConfig(): Config {
    return this.config;
  }

  setConfig(patch: Partial<Config>): Config {
    this.config = normalizeConfig({ ...this.config, ...patch });
    writeJson(CONFIG, this.config);
    return this.config;
  }

  getChannels(): Channel[] {
    return this.channels;
  }

  getChannel(id: string): Channel | undefined {
    return this.channels.find((c) => c.id === id);
  }

  addChannel(raw: unknown): Channel {
    const c = normalizeChannel(raw);
    if (!c) throw new Error('platform/id가 올바르지 않습니다');
    if (!c.name) throw new Error('채널명이 필요합니다');
    if (this.channels.some((x) => x.platform === c.platform && x.id === c.id)) throw new Error('이미 등록된 채널입니다');
    this.channels.push(c);
    this.saveChannels();
    return c;
  }

  updateChannel(id: string, patch: unknown): Channel {
    const cur = this.getChannel(id);
    if (!cur) throw new Error('Channel not found');
    const next = normalizeChannel({ ...cur, ...(patch as object), id });
    if (!next) throw new Error('잘못된 채널 값입니다');
    Object.assign(cur, next); // 녹화 루프가 들고 있는 참조에도 바로 반영된다
    this.saveChannels();
    return cur;
  }

  removeChannel(id: string): boolean {
    const i = this.channels.findIndex((c) => c.id === id);
    if (i < 0) return false;
    this.channels.splice(i, 1);
    this.saveChannels();
    return true;
  }

  private saveChannels() {
    writeJson(CHANNELS, this.channels);
  }

  getChzzkCookies(): ChzzkCookies {
    const v = readJson<ChzzkCookies>(COOKIE, {});
    return v && typeof v === 'object' ? v : {};
  }

  setChzzkCookies(c: ChzzkCookies) {
    writeJson(COOKIE, { NID_AUT: c.NID_AUT ?? '', NID_SES: c.NID_SES ?? '' });
  }

  /** yt-dlp에 넘기는 Netscape 형식 쿠키 파일 경로. 없으면 null. */
  getYoutubeCookiePath(): string | null {
    return fs.existsSync(YCOOKIE) ? YCOOKIE : null;
  }

  getYoutubeCookieText(): string {
    return fs.existsSync(YCOOKIE) ? fs.readFileSync(YCOOKIE, 'utf8') : '';
  }

  setYoutubeCookieText(text: string) {
    fs.mkdirSync(jsonPath('.'), { recursive: true });
    fs.writeFileSync(YCOOKIE, text, 'utf8');
  }

  /** yt-dlp에 넘기는 X 쿠키 파일(Netscape). auth_token/ct0가 없으면 null. */
  getXCookiePath(): string | null {
    return this.getXCookies() ? XCOOKIE : null;
  }

  getXCookies(): XCookies | null {
    return fs.existsSync(XCOOKIE) ? parseXCookies(fs.readFileSync(XCOOKIE, 'utf8')) : null;
  }

  getXCookieText(): string {
    return fs.existsSync(XCOOKIE) ? fs.readFileSync(XCOOKIE, 'utf8') : '';
  }

  /** 빈 문자열이면 삭제(헤더만 남김), 아니면 검증 후 Netscape 형식으로 저장. 검증 실패 시 예외. */
  setXCookieText(text: string) {
    fs.mkdirSync(jsonPath('.'), { recursive: true });
    fs.writeFileSync(XCOOKIE, text.trim() ? normalizeXCookieInput(text) : '# Netscape HTTP Cookie File\n', 'utf8');
    try {
      fs.chmodSync(XCOOKIE, 0o600);
    } catch {
      /* Windows 등 */
    }
  }

  getTelegram(): { token: string; chatId: string } {
    const t = readJson<Record<string, string>>(TELEGRAM, {});
    return { token: t.telegram_bot_token ?? '', chatId: t.telegram_chat_id ?? '' };
  }

  setTelegram(token: string, chatId: string) {
    writeJson(TELEGRAM, { telegram_bot_token: token, telegram_chat_id: chatId });
  }
}
