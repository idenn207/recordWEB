import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { AuthController } from './auth/auth.controller.js';
import { AuthGuard } from './auth/auth.guard.js';
import { AuthService } from './auth/auth.service.js';
import { ChannelsController } from './channels/channels.controller.js';
import { SettingsController } from './config/settings.controller.js';
import { StoreService } from './config/store.service.js';
import { FilesController } from './files/files.controller.js';
import { FilesService } from './files/files.service.js';
import { NotifierService } from './recorder/notifier.service.js';
import { RecorderClient } from './recorder/recorder-client.js';
import { RecorderService } from './recorder/recorder.service.js';
import { SystemController } from './system/system.controller.js';
import { UploadsController } from './uploads/uploads.controller.js';
import { YtUploadService } from './uploads/yt-upload.service.js';

// ROLE=recorder: 녹화/후처리 + 채널 API, ROLE=app: 웹 + 업로드 + 파일 관리 (녹화 요청은 녹화기로 프록시), 없으면 한 프로세스에 전부(개발용).
// 웹/업로더를 배포해도 녹화가 끊기지 않게 하려는 분리다.
const role = process.env.ROLE ?? 'all';
const recorder = role !== 'app';
const app = role !== 'recorder';

@Module({
  controllers: [...(recorder ? [ChannelsController] : []), ...(app ? [AuthController, SettingsController, FilesController, UploadsController, SystemController] : [])],
  providers: [
    AuthService,
    { provide: APP_GUARD, useClass: AuthGuard },
    StoreService,
    NotifierService,
    ...(recorder ? [RecorderService] : [{ provide: RecorderService, useClass: RecorderClient }]),
    ...(app ? [YtUploadService, FilesService] : []),
  ],
})
export class AppModule {}
