import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, App, Divider } from 'antd';
import { GithubOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { getGithubAuthUrl } from '@/lib/api/auth';

const LoginPage = () => {
  const [loading, setLoading] = useState(false);
  const { message } = App.useApp();

  const handleGithubLogin = async () => {
    setLoading(true);
    try {
      const { authorize_url } = await getGithubAuthUrl();
      window.location.href = authorize_url;
    } catch {
      message.error('获取授权地址失败，请重试');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F6F8FA] flex">
      <div className="hidden lg:flex flex-1 bg-[#0D1117] items-center justify-center relative overflow-hidden">
        <div className="absolute top-20 left-20 w-96 h-96 bg-[#FF6B35]/10 rounded-full blur-3xl" />
        <div className="absolute bottom-20 right-20 w-80 h-80 bg-[#FF6B35]/5 rounded-full blur-3xl" />
        <div className="absolute top-1/2 right-1/3 w-64 h-64 bg-[#2DA44E]/5 rounded-full blur-3xl" />
        <div className="relative max-w-md text-center">
          <div className="w-20 h-20 rounded-2xl bg-[#FF6B35] flex items-center justify-center text-3xl mx-auto mb-6">
            AI
          </div>
          <h2 className="text-3xl font-extrabold text-white mb-4">AI 面试平台</h2>
          <p className="text-lg text-white/60 leading-relaxed mb-10">
            智能模拟面试，精准分析报告。
            <br />
            让每一次练习，都离 offer 更近一步。
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center px-8">
        <div className="w-full max-w-[420px]">
          <Link to="/" className="inline-flex items-center gap-2 text-sm text-[#5F6B7A] hover:text-[#0D1117] mb-10 transition-colors">
            <ArrowLeftOutlined /> 返回首页
          </Link>

          <div className="mb-8">
            <h1 className="text-[28px] font-extrabold text-[#0D1117] mb-2">欢迎使用 AI 面试平台</h1>
          </div>

          <Button
            onClick={handleGithubLogin}
            loading={loading}
            block
            className="!h-12 !rounded-xl !font-semibold !text-base !flex !items-center !justify-center !gap-3 !mb-6"
            style={{
              background: '#24292F',
              borderColor: '#24292F',
              color: '#FFFFFF',
              boxShadow: '0 4px 16px rgba(36,41,47,0.3)',
            }}
            icon={<GithubOutlined style={{ fontSize: 22 }} />}
          >
            {loading ? '正在授权...' : '使用 GitHub 登录 / 注册'}
          </Button>

          <Divider className="!text-xs !text-[#8B949E] !mb-6">安全便捷的第三方登录</Divider>

          <p className="text-xs text-[#8B949E] text-center mt-8">
            登录即表示你同意我们的
            <Link to="/privacy" className="text-[#FF6B35] hover:underline mx-1">隐私政策</Link>
            和服务条款
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;