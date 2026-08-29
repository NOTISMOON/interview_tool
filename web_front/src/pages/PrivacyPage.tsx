import { useNavigate } from 'react-router-dom';
import { ArrowLeftOutlined } from '@/components/icons';

const SECTIONS = [
  {
    title: '一、信息收集',
    content: '当您注册账户时，我们收集您的电子邮箱地址和昵称。当您使用面试功能时，我们收集您上传的简历文件内容，用于生成面试题目。我们不会收集超出功能所需的额外个人信息。',
  },
  {
    title: '二、信息使用',
    content: '我们使用收集的信息来提供、维护和改进我们的服务。具体包括：根据您的简历内容生成个性化面试题目；提供面试评估报告和改进建议；优化社区内容推荐算法；向您发送与服务相关的重要通知。',
  },
  {
    title: '三、信息存储',
    content: '您的数据存储在安全的云服务器上，采用行业标准的加密技术进行保护。我们采取合理的技术和管理措施，防止数据被未经授权访问、使用或泄露。',
  },
  {
    title: '四、信息共享',
    content: '我们不会将您的个人信息出售给第三方。在以下情况下，我们可能会共享您的信息：获得您的明确同意；法律法规要求；保护我们或他人的权利、财产或安全所需。',
  },
  {
    title: '五、Cookie 使用',
    content: '我们使用 Cookie 和类似技术来保持您的登录状态、记住您的偏好设置，以及分析网站使用情况。您可以在浏览器设置中管理 Cookie 偏好，但这可能影响部分功能的正常使用。',
  },
  {
    title: '六、数据安全',
    content: '我们采用传输层安全协议（TLS）加密所有数据传输。存储的数据使用 AES-256 加密算法进行保护。我们定期进行安全审计和漏洞扫描，确保系统安全。',
  },
  {
    title: '七、用户权利',
    content: '您有权访问、更正或删除您的个人信息。您可以在「个人设置」中修改昵称和头像，在「设置」中管理通知偏好。如需彻底删除账户，请使用设置中的注销账号功能。',
  },
  {
    title: '八、隐私政策更新',
    content: '我们可能会不时更新本隐私政策。更新后的政策将在本页面发布，并在重大变更时通过邮件或站内通知告知您。建议您定期查阅本页面了解最新信息。',
  },
  {
    title: '九、联系我们',
    content: '如果您对隐私政策有任何疑问或建议，请通过以下方式联系我们：发送邮件至 interview-coach@example.com，或在「帮助与反馈」页面提交反馈。',
  },
];

const PrivacyPage = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F7F8FA]">
      <div className="max-w-[800px] mx-auto px-6 py-8">
        <nav className="flex items-center gap-4 mb-8">
          <button
            onClick={() => navigate(-1)}
            className="w-9 h-9 rounded-lg border border-[#E8E8E8] bg-white flex items-center justify-center text-[#666666] hover:text-[#232529] hover:border-[#232529] transition-colors"
          >
            <ArrowLeftOutlined />
          </button>
          <h1 className="text-xl font-bold text-[#232529]">隐私政策</h1>
        </nav>

        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6 mb-8">
          <p className="text-sm text-[#666666] leading-relaxed mb-4">
            <strong className="text-[#232529]">最后更新日期：2026 年 8 月 10 日</strong>
          </p>
          <p className="text-sm text-[#666666] leading-relaxed">
            AI 超级面试（"我们"）非常重视您的隐私。本隐私政策说明了我们如何收集、使用、存储和保护您的个人信息。使用我们的服务即表示您同意本政策中描述的做法。
          </p>
        </div>

        <div className="space-y-4">
          {SECTIONS.map((section) => (
            <div key={section.title} className="bg-white border border-[#E8E8E8] rounded-2xl p-6">
              <h2 className="text-base font-bold text-[#232529] mb-3">{section.title}</h2>
              <p className="text-sm text-[#666666] leading-relaxed">{section.content}</p>
            </div>
          ))}
        </div>

        <div className="bg-white border border-[#E8E8E8] rounded-2xl p-6 mt-4 text-center">
          <p className="text-sm text-[#666666]">
            如有疑问，请联系{' '}
            <span className="text-[#D9A441] font-medium">interview-coach@example.com</span>
          </p>
        </div>

        <p className="text-center text-xs text-[#999999] mt-8">AI 超级面试 v1.0.0</p>
      </div>
    </div>
  );
};

export default PrivacyPage;