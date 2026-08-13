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
  access_token: string;
  token_type: string;
  user: GithubUser;
}

export async function getGithubAuthUrl(): Promise<GithubLoginResponse> {
  const { data } = await request.get<GithubLoginResponse>('/auth/github/login');
  return data;
}

export async function githubCallback(params: GithubCallbackRequest): Promise<GithubCallbackResponse> {
  const { data } = await request.post<GithubCallbackResponse>('/auth/github/callback', params);
  return data;
}