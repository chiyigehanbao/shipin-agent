import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App.jsx'
import './styles/global.css'

// 应用入口：路由 + Ant Design 中文 + 日光片场浅色主题
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ConfigProvider
        locale={zhCN}
        theme={{
          token: {
            colorPrimary: '#e94560',
            colorInfo: '#0891b2',
            colorSuccess: '#10b981',
            colorWarning: '#f59e0b',
            colorError: '#ef4444',
            borderRadius: 10,
            colorBgBase: '#f3f5f8',
            colorBgContainer: '#ffffff',
            colorBgElevated: '#ffffff',
            colorBgLayout: '#f3f5f8',
            colorText: '#1a2332',
            colorTextSecondary: '#5a6577',
            colorTextTertiary: '#8b95a5',
            colorBorder: '#e2e8f0',
            colorBorderSecondary: '#eef2f6',
            fontFamily:
              "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
            controlHeight: 36,
          },
          components: {
            Layout: {
              headerBg: 'rgba(255,255,255,0.82)',
              bodyBg: 'transparent',
              siderBg: '#ffffff',
            },
            Menu: {
              itemBg: 'transparent',
              horizontalItemSelectedColor: '#e94560',
              itemSelectedColor: '#e94560',
              itemSelectedBg: 'rgba(233, 69, 96, 0.1)',
            },
            Card: {
              colorBgContainer: '#ffffff',
            },
            Button: {
              primaryShadow: '0 6px 16px rgba(233, 69, 96, 0.25)',
            },
          },
        }}
      >
        <App />
      </ConfigProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
