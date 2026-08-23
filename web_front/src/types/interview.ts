export type QuestionType = 'technical' | 'project' | 'behavioral';

/** 题目维度，用于 AI 分析完成后的维度卡片与面试间标签展示（对齐后端 category） */
export type QuestionCategory = '技术八股' | '项目与社会实践' | '综合素养' | '架构设计';

export interface InterviewQuestion {
  id: string;
  questionNo: number;
  questionText: string;
  questionType: QuestionType;
  /** 题目所属维度，缺省时按 questionType 推断 */
  category?: QuestionCategory;
  /** 是否为追问题；追问题在面试间会展示「追问」徽标 */
  followUp?: boolean;
  userAnswer?: string;
  aiScore?: number;
  aiComment?: string;
}

export interface InterviewReport {
  id: string;
  totalScore: number;
  summary: string;
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
  questionDetails: InterviewQuestion[];
  interviewTime: string;
  resumeName: string;
  type: 'full' | 'quick';
  questionCount: number;
}

export type InterviewStatus = 'idle' | 'in_progress' | 'completed';

export interface InterviewState {
  id: string;
  resumeId: string;
  questions: InterviewQuestion[];
  currentQuestionIndex: number;
  status: InterviewStatus;
}

export const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  technical: '技术题',
  project: '项目题',
  behavioral: '行为题',
};

export const QUESTION_TYPE_COLOR: Record<QuestionType, string> = {
  technical: 'orange',
  project: 'green',
  behavioral: 'purple',
};