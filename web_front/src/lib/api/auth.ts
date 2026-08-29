import request from '@/lib/request';

export interface GithubLoginResponse {
  authorize_url: string;
}

export interface GithubCallbackRequest {
  code: string;
  state?: string;
}

export interface GithubUser {
  id: number;
  login: string;
  name: string | null;
  email: string | null;
  avatar_url: string;
  html_url: string;
}

export interface GithubCallbackResponse {
  user: GithubUser;
  jti?: string;  // 当前会话的JTI，用于过滤自身session_kicked事件
}

export async function getGithubAuthUrl(): Promise<GithubLoginResponse> {
  const { data } = await request.get<GithubLoginResponse>('/auth/github/login');
  return data;
}

export async function githubCallback(params: GithubCallbackRequest): Promise<GithubCallbackResponse> {
  const { data } = await request.post<GithubCallbackResponse>('/auth/github/callback', params, {
    timeout: 30000, // GitHub OAuth 涉及外部 API 调用，超时设为 30 秒
  });
  return data;
}

/** 退出登录：吊销服务端会话并清除HttpOnly Cookie（幂等）。 */
export async function logout(): Promise<void> {
  await request.post('/auth/logout');
}