import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Form, Input, Button, App } from 'antd';
import { MailOutlined, LockOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useAppStore } from '@/store';
import type { LoginForm } from '@/types';

const LoginPage = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { message } = App.useApp();
  const login = useAppStore((s) => s.login);

  const handleSubmit = async (values: LoginForm) => {
    setLoading(true);
    try {
      await login(values.email, values.password);
      message.success('登录成功');
      navigate('/dashboard', { replace: true });
    } catch {
      message.error('登录失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F6F8FA] flex">
      <div className="hidden lg:flex flex-1 bg-[#0D1117] items-center justify-center relative overflow-hidden">
        <div className="absolute top-20 left-20 w-96 h-96 bg-[#FF6B35]/10 rounded-full blur-3xl" />
        <div className="absolute bottom-20 right-20 w-80 h-80 bg-[#FF6B35]/5 rounded-full blur-3xl" />
        <div className="relative max-w-md text-center">
          <div className="w-20 h-20 rounded-2xl bg-[#FF6B35] flex items-center justify-center text-3xl mx-auto mb-6">
            AI
          </div>
          <h2 className="text-3xl font-extrabold text-white mb-4">AI 面试教练</h2>
          <p className="text-lg text-white/60 leading-relaxed">
            智能模拟面试，精准分析报告。
            <br />
            让每一次练习，都离 offer 更近一步。
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center px-8">
        <div className="w-full max-w-[400px]">
          <Link to="/" className="inline-flex items-center gap-2 text-sm text-[#5F6B7A] hover:text-[#0D1117] mb-10 transition-colors">
            <ArrowLeftOutlined /> 返回首页
          </Link>

          <h1 className="text-2xl font-extrabold text-[#0D1117] mb-2">欢迎回来</h1>
          <p className="text-sm text-[#5F6B7A] mb-8">登录你的账号，继续面试练习</p>

          <Form
            layout="vertical"
            onFinish={handleSubmit}
            autoComplete="off"
            size="large"
            initialValues={{ email: 'demo@example.com', password: '123456' }}
          >
            <Form.Item
              name="email"
              rules={[{ required: true, message: '请输入邮箱地址' }, { type: 'email', message: '请输入有效的邮箱地址' }]}
            >
              <Input prefix={<MailOutlined className="text-[#8B949E]" />} placeholder="邮箱地址" className="!rounded-xl !h-11" />
            </Form.Item>

            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined className="text-[#8B949E]" />} placeholder="密码" className="!rounded-xl !h-11" />
            </Form.Item>

            <Form.Item className="mb-6">
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                className="!h-11 !rounded-xl !font-semibold !text-base !border-none"
                style={{ background: '#FF6B35', boxShadow: '0 4px 16px rgba(255,107,53,0.25)' }}
              >
                登录
              </Button>
            </Form.Item>
          </Form>

          <div className="text-center">
            <span className="text-sm text-[#5F6B7A]">还没有账号？</span>
            <Link to="/register" className="text-sm text-[#FF6B35] font-semibold ml-1 hover:text-[#E85D26] transition-colors">
              立即注册
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;