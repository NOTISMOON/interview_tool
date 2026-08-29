import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import ConfigProvider from 'antd/es/config-provider';
import AntApp from 'antd/es/app';
import zhCN from 'antd/es/locale/zh_CN';
import App from './App';
import { MessageVersionProvider } from '@/lib/messageVersion';
import "./styles/index.css";

const theme = {
  token: {
    colorPrimary: '#D9A441',
    colorInfo: '#D9A441',
    colorSuccess: '#00B578',
    colorWarning: '#FFAA00',
    colorError: '#F53535',
    borderRadius: 10,
    borderRadiusLG: 14,
    borderRadiusSM: 6,
    colorBgContainer: '#FFFFFF',
    colorBorder: '#E8E8E8',
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider theme={theme} locale={zhCN}>
      <AntApp>
        <BrowserRouter>
          <MessageVersionProvider>
            <App />
          </MessageVersionProvider>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);