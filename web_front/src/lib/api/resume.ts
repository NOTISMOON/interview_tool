/** 简历模块API客户端，对接后端 /api/v1/resumes 端点。 */

import request from '@/lib/request';

/** 简历解析状态（对齐后端 resume.status） */
export type ResumeStatus = 0 | 1 | 2;

/** 工作经历（对齐后端 ResumeWorkExperienceOut） */
export interface ApiWorkExperience {
  id: number;
  company: string;
  role: string;
  duration: string | null;
  description: string | null;
  sort_order: number;
}

/** 后端简历详情/列表项（对齐后端 ResumeOut） */
export interface ApiResume {
  id: number;
  user_id: number;
  file_name: string;
  file_url: string | null;
  file_size: number | null;
  status: ResumeStatus;
  parsed_name: string | null;
  parsed_skills: string[] | null;
  parsed_education: Array<Record<string, unknown>> | null;
  parsed_projects: Array<Record<string, unknown>> | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  work_experiences: ApiWorkExperience[];
}

/** 简历分页列表响应 */
export interface ApiResumeListResponse {
  items: ApiResume[];
  total: number;
  page: number;
  page_size: number;
}

/** 解析状态文案/配色映射 */
export const RESUME_STATUS_LABEL: Record<ResumeStatus, string> = {
  0: '解析中',
  1: '已就绪',
  2: '解析失败',
};

/**
 * 查询当前用户简历列表（分页）。
 * @param page 页码（从1开始）
 * @param pageSize 页大小
 */
export async function getResumes(page = 1, pageSize = 20): Promise<ApiResumeListResponse> {
  const { data } = await request.get<ApiResumeListResponse>('/resumes', {
    params: { page, page_size: pageSize },
  });
  return data;
}

/**
 * 删除简历（软删 + 联动清理COS/缓存/锁）。
 * @param resumeId 简历ID
 */
export async function deleteResume(resumeId: number): Promise<void> {
  await request.delete(`/resumes/${resumeId}`);
}

/**
 * 对解析失败的简历一键重试。
 * @param resumeId 简历ID
 */
export async function retryResume(resumeId: number): Promise<ApiResume> {
  const { data } = await request.post<ApiResume>(`/resumes/${resumeId}/retry`);
  return data;
}