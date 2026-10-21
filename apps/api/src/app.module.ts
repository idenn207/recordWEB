import { Module } from '@nestjs/common';
import { ChannelsController } from './channels/channels.controller.js';
import { SettingsController } from './config/settings.controller.js';
import { StoreService } from './config/store.service.js';
import { FilesController } from './files/files.controller.js';
import { FilesService } from './files/files.service.js';
import { NotifierService } from './recorder/notifier.service.js';
import { RecorderService } from './recorder/recorder.service.js';
import { SystemController } from './system/system.controller.js';
import { UploadsController } from './uploads/uploads.controller.js';
import { YtUploadService } from './uploads/yt-upload.service.js';

@Module({
  controllers: [ChannelsController, SettingsController, FilesController, UploadsController, SystemController],
  providers: [StoreService, NotifierService, RecorderService, YtUploadService, FilesService],
})
export class AppModule {}
