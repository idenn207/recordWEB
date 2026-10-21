import { BadRequestException, Body, Controller, Get, Post, Query, Res } from '@nestjs/common';
import type { Response } from 'express';
import { FilesService } from './files.service.js';

const need = (v: unknown, msg: string) => {
  if (!v || (Array.isArray(v) && !v.length)) throw new BadRequestException(msg);
};

@Controller('api/files')
export class FilesController {
  constructor(private readonly files: FilesService) {}

  @Get('roots')
  roots() {
    return this.files.roots();
  }

  @Get('ls')
  ls(@Query('path') path: string, @Query('show_hidden') showHidden?: string) {
    need(path, 'path required');
    return this.files.ls(path, showHidden === 'true' || showHidden === '1');
  }

  @Get('disk-usage')
  disk(@Query('paths') paths?: string | string[]) {
    return { usages: this.files.diskUsage(paths == null ? undefined : [paths].flat()) };
  }

  @Get('download')
  download(@Query('path') path: string, @Res() res: Response) {
    need(path, 'path required');
    res.download(this.files.downloadPath(path));
  }

  @Post('mkdir')
  mkdir(@Body() b: { path: string; new_name: string }) {
    need(b.path && b.new_name, 'path/new_name required');
    return { created: this.files.mkdir(b.path, b.new_name) };
  }

  @Post('rename')
  rename(@Body() b: { path: string; new_name: string }) {
    need(b.path && b.new_name, 'path/new_name required');
    return { path: this.files.rename(b.path, b.new_name) };
  }

  @Post('move')
  move(@Body() b: { srcs: string[]; dst_dir: string }) {
    need(b.srcs?.length && b.dst_dir, 'srcs/dst_dir required');
    return { moved: this.files.move(b.srcs, b.dst_dir) };
  }

  @Post('delete')
  remove(@Body() b: { paths: string[]; hard?: boolean }) {
    need(b.paths, 'paths required');
    return { deleted: this.files.remove(b.paths, Boolean(b.hard)) };
  }

  @Post('streamcopy')
  async streamCopy(@Body() b: { paths: string[] }) {
    need(b.paths, 'paths required');
    return { results: await this.files.streamCopy(b.paths) };
  }
}
