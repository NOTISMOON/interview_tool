import type { InterviewQuestion, InterviewReport, UserBrief, PostComment } from '@/types';

export const mockFollowingList: UserBrief[] = [
  { id: 'u2', nickname: '上岸的鱼', avatar: '', bio: '已拿到大厂 offer，分享面试经验', isFollowing: true },
  { id: 'u3', nickname: 'Go 夜读', avatar: '', bio: '后端开发，Go 语言爱好者', isFollowing: true },
  { id: 'u4', nickname: '求职小白', avatar: '', bio: '2026 届毕业生，正在找工作中', isFollowing: true },
  { id: 'u5', nickname: '老码农', avatar: '', bio: '10 年开发经验，技术管理方向', isFollowing: true },
  { id: 'u6', nickname: 'Pythonista', avatar: '', bio: '数据科学 + 后端开发', isFollowing: false },
  { id: 'u7', nickname: '前端小张', avatar: '', bio: '三年 Vue 经验，正在学 React', isFollowing: true },
];

export const mockFollowersList: UserBrief[] = [
  { id: 'u8', nickname: 'ByteDancer', avatar: '', bio: '字节跳动后端开发', isFollowing: false, isFollowedBy: true },
  { id: 'u9', nickname: 'Alibaba Cloud', avatar: '', bio: '阿里云前端工程师', isFollowing: true, isFollowedBy: true },
  { id: 'u10', nickname: 'React 达人', avatar: '', bio: 'React 开源贡献者', isFollowing: false, isFollowedBy: true },
  { id: 'u11', nickname: '面试达人', avatar: '', bio: '已帮助 100+ 人通过面试', isFollowing: false, isFollowedBy: true },
  { id: 'u12', nickname: '全栈小李', avatar: '', bio: '全栈开发，热爱技术分享', isFollowing: true, isFollowedBy: false },
  { id: 'u5', nickname: '老码农', avatar: '', bio: '10 年开发经验，技术管理方向', isFollowing: true, isFollowedBy: true },
];

export const mockPostDetailComments: PostComment[] = [
  {
    id: 'c1',
    postId: '1',
    authorId: 'u2',
    authorName: '上岸的鱼',
    authorAvatar: '',
    content: '深有同感！我也是面了好几次才过，建议多刷 leetcode，系统设计可以看看 DDIA。',
    likes: 23,
    createdAt: '5 分钟前',
  },
  {
    id: 'c2',
    postId: '1',
    authorId: 'u3',
    authorName: 'Go 夜读',
    authorAvatar: '',
    content: '可以参考一下我这个面经整理，里面有很多系统设计的高频题。',
    likes: 15,
    createdAt: '15 分钟前',
  },
  {
    id: 'c3',
    postId: '1',
    authorId: 'u4',
    authorName: '求职小白',
    authorAvatar: '',
    content: '加油！同是天涯沦落人😭',
    likes: 8,
    createdAt: '30 分钟前',
  },
  {
    id: 'c4',
    postId: '1',
    authorId: 'u5',
    authorName: '老码农',
    authorAvatar: '',
    content: '三年经验面字节确实有难度，建议先面一些中小厂积累经验再冲大厂。',
    likes: 32,
    createdAt: '1 小时前',
  },
];

export const mockQuestions: InterviewQuestion[] = [
  {
    id: 'q1',
    questionNo: 1,
    questionText: '请简要介绍一下你自己，以及你在前端开发领域的主要技术栈？',
    questionType: 'behavioral',
  },
  {
    id: 'q2',
    questionNo: 2,
    questionText:
      '你在简历中提到使用 React 开发过大型项目，请介绍一下你在项目中如何处理状态管理？为什么选择这个方案？',
    questionType: 'project',
  },
  {
    id: 'q3',
    questionNo: 3,
    questionText: '请解释一下 React 的 Virtual DOM 的工作原理，以及它相比直接操作 DOM 的优势是什么？',
    questionType: 'technical',
  },
  {
    id: 'q4',
    questionNo: 4,
    questionText:
      '你的项目中提到了性能优化，请具体说说你做过哪些前端性能优化措施？效果如何衡量？',
    questionType: 'project',
  },
  {
    id: 'q5',
    questionNo: 5,
    questionText: '请描述一下你遇到过的最难的技术问题，以及你是如何解决它的？',
    questionType: 'behavioral',
  },
  {
    id: 'q6',
    questionNo: 6,
    questionText: '如果让你设计一个高并发的实时消息系统，你会考虑哪些技术方案？',
    questionType: 'technical',
  },
  {
    id: 'q7',
    questionNo: 7,
    questionText: '你对未来 3-5 年的职业规划是什么？你希望在这个岗位上获得什么？',
    questionType: 'behavioral',
  },
];

export const mockReport: InterviewReport = {
  totalScore: 82,
  summary:
    '整体表现良好，展现了扎实的前端技术功底和项目经验。在 React 相关技术问题上回答较为深入，但部分系统设计类问题可以更加全面。沟通表达清晰，具备良好的学习能力和问题解决能力。',
  strengths: [
    '前端技术基础扎实，React 生态系统理解深入',
    '有实际的大型项目经验，能结合实践回答问题',
    '沟通表达清晰，逻辑思维能力强',
    '对性能优化有实际经验和量化思维',
  ],
  weaknesses: [
    '系统设计类问题考虑维度不够全面',
    '部分技术细节可以更深入展开',
    '对后端技术栈了解相对有限',
  ],
  suggestions: [
    '建议加强对分布式系统和后端架构的学习',
    '可以多关注前端工程化和构建工具链的底层原理',
    '面试中可以更主动地展示自己的思考过程',
    '建议准备一些更有深度的项目案例来展示技术能力',
  ],
  questionDetails: [
    {
      ...mockQuestions[0],
      userAnswer:
        '我是一名有5年经验的前端开发工程师，主要技术栈是 React + TypeScript。我参与过多个大型 B 端项目的开发，对组件化开发、状态管理、性能优化有比较深入的了解。',
      aiScore: 4,
      aiComment: '自我介绍简洁明了，突出了核心优势和技术栈，但可以补充一些量化成果。',
    },
    {
      ...mockQuestions[1],
      userAnswer:
        '我们项目初期使用 Redux，但随着业务复杂度增加，Redux 的样板代码太多。后来我们迁移到了 Zustand，它的 API 更简洁，学习成本低，配合 React Context 做局部状态管理，整体状态管理方案更清晰。',
      aiScore: 5,
      aiComment: '回答很好，展示了从实际问题出发做技术选型的能力，对不同方案的优劣有清晰认识。',
    },
    {
      ...mockQuestions[2],
      userAnswer:
        'Virtual DOM 是真实 DOM 的 JavaScript 对象映射。React 通过对比新旧 Virtual DOM 树来计算出最小的 DOM 更新操作。优势在于批量更新减少了真实 DOM 操作次数，并且让跨平台渲染成为可能。',
      aiScore: 4,
      aiComment: '基本概念解释准确，可以补充 Fiber 架构和增量渲染相关的知识。',
    },
    {
      ...mockQuestions[3],
      userAnswer:
        '我们做了代码分割、图片懒加载、虚拟列表、防抖节流、以及使用 Webpack Bundle Analyzer 分析打包体积。优化后首屏加载时间从 4.5s 降到了 1.8s。',
      aiScore: 5,
      aiComment: '答案具体且有量化指标，体现了工程实践能力。',
    },
    {
      ...mockQuestions[4],
      userAnswer:
        '最难的一次是排查一个内存泄漏问题，用户在长时间使用后页面变得很卡。通过 Chrome DevTools 的 Memory Profiler 逐步定位到是事件监听器没有正确移除导致的。',
      aiScore: 4,
      aiComment: '展示了问题排查的系统性方法，可以补充一下预防类似问题的措施。',
    },
    {
      ...mockQuestions[5],
      userAnswer:
        '我会考虑使用 WebSocket 做实时通信，消息队列做异步处理，Redis 做缓存。前端方面使用虚拟滚动处理大量消息渲染。',
      aiScore: 3,
      aiComment: '方案基本正确，但缺乏对一致性、可靠性、消息顺序等关键问题的考虑。',
    },
    {
      ...mockQuestions[6],
      userAnswer:
        '我希望在前端架构方向深入发展，3年内成为技术专家。同时我也希望在这个岗位上能够接触到更多大型项目的架构设计，提升自己的技术深度和广度。',
      aiScore: 4,
      aiComment: '职业规划清晰，有明确的发展方向，与技术岗位的需求匹配。',
    },
  ],
};