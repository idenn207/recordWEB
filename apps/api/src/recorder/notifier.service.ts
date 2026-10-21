import { Injectable } from '@nestjs/common';
import { StoreService } from '../config/store.service.js';

@Injectable()
export class NotifierService {
  private last = new Map<string, string>();

  constructor(private readonly store: StoreService) {}

  /** 같은 채널에 같은 상태를 연속으로 알리지 않는다. key가 없으면 항상 보낸다. */
  async notify(message: string, dedupe?: { channelId: string; state: string }) {
    if (dedupe) {
      if (this.last.get(dedupe.channelId) === dedupe.state) return;
      this.last.set(dedupe.channelId, dedupe.state);
    }
    await this.send(message).catch((e) => console.warn('[TELEGRAM]', (e as Error).message));
  }

  async send(message: string): Promise<boolean> {
    if (!this.store.getConfig().telegram_enabled) return false;
    const { token, chatId } = this.store.getTelegram();
    if (!token || !chatId) return false;
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text: message, parse_mode: 'HTML' }),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return true;
  }
}

export const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c] as string);
