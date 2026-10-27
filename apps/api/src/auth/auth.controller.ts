import { BadRequestException, Body, Controller, Get, HttpCode, HttpException, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { Public } from './auth.guard.js';
import { AuthService, clientIp, TooMany } from './auth.service.js';

@Controller('api/auth')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Public()
  @Get('state')
  state(@Req() req: Request) {
    return { setup: this.auth.needsSetup(), user: this.auth.user(req) };
  }

  @Public()
  @Post('setup')
  setup(@Body() b: { username?: string; password?: string }, @Req() req: Request, @Res({ passthrough: true }) res: Response) {
    try {
      this.auth.setup(String(b?.username ?? ''), String(b?.password ?? ''), clientIp(req));
    } catch (e) {
      throw new BadRequestException((e as Error).message);
    }
    this.auth.setCookie(res, this.auth.login(String(b.username), String(b.password), clientIp(req))!, req);
    return { ok: true };
  }

  @Public()
  @Post('login')
  @HttpCode(200)
  login(@Body() b: { username?: string; password?: string }, @Req() req: Request, @Res({ passthrough: true }) res: Response) {
    try {
      const token = this.auth.login(String(b?.username ?? ''), String(b?.password ?? ''), clientIp(req));
      if (!token) throw new UnauthorizedException('아이디 또는 비밀번호가 맞지 않습니다.');
      this.auth.setCookie(res, token, req);
      return { ok: true };
    } catch (e) {
      if (e instanceof TooMany) {
        res.setHeader('Retry-After', String(e.retryAfter));
        throw new HttpException(e.message, 429);
      }
      throw e;
    }
  }

  @Post('logout')
  @HttpCode(200)
  logout(@Req() req: Request, @Res({ passthrough: true }) res: Response) {
    this.auth.audit('logout', clientIp(req));
    this.auth.clearCookie(res);
    return { ok: true };
  }

  @Post('logout-all')
  @HttpCode(200)
  logoutAll(@Req() req: Request, @Res({ passthrough: true }) res: Response) {
    this.auth.logoutAll(clientIp(req));
    this.auth.clearCookie(res);
    return { ok: true };
  }

  @Post('password')
  @HttpCode(200)
  password(@Body() b: { current?: string; next?: string }, @Req() req: Request, @Res({ passthrough: true }) res: Response) {
    try {
      this.auth.setCookie(res, this.auth.changePassword(String(b?.current ?? ''), String(b?.next ?? ''), clientIp(req)), req);
    } catch (e) {
      throw new BadRequestException((e as Error).message);
    }
    return { ok: true };
  }

  @Get('activity')
  activity() {
    return this.auth.activity();
  }
}
