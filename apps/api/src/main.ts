import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import type { NextFunction, Request, Response } from 'express';
import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { AppModule } from './app.module.js';
import { StoreService } from './config/store.service.js';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bodyParser: false });
  app.enableShutdownHooks();
  app.use(express.json({ limit: '5mb' }));

  // 빌드된 웹(SPA)을 같은 포트에서 서빙한다. /api 이외의 GET은 index.html로 보낸다.
  const webDist = process.env.WEB_DIST ?? path.resolve(import.meta.dirname, '../../web/dist');
  if (fs.existsSync(webDist)) {
    app.use(express.static(webDist));
    app.use((req: Request, res: Response, next: NextFunction) =>
      req.method === 'GET' && !req.path.startsWith('/api') ? res.sendFile(path.join(webDist, 'index.html')) : next(),
    );
  }

  const port = Number(process.env.PORT) || app.get(StoreService).getConfig().port;
  await app.listen(port, '0.0.0.0');
  console.log(`[recordWEB] http://0.0.0.0:${port}  (web: ${fs.existsSync(webDist) ? webDist : '없음'})`);
}

void bootstrap();
