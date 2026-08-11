import { create } from 'zustand';
import type { User, Resume, InterviewQuestion, InterviewReport, InterviewState, CommunityPost } from '@/types';
import { mockQuestions, mockReport } from '@/mocks/data';

const MOCK_FOLLOWED_POSTS: CommunityPost[] = [
  {
    id: 'f1', title: '分享一套后端面试常见问题整理',
    content: '整理了最近面试遇到的 50 道高频题，包括 JVM、并发、数据库、Redis 等核心知识点...',
    author: { id: 'u3', nickname: 'Go 夜读', avatar: '' },
    tags: ['资源分享', '后端'], likes: 89, comments: 23, views: 1800,
    isPinned: false, isHot: false, createdAt: '5 小时前',
  },
  {
    id: 'f2', title: 'AI 模拟面试真的有用！拿到 offer 了',
    content: '用这个工具练习了两周，面试时明显感觉更自信了，推荐大家都试试...',
    author: { id: 'u2', nickname: '上岸的鱼', avatar: '' },
    tags: ['经验分享', 'Offer'], likes: 256, comments: 89, views: 5600,
    isPinned: false, isHot: true, createdAt: '2 小时前',
  },
  {
    id: 'f3', title: '35 岁程序员何去何从？大龄转管理经验分享',
    content: '做了 10 年开发，最近成功转技术管理，分享一下我的转型心得...',
    author: { id: 'u5', nickname: '老码农', avatar: '' },
    tags: ['职业规划', '经验分享'], likes: 342, comments: 120, views: 8900,
    isPinned: false, isHot: true, createdAt: '昨天',
  },
  {
    id: 'f4', title: '面试时如何回答"你的缺点是什么"？',
    content: '每次被问到这个问题都不知道怎么回答，求大佬指点...',
    author: { id: 'u4', nickname: '求职小白', avatar: '' },
    tags: ['面试技巧', '求助'], likes: 67, comments: 34, views: 1200,
    isPinned: false, isHot: false, createdAt: '昨天',
  },
];

interface AppState {
  user: User | null;
  isLoggedIn: boolean;
  resumes: Resume[];
  currentInterview: InterviewState | null;
  reports: Record<string, InterviewReport>;
  followedPosts: CommunityPost[];

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, nickname: string) => Promise<void>;
  loginWithGithub: () => Promise<void>;
  logout: () => void;
  updateUser: (nickname: string, avatar?: string) => void;
  addResume: (resume: Resume) => void;
  startInterview: (resumeId: string, questions: InterviewQuestion[]) => void;
  submitAnswer: (questionId: string, answer: string) => void;
  completeInterview: (report: InterviewReport) => void;
  nextQuestion: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  user: null,
  isLoggedIn: false,
  resumes: [],
  currentInterview: null,
  reports: {},
  followedPosts: MOCK_FOLLOWED_POSTS,

  login: async (email: string, _password: string) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    set({
      user: {
        id: '1',
        email,
        nickname: email.split('@')[0],
        followingCount: 23,
        followersCount: 156,
        followingIds: ['u2', 'u3', 'u4', 'u5'],
      },
      isLoggedIn: true,
    });
  },

  register: async (email: string, _password: string, nickname: string) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    set({
      user: {
        id: '1',
        email,
        nickname,
        followingCount: 0,
        followersCount: 0,
        followingIds: [],
      },
      isLoggedIn: true,
    });
  },

  loginWithGithub: async () => {
    await new Promise((resolve) => setTimeout(resolve, 1200));
    set({
      user: {
        id: 'github_user',
        email: 'github@interview.dev',
        nickname: 'GitHub 用户',
        avatar: 'https://avatars.githubusercontent.com/u/0?v=4',
        followingCount: 0,
        followersCount: 0,
        followingIds: [],
      },
      isLoggedIn: true,
    });
  },

  logout: () => {
    set({
      user: null,
      isLoggedIn: false,
      currentInterview: null,
    });
  },

  updateUser: (nickname: string, avatar?: string) => {
    set((state) => {
      if (!state.user) return state;
      return {
        user: {
          ...state.user,
          nickname,
          ...(avatar !== undefined ? { avatar } : {}),
        },
      };
    });
  },

  addResume: (resume: Resume) => {
    set((state) => ({
      resumes: [resume, ...state.resumes],
    }));
  },

  startInterview: (resumeId: string, questions: InterviewQuestion[]) => {
    const id = `interview_${Date.now()}`;
    set({
      currentInterview: {
        id,
        resumeId,
        questions,
        currentQuestionIndex: 0,
        status: 'in_progress',
      },
    });
  },

  submitAnswer: (questionId: string, answer: string) => {
    set((state) => {
      if (!state.currentInterview) return state;
      const questions = state.currentInterview.questions.map((q) =>
        q.id === questionId ? { ...q, userAnswer: answer } : q
      );
      return {
        currentInterview: { ...state.currentInterview, questions },
      };
    });
  },

  completeInterview: (report: InterviewReport) => {
    const { currentInterview } = get();
    if (!currentInterview) return;
    set((state) => ({
      currentInterview: { ...currentInterview, status: 'completed' },
      reports: {
        ...state.reports,
        [currentInterview.id]: report,
      },
    }));
  },

  nextQuestion: () => {
    set((state) => {
      if (!state.currentInterview) return state;
      return {
        currentInterview: {
          ...state.currentInterview,
          currentQuestionIndex: state.currentInterview.currentQuestionIndex + 1,
        },
      };
    });
  },
}));

export { mockQuestions, mockReport };