import { BadRequestException, Body, Controller, Get, Post } from '@nestjs/common';
import { FilesService } from '../files/files.service.js';
import { YtUploadService } from './yt-upload.service.js';

@Controller('api/uploads')
export class UploadsController {
  constructor(
    private readonly uploads: YtUploadService,
    private readonly files: FilesService,
  ) {}

  @Get()
  queue() {
    return this.uploads.snapshot();
  }

  /** 파일 관리자에서 고른 파일을 수동 큐에 넣는다. 경로 검증은 파일 관리자와 같은 규칙을 쓴다. */
  @Post('enqueue')
  enqueue(@Body() b: { paths: string[] }) {
    if (!b.paths?.length) throw new BadRequestException('paths required');
    const results = b.paths.map((p) => {
      try {
        this.uploads.enqueue(this.files.ensureInRoots(p));
        return { src: p, ok: true };
      } catch (e) {
        return { src: p, ok: false, error: (e as Error).message };
      }
    });
    return { results };
  }

  @Post('settings')
  save(@Body() b: { settings?: Record<string, unknown>; token?: string }) {
    try {
      if (b.token) this.uploads.saveToken(b.token);
      if (b.settings) this.uploads.saveSettings(b.settings);
    } catch (e) {
      throw new BadRequestException((e as Error).message);
    }
    return { ok: true };
  }
}
