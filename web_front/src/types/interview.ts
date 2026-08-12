export type QuestionType = 'technical' | 'project' | 'behavioral';

export interface InterviewQuestion {
  id: string;
  questionNo: number;
  questionText: string;
  questionType: QuestionType;
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