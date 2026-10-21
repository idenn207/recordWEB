import { BadRequestException, Body, Controller, Delete, Get, NotFoundException, Param, Post, Put } from '@nestjs/common';
import { StoreService } from '../config/store.service.js';
import { RecorderService } from '../recorder/recorder.service.js';

@Controller('api')
export class ChannelsController {
  constructor(
    private readonly store: StoreService,
    private readonly recorder: RecorderService,
  ) {}

  private channel(id: string) {
    const ch = this.store.getChannel(id);
    if (!ch) throw new NotFoundException('Channel not found');
    return ch;
  }

  /** 채널 설정 + 실시간 상태(녹화 중/예약/대기, 방송 정보)를 한 번에. UI는 이 목록을 폴링한다. */
  @Get('channels')
  list() {
    return this.store.getChannels().map((ch) => ({ ...ch, status: this.recorder.status(ch) }));
  }

  @Post('channels')
  add(@Body() body: unknown) {
    try {
      const ch = this.store.addChannel(body);
      // 자동 녹화가 켜진 채널은 서버를 재시작하지 않아도 바로 감시를 시작한다
      if (ch.record_enabled && this.store.getConfig().autoRecordingMode) this.recorder.start(ch.id, false);
      return ch;
    } catch (e) {
      throw new BadRequestException((e as Error).message);
    }
  }

  @Put('channels/:id')
  update(@Param('id') id: string, @Body() body: unknown) {
    this.channel(id);
    try {
      return this.store.updateChannel(id, body);
    } catch (e) {
      throw new BadRequestException((e as Error).message);
    }
  }

  @Delete('channels/:id')
  async remove(@Param('id') id: string) {
    this.channel(id);
    await this.recorder.stop(id);
    this.store.removeChannel(id);
    return { ok: true };
  }

  @Post('channels/:id/toggle')
  async toggle(@Param('id') id: string) {
    const ch = this.channel(id);
    const updated = this.store.updateChannel(id, { record_enabled: !ch.record_enabled });
    await this.recorder.onToggled(updated);
    if (updated.record_enabled && this.store.getConfig().autoRecordingMode) this.recorder.start(id, false);
    return { record_enabled: updated.record_enabled };
  }

  @Post('channels/:id/start')
  start(@Param('id') id: string) {
    this.channel(id);
    this.recorder.start(id, true);
    return { ok: true };
  }

  @Post('channels/:id/stop')
  async stop(@Param('id') id: string) {
    this.channel(id);
    await this.recorder.stop(id);
    return { ok: true };
  }

  @Post('recording/start-all')
  startAll() {
    this.recorder.startAll();
    return { ok: true };
  }

  @Post('recording/stop-all')
  async stopAll() {
    await this.recorder.stopAll();
    return { ok: true };
  }
}
