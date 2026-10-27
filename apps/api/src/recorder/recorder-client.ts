import { Injectable } from '@nestjs/common';
import http from 'node:http';

/** 웹/업로더 프로세스에서 RecorderService 대신 쓴다. 녹화기에 지금 쓰는 파일 목록만 물어 본다. */
@Injectable()
export class RecorderClient {
  private busy: string[] = [];

  constructor() {
    const poll = () => {
      const req = http
        .get({ socketPath: process.env.RECORDER_SOCKET, path: '/api/recorder/busy', timeout: 3000 }, (res) => {
          let text = '';
          res.on('data', (d) => (text += d));
          res.on('end', () => {
            try {
              this.busy = JSON.parse(text);
            } catch {
              this.busy = [];
            }
          });
        })
        // 녹화기가 내려가 있으면 녹화 중인 파일도 없다
        .on('error', () => (this.busy = []));
      req.on('timeout', () => req.destroy());
    };
    poll();
    setInterval(poll, 5000).unref();
  }

  busyPaths(): string[] {
    return this.busy;
  }
}
