import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Collapse } from 'antd';
import {
  ArrowLeftOutlined,
  QuestionCircleOutlined,
  MessageOutlined,
  MailOutlined,
} from '@ant-design/icons';

const FAQ_ITEMS = [
  {
    key: '1',
    label: '如何使用 AI 模拟面试功能？',
    children: '在「开始面试」页面，上传你的简历文件（支持 PDF、Word、图片格式），AI 将自动解析你的简历内容，并生成针对性的面试题目。然后进入面试答题环节，逐题作答，完成后即可查看详细的面试报告。',
  },
  {
    key: '2',
    label: '面试报告包含哪些内容？',
    children: '面试报告包含：总分评估、综合评语、优势亮点、待改进项、改进建议，以及每道题的详细评分和 AI 点评。你可以通过报告了解自己的面试表现和能力短板。',
  },
  {
    key: '3',
    label: '支持哪些类型的面试题？',
    children: '面试题覆盖四个维度：技术八股（考察基础功底）、项目与社会实践（考察项目、实习与团队协作）、架构设计（考察系统设计与方案取舍）、综合素养（考察沟通表达与职业规划），综合素养题放在最后。题目由 AI 根据你的简历内容自动生成。',
  },
  {
    key: '4',
    label: '社区功能有哪些？',
    children: '社区是面试经验交流的平台，你可以浏览热门帖子、关注感兴趣的用户、点赞和收藏优质内容，也可以自己发帖分享面试经验。后续还将上线更多互动功能。',
  },
  {
    key: '5',
    label: '如何修改个人资料？',
    children: '在「个人设置」页面，点击头像旁边的编辑按钮，可以修改昵称和更换头像。其他账号信息修改功能正在开发中。',
  },
  {
    key: '6',
    label: '忘记密码怎么办？',
    children: '目前密码找回功能正在开发中。如果你遇到登录问题，请联系客服获取帮助。建议使用常用邮箱注册，以便后续找回密码。',
  },
  {
    key: '7',
    label: '面试数据是否安全？',
    children: '我们非常重视你的数据安全。所有面试数据均采用加密传输和存储，不会未经授权分享给第三方。你可以随时在设置中清除本地缓存数据。',
  },
  {
    key: '8',
    label: '如何反馈问题或建议？',
    children: '你可以通过以下方式联系我们：发送邮件至 interview-coach@example.com，或在社区中发布反馈帖子。我们会在 1-2 个工作日内回复。',
  },
];

const HelpPage = () => {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();

  return (
    <div className="max-w-[800px]">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/dashboard/profile')}
          className="w-9 h-9 rounded-lg border border-[#E8E8E8] flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
        >
          <ArrowLeftOutlined />
        </button>
        <h1 className="text-xl font-bold text-[#232529]">帮助与反馈</h1>
      </div>

      <div className="bg-white border border-[#E8E8E8] rounded-2xl p-8 mb-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-[#00BFA5]" />
        <div className="relative">
          <h2 className="text-xl font-bold text-[#232529] mb-2">需要帮助？</h2>
          <p className="text-sm text-[#666666] mb-4">我们随时为你提供支持</p>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => msg.info('在线客服功能即将上线')}
              className="btn-flame !py-2 !px-4 !text-sm"
            >
              <MessageOutlined /> 在线客服
            </button>
            <button
              onClick={() => msg.info('已复制邮箱地址')}
              className="btn-ghost btn-ghost-lg !py-2 !px-4 !text-sm !text-white !border-white/20 hover:!border-white/50"
            >
              <MailOutlined /> interview-coach@example.com
            </button>
          </div>
        </div>
      </div>

      <div className="mb-6">
        <h2 className="text-base font-bold text-[#232529] mb-4 flex items-center gap-2">
          <QuestionCircleOutlined className="text-[#00BFA5]" />
          常见问题
        </h2>
        <div className="bg-white border border-[#E8E8E8] rounded-2xl overflow-hidden">
          <Collapse
            ghost
            expandIconPosition="end"
            items={FAQ_ITEMS.map((item) => ({
              key: item.key,
              label: <span className="text-sm font-semibold text-[#232529]">{item.label}</span>,
              children: <p className="text-sm text-[#666666] leading-relaxed">{item.children}</p>,
            }))}
            className="!bg-transparent [&_.ant-collapse-item]:!border-b [&_.ant-collapse-item]:!border-[#F2F3F5] [&_.ant-collapse-item:last-child]:!border-b-0 [&_.ant-collapse-header]:!px-6 [&_.ant-collapse-content-box]:!px-6 [&_.ant-collapse-content-box]:!pb-5"
          />
        </div>
      </div>

      <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6 text-center">
        <p className="text-sm text-[#666666] mb-2">没有找到答案？</p>
        <button
          onClick={() => msg.info('提交反馈功能即将上线')}
          className="btn-flame"
        >
          提交反馈
        </button>
      </div>
    </div>
  );
};

export default HelpPage;