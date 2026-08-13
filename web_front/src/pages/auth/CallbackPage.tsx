import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Spin, App } from 'antd';
import { useAppStore } from '@/store';

const CallbackPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const handleGithubCallback = useAppStore((s) => s.handleGithubCallback);
  const hasCalled = useRef(false);

  useEffect(() => {
    if (hasCalled.current) return;
    hasCalled.current = true;

    const code = searchParams.get('code');
    if (!code) {
      message.error('授权失败，未获取到授权码');
      navigate('/login', { replace: true });
      return;
    }

    handleGithubCallback(code)
      .then(() => {
        message.success('授权成功，欢迎回来');
        navigate('/dashboard', { replace: true });
      })
      .catch(() => {
        message.error('GitHub 授权失败，请重试');
        navigate('/login', { replace: true });
      });
  }, []);

  return (
    <div className="min-h-screen bg-[#F6F8FA] flex items-center justify-center">
      <Spin size="large" tip="正在登录..." />
    </div>
  );
};

export default CallbackPage;