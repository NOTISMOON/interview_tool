/** 面试模块API客户端，对接后端 /api/v1/interviews 端点（面试流程功能文档 §3.4）。 */

import request from '@/lib/request';
import { TAB_ID } from '@/lib/tabId';

/** 面试类型：1-完整面试 2-快速面试 */
export type InterviewType = 1 | 2;

/** 面试状态：0-进行中 1-已完成 2-已中断 */
export type InterviewStatus = 0 | 1 | 2;

/** 面试阶段（后端 Checkpoint phase） */
export type InterviewPhase = 'not_started' | 'answering' | 'analyzing' | 'summarizing' | 'completed' | 'aborted';

/** 当前题目（后端 QuestionOut） */
export interface ApiInterviewQuestion {
  question_index: number;
  question_no: number;
  question_id: number;
  question_text: string;
  question_type: number;
  category: number | null;
  is_follow_up: boolean;
}

/** 创建面试响应（后端 InterviewCreateResponse） */
export interface ApiInterviewCreateResponse {
  interview_id: number;
  epoch: number;
  status: number;
  type: number;
  total_questions: number;
  current_question: ApiInterviewQuestion | null;
}

/** 面试当前状态响应（后端 InterviewStateResponse） */
export interface ApiInterviewState {
  interview_id: number;
  status: InterviewStatus;
  type: number;
  phase: InterviewPhase;
  question_index: number;
  epoch: number;
  answered_count: number;
  total_questions: number;
  current_question: ApiInterviewQuestion | null;
}

/** 单题分析摘要（后端 AnswerAnalysisOut） */
export interface ApiAnswerAnalysis {
  score: number;
  comment: string;
  correctness: string;
  technical_depth: number;
  completeness: number;
  logic: number;
  key_points: string[];
  weaknesses: string[];
}

/** 提交回答响应（后端 AnswerSubmitResponse） */
export interface ApiAnswerSubmitResponse {
  interview_id: number;
  question_index: number;
  analysis: ApiAnswerAnalysis;
  duplicated: boolean;
  phase: 'answering' | 'summarizing';
  next_question: ApiInterviewQuestion | null;
}

/** 面试报告（后端 InterviewReportResponse） */
export interface ApiInterviewReport {
  interview_id: number;
  total_score: number;
  dimension_scores: Record<string, number> | null;
  strengths: string[];
  weaknesses: string[];
  capability_profile: Record<string, string> | null;
  suggestions: string[];
  summary: string;
  question_count: number;
  follow_up_count: number;
  total_duration: number | null;
  created_at: string;
}

/** 报告状态响应（后端 ReportStatusResponse） */
export interface ApiReportStatus {
  status: 'generating' | 'ready' | 'failed' | 'invalid';
  report: ApiInterviewReport | null;
}

/** 面试记录列表项（后端 InterviewListItem） */
export interface ApiInterviewListItem {
  interview_id: number;
  status: InterviewStatus;
  type: number;
  total_score: number | null;
  follow_up_count: number;
  question_count: number;
  answered_count: number;
  report_ready: boolean;
  /** 是否已正式启动（False=草稿，设备检测前；历史页据此分流跳转） */
  is_started: boolean;
  created_at: string;
  interview_time: string | null;
  total_duration: number | null;
}

/** 面试记录列表响应 */
export interface ApiInterviewListResponse {
  items: ApiInterviewListItem[];
  total: number;
  page: number;
  page_size: number;
}

/** 面试统计响应（GET /interviews/stats，含软删除记录，删除不影响平均分） */
export interface ApiInterviewStats {
  /** 可见（未删除）记录总数，用于历史页分页 */
  total: number;
  /** 已完成面试次数（含已删记录） */
  completed_count: number;
  /** 已完成面试平均分（含已删记录，无则 null） */
  avg_score: number | null;
}

/** 逐题详情（后端 InterviewQuestionDetail，仅已结束面试返回） */
export interface ApiInterviewQuestionDetail {
  question_index: number;
  question_no: number;
  question_id: number;
  question_text: string;
  question_type: number;
  category: number | null;
  is_follow_up: boolean;
  user_answer: string | null;
  ai_score: number | null;
  ai_comment: string | null;
  answer_duration: number | null;
}

/** 逐题详情列表响应 */
export interface ApiInterviewQuestionListResponse {
  items: ApiInterviewQuestionDetail[];
  total: number;
}

/** 后端409冲突响应体：{reason, latest_state} 或 {code, message} */
export interface ApiConflictDetail {
  reason?: string;
  latest_state?: ApiInterviewState | null;
  code?: string;
  message?: string;
}

/** 题型常量 → 文案映射（对齐后端 question_type） */
export const QUESTION_TYPE_LABEL: Record<number, string> = {
  1: '技术题',
  2: '项目题',
  3: '行为题',
};

/** 题目维度常量 → 文案映射（对齐后端 category） */
export const CATEGORY_LABEL: Record<number, string> = {
  1: '技术八股',
  2: '项目与社会实践',
  3: '综合素养',
  4: '架构设计',
};

/** 面试类型 → 文案映射 */
export const INTERVIEW_TYPE_LABEL: Record<number, string> = {
  1: '完整面试',
  2: '快速面试',
};

/**
 * 从 axios 错误中提取后端409冲突详情。
 * @param err 任意抛出的错误对象
 */
export function extractConflict(err: unknown): ApiConflictDetail | null {
  const detail = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail && typeof detail === 'object') return detail as ApiConflictDetail;
  return null;
}

/**
 * 创建面试会话：简历状态硬校验 + 预生成基础题（真实LLM，耗时5~20秒）。
 * @param resumeId 简历ID（须已就绪）
 * @param type 面试类型 1-完整 2-快速
 */
export async function createInterview(resumeId: number, type: InterviewType): Promise<ApiInterviewCreateResponse> {
  const { data } = await request.post<ApiInterviewCreateResponse>(
    '/interviews',
    { resume_id: resumeId, type, tab_id: TAB_ID },
    { timeout: 120000 },
  );
  return data;
}

/**
 * 查询面试当前状态（刷新恢复/超时兜底轮询）。
 * 携带 tab_id 时触发客户端租约激活（同页幂等/新页接管 epoch+1）。
 * @param interviewId 面试会话ID
 * @param withTab 是否携带本标签页标识（进入/刷新面试页时 true）
 */
export async function getInterviewState(
  interviewId: number,
  withTab = false,
): Promise<ApiInterviewState> {
  const { data } = await request.get<ApiInterviewState>(`/interviews/${interviewId}`, {
    params: withTab ? { tab_id: TAB_ID } : undefined,
    timeout: 15000,
  });
  return data;
}

/**
 * 设备检测通过后正式启动面试（后端草稿态 not_started → answering，幂等）。
 * @param interviewId 面试会话ID
 */
export async function startInterview(interviewId: number): Promise<ApiInterviewState> {
  const { data } = await request.post<ApiInterviewState>(
    `/interviews/${interviewId}/start`,
    null,
    { timeout: 15000 },
  );
  return data;
}

/**
 * 提交回答：Fast Decision 即时判定，秒级返回下一题（v2，全量分析走异步 Worker）。
 * 幂等键 (interviewId, questionIndex)，重试安全。
 * @param interviewId 面试会话ID
 * @param questionIndex 所答题目题序（状态版本token）
 * @param answer 回答文本（语音转写或键盘输入）
 * @param tabEpoch 客户端租约epoch
 * @param answerDuration 回答时长（秒，可选）
 */
export async function submitAnswer(
  interviewId: number,
  questionIndex: number,
  answer: string,
  tabEpoch: number,
  answerDuration?: number,
): Promise<ApiAnswerSubmitResponse> {
  const { data } = await request.post<ApiAnswerSubmitResponse>(
    `/interviews/${interviewId}/answers`,
    {
      question_index: questionIndex,
      answer,
      tab_epoch: tabEpoch,
      ...(answerDuration !== undefined ? { answer_duration: answerDuration } : {}),
    },
    { timeout: 30000 },
  );
  return data;
}

/**
 * 获取面试报告（未生成时返回 generating 并惰性触发一次生成）。
 * @param interviewId 面试会话ID
 */
export async function getInterviewReport(interviewId: number): Promise<ApiReportStatus> {
  const { data } = await request.get<ApiReportStatus>(`/interviews/${interviewId}/report`, {
    timeout: 15000,
  });
  return data;
}

/**
 * 报告生成失败后的手动重试。
 * @param interviewId 面试会话ID
 */
export async function regenerateReport(interviewId: number): Promise<ApiReportStatus> {
  const { data } = await request.post<ApiReportStatus>(
    `/interviews/${interviewId}/report/regenerate`,
    null,
    { timeout: 15000 },
  );
  return data;
}

/**
 * 主动放弃面试（status=2，已答数据保留）。
 * @param interviewId 面试会话ID
 * @param tabEpoch 客户端租约epoch
 */
export async function abortInterview(interviewId: number, tabEpoch: number): Promise<void> {
  await request.post(`/interviews/${interviewId}/abort`, { tab_epoch: tabEpoch }, { timeout: 15000 });
}

/**
 * 删除面试记录（软删除：草稿/进行中/已中断/已完成均可删，不影响统计）。
 * @param interviewId 面试会话ID
 */
export async function deleteInterview(interviewId: number): Promise<void> {
  await request.delete(`/interviews/${interviewId}`, { timeout: 15000 });
}

/**
 * 查询面试统计（总次数/完成数/平均分，含软删除记录——删除不影响平均分）。
 */
export async function getInterviewStats(): Promise<ApiInterviewStats> {
  const { data } = await request.get<ApiInterviewStats>('/interviews/stats', { timeout: 15000 });
  return data;
}

/**
 * 分页查询我的面试记录列表（历史页）。
 * @param page 页码
 * @param pageSize 页大小
 */
export async function getInterviewList(page = 1, pageSize = 20): Promise<ApiInterviewListResponse> {
  const { data } = await request.get<ApiInterviewListResponse>('/interviews', {
    params: { page, page_size: pageSize },
    timeout: 15000,
  });
  return data;
}

/**
 * 查询已结束面试的逐题详情（报告页逐题展示；进行中面试返回409）。
 * @param interviewId 面试会话ID
 */
export async function getInterviewQuestions(
  interviewId: number,
): Promise<ApiInterviewQuestionListResponse> {
  const { data } = await request.get<ApiInterviewQuestionListResponse>(
    `/interviews/${interviewId}/questions`,
    { timeout: 15000 },
  );
  return data;
}
