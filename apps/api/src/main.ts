import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import type { NextFunction, Request, Response } from 'express';
import express from 'express';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { AppModule } from './app.module.js';
import { requireLogin, security } from './auth/auth.guard.js';
import { AuthService } from './auth/auth.service.js';
import { StoreService } from './config/store.service.js';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bodyParser: false });
  app.enableShutdownHooks();
  const role = process.env.ROLE ?? 'all';
  // 녹화기는 인증 없이 소켓으로만 받는다. 소켓 설정이 빠졌는데 포트로 열리면 인증이 사라지므로 시작하지 않는다.
  if (role === 'recorder' && !process.env.RECORDER_SOCKET) throw new Error('ROLE=recorder 에는 RECORDER_SOCKET 이 필요합니다.');

  if (role !== 'recorder') app.use(security);

  // 웹 컨테이너는 채널/녹화 API를 녹화기로 그대로 넘긴다 (본문을 읽기 전에 스트림째 전달). Nest 가드를 거치지 않으니 로그인 검사를 앞에 둔다.
  if (role === 'app') {
    app.use(['/api/channels', '/api/recording'], requireLogin(app.get(AuthService)), (req: Request, res: Response) => {
      const up = http.request({ socketPath: process.env.RECORDER_SOCKET, method: req.method, path: req.originalUrl, headers: req.headers }, (r) => {
        res.writeHead(r.statusCode ?? 502, r.headers);
        r.pipe(res);
      });
      up.on('error', () => res.status(502).json({ message: '녹화기에 연결할 수 없습니다' }));
      req.pipe(up);
    });
  }
  app.use(express.json({ limit: '5mb' }));

  // 빌드된 웹(SPA)을 같은 포트에서 서빙한다. /api 이외의 GET은 index.html로 보낸다.
  const webDist = process.env.WEB_DIST ?? path.resolve(import.meta.dirname, '../../web/dist');
  if (role !== 'recorder' && fs.existsSync(webDist)) {
    app.use(express.static(webDist));
    app.use((req: Request, res: Response, next: NextFunction) =>
      req.method === 'GET' && !req.path.startsWith('/api') ? res.sendFile(path.join(webDist, 'index.html')) : next(),
    );
  }

  // 녹화기는 포트 대신 공유 볼륨의 유닉스 소켓으로만 받는다 (NAS의 브리지 방화벽이 컨테이너 사이 TCP를 막는다).
  if (role === 'recorder' && process.env.RECORDER_SOCKET) {
    fs.rmSync(process.env.RECORDER_SOCKET, { force: true });
    await app.listen(process.env.RECORDER_SOCKET);
    console.log(`[recordWEB] recorder socket ${process.env.RECORDER_SOCKET}`);
    return;
  }
  const port = Number(process.env.PORT) || app.get(StoreService).getConfig().port;
  await app.listen(port, '0.0.0.0');
  console.log(`[recordWEB] http://0.0.0.0:${port}  (web: ${fs.existsSync(webDist) ? webDist : '없음'})`);
}

void bootstrap();
