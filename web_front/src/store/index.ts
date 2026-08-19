import { create } from 'zustand';
import type { User, Resume, InterviewQuestion, InterviewReport, InterviewState, CommunityPost } from '@/types';
import { mockQuestions, mockReport } from '@/lib/mocks/data';
import { githubCallback, logout as logoutApi } from '@/lib/api/auth';
import type { GithubUser } from '@/lib/api/auth';
import {
  getMyProfile,
  updateMyProfile as updateMyProfileApi,
  updateProfileVisibility as updateProfileVisibilityApi,
  deleteAccount as deleteAccountApi,
  followUser as followUserApi,
  unfollowUser as unfollowUserApi,
} from '@/lib/api/user';
import type { UserProfileResponse, UserUpdateRequest } from '@/lib/api/user';

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
  authLoading: boolean;
  resumes: Resume[];
  currentInterview: InterviewState | null;
  reports: Record<string, InterviewReport>;
  followedPosts: CommunityPost[];

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, nickname: string) => Promise<void>;
  handleGithubCallback: (code: string) => Promise<void>;
  initAuth: () => Promise<void>;
  refreshUser: () => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (updates: Partial<Pick<User, 'nickname' | 'avatar' | 'gender' | 'birthday' | 'bio' | 'phone' | 'location' | 'profileVisibility'>>) => Promise<void>;
  deleteAccount: () => Promise<void>;
  removeResume: (resumeId: string) => void;
  addResume: (resume: Resume) => void;
  startInterview: (resumeId: string, questions: InterviewQuestion[]) => void;
  submitAnswer: (questionId: string, answer: string) => void;
  completeInterview: (report: InterviewReport) => void;
  nextQuestion: () => void;
}

/** 将后端性别整数映射为前端性别字符串 */
function mapGender(gender: number): 'male' | 'female' | 'other' {
  if (gender === 1) return 'male';
  if (gender === 2) return 'female';
  return 'other';
}

/** 将后端user_settings可见性字段映射为前端可见性对象 */
function mapProfileVisibility(profile: UserProfileResponse): User['profileVisibility'] {
  return {
    gender: profile.visibility_gender === 1,
    birthday: profile.visibility_birthday === 1,
    bio: profile.visibility_bio === 1,
    location: profile.visibility_location === 1,
    phone: profile.visibility_phone === 1,
  };
}

/** 将后端UserProfileResponse映射为前端User类型 */
function mapUserProfile(profile: UserProfileResponse): User {
  return {
    id: String(profile.id),
    email: profile.email || '',
    nickname: profile.nickname,
    avatar: profile.avatar || undefined,
    gender: mapGender(profile.gender),
    birthday: profile.birthday || '',
    bio: profile.bio,
    phone: profile.phone || '',
    location: profile.location || '',
    followingCount: profile.following_count,
    followersCount: profile.followers_count,
    followingIds: [],
    profileVisibility: mapProfileVisibility(profile),
  };
}

function mapGithubUser(githubUser: GithubUser): User {
  return {
    id: String(githubUser.id),
    email: githubUser.email || '',
    nickname: githubUser.name || githubUser.login,
    avatar: githubUser.avatar_url,
    gender: 'other',
    birthday: '',
    bio: '',
    phone: '',
    location: '',
    followingCount: 0,
    followersCount: 0,
    followingIds: [],
    profileVisibility: {
      gender: true,
      birthday: true,
      bio: true,
      location: true,
      phone: false,
    },
  };
}

export const useAppStore = create<AppState>((set, get) => ({
  user: null,
  isLoggedIn: false,
  authLoading: true,
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
        gender: 'other',
        birthday: '',
        bio: '',
        phone: '',
        location: '',
        followingCount: 23,
        followersCount: 156,
        followingIds: ['u2', 'u3', 'u4', 'u5'],
        profileVisibility: {
          gender: true,
          birthday: true,
          bio: true,
          location: true,
          phone: false,
        },
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
        gender: 'other',
        birthday: '',
        bio: '',
        phone: '',
        location: '',
        followingCount: 0,
        followersCount: 0,
        followingIds: [],
        profileVisibility: {
          gender: true,
          birthday: true,
          bio: true,
          location: true,
          phone: false,
        },
      },
      isLoggedIn: true,
    });
  },

  handleGithubCallback: async (code: string) => {
    const res = await githubCallback({ code });
    const user = mapGithubUser(res.user);
    localStorage.setItem('auth_user', JSON.stringify(user));
    set({ user, isLoggedIn: true });
  },

  initAuth: async () => {
    const userStr = localStorage.getItem('auth_user');
    if (userStr) {
      try {
        const user = JSON.parse(userStr) as User;
        set({ user, isLoggedIn: true, authLoading: false });
      } catch {
        localStorage.removeItem('auth_user');
        set({ authLoading: false });
      }
      return;
    }

    // 本地无缓存时，尝试从后端 /users/me 拉取资料（Cookie 由浏览器自动携带）
    try {
      const profile = await getMyProfile();
      const user = mapUserProfile(profile);
      localStorage.setItem('auth_user', JSON.stringify(user));
      set({ user, isLoggedIn: true, authLoading: false });
    } catch {
      set({ authLoading: false });
    }
  },

  refreshUser: async () => {
    try {
      const profile = await getMyProfile();
      const user = mapUserProfile(profile);
      localStorage.setItem('auth_user', JSON.stringify(user));
      set({ user });
    } catch {
      // 刷新失败不改变当前状态
    }
  },

  logout: async () => {
    try {
      await logoutApi();
    } catch {
      // 服务端已失效时忽略，继续清理本地
    }
    localStorage.removeItem('auth_user');
    set({
      user: null,
      isLoggedIn: false,
      currentInterview: null,
    });
  },

  updateUser: async (updates) => {
    const currentUser = get().user;
    if (!currentUser) return;

    // 构建后端请求体
    const body: UserUpdateRequest = {};
    if (updates.nickname !== undefined) body.nickname = updates.nickname;
    if (updates.avatar !== undefined) body.avatar = updates.avatar || undefined;
    if (updates.gender !== undefined) {
      body.gender = updates.gender === 'male' ? 1 : updates.gender === 'female' ? 2 : 0;
    }
    if (updates.birthday !== undefined) body.birthday = updates.birthday || undefined;
    if (updates.bio !== undefined) body.bio = updates.bio || undefined;
    if (updates.phone !== undefined) body.phone = updates.phone || undefined;
    if (updates.location !== undefined) body.location = updates.location || undefined;

    // 如果更新了可见性，单独调用可见性接口（按字段发送）
    if (updates.profileVisibility !== undefined) {
      const newVisibility = updates.profileVisibility;
      await updateProfileVisibilityApi({
        visibility_gender: newVisibility.gender ? 1 : 0,
        visibility_birthday: newVisibility.birthday ? 1 : 0,
        visibility_bio: newVisibility.bio ? 1 : 0,
        visibility_location: newVisibility.location ? 1 : 0,
        visibility_phone: newVisibility.phone ? 1 : 0,
      });
    }

    // 调用更新资料接口
    const profile = await updateMyProfileApi(body);
    const user = mapUserProfile(profile);
    localStorage.setItem('auth_user', JSON.stringify(user));
    set({ user });
  },

  deleteAccount: async () => {
    await deleteAccountApi();
    localStorage.removeItem('auth_user');
    set({
      user: null,
      isLoggedIn: false,
      currentInterview: null,
    });
  },

  removeResume: (resumeId: string) => {
    set((state) => ({
      resumes: state.resumes.filter((r) => r.id !== resumeId),
    }));
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