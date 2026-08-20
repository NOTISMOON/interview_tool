import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import ConfigProvider from 'antd/es/config-provider';
import AntApp from 'antd/es/app';
import zhCN from 'antd/es/locale/zh_CN';
import App from './App';
import "./styles/index.css";

const theme = {
  token: {
    colorPrimary: '#FF6B35',
    colorInfo: '#FF6B35',
    colorSuccess: '#2DA44E',
    colorWarning: '#BF8700',
    colorError: '#CF222E',
    borderRadius: 10,
    borderRadiusLG: 14,
    borderRadiusSM: 6,
    colorBgContainer: '#FFFFFF',
    colorBorder: '#E1E4E8',
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider theme={theme} locale={zhCN}>
      <AntApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);