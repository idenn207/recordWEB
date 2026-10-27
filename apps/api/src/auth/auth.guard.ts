import { CanActivate, ExecutionContext, Injectable, SetMetadata, UnauthorizedException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { NextFunction, Request, Response } from 'express';
import { AuthService } from './auth.service.js';

export const Public = () => SetMetadata('public', true);

/** 모든 /api 라우트는 로그인해야 쓴다. @Public() 이 붙은 인증 라우트만 예외. */
@Injectable()
export class AuthGuard implements CanActivate {
  constructor(
    private readonly auth: AuthService,
    private readonly reflector: Reflector,
  ) {}

  canActivate(ctx: ExecutionContext): boolean {
    if (process.env.ROLE === 'recorder') return true; // 녹화기는 유닉스 소켓으로 app만 접근한다
    if (this.reflector.getAllAndOverride<boolean>('public', [ctx.getHandler(), ctx.getClass()])) return true;
    const req = ctx.switchToHttp().getRequest<Request>();
    if (this.auth.user(req)) return true;
    throw new UnauthorizedException(this.auth.needsSetup() ? 'setup_required' : 'login_required');
  }
}

const CSP = "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; frame-ancestors 'none'";

/** 보안 헤더와 same-origin 검사. 상태를 바꾸는 요청의 Origin이 Host와 다르면 거절한다 (CSRF). */
export function security(req: Request, res: Response, next: NextFunction) {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'same-origin');
  res.setHeader('Content-Security-Policy', CSP);
  if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
    const origin = req.headers.origin;
    let host: string | null = null;
    try {
      host = origin ? new URL(origin).host : null; // 'null' 같은 값은 해석할 수 없으니 거절한다
    } catch {
      host = '';
    }
    if (origin && host !== req.headers.host) return void res.status(403).json({ message: '허용되지 않은 출처의 요청입니다.' });
  }
  next();
}

/** 녹화기 프록시 앞에서 쓰는 로그인 검사 (Nest 가드를 거치지 않는 경로). */
export const requireLogin = (auth: AuthService) => (req: Request, res: Response, next: NextFunction) =>
  auth.user(req) ? next() : void res.status(401).json({ message: auth.needsSetup() ? 'setup_required' : 'login_required' });
