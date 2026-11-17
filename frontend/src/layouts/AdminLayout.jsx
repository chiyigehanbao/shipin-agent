import React from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  FileTextOutlined,
  BookOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons'

const { Sider, Content } = Layout

function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const getSelectedKey = () => {
    if (location.pathname.includes('/admin/prompts')) return 'prompts'
    if (location.pathname.includes('/admin/rag')) return 'rag'
    if (location.pathname.includes('/admin/models')) return 'models'
    if (location.pathname.includes('/admin/settings')) return 'settings'
    return 'prompts'
  }

  const menuItems = [
    {
      key: 'prompts',
      icon: <FileTextOutlined />,
      label: '提示词模板',
      onClick: () => navigate('/admin/prompts'),
    },
    {
      key: 'rag',
      icon: <BookOutlined />,
      label: 'RAG 知识库',
      onClick: () => navigate('/admin/rag'),
    },
    {
      key: 'models',
      icon: <ToolOutlined />,
      label: '模型配置',
      onClick: () => navigate('/admin/models'),
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '系统设置',
      onClick: () => navigate('/admin/settings'),
    },
  ]

  return (
    <Layout style={{ background: 'transparent', minHeight: 'calc(100vh - 64px - 48px)' }}>
      <Sider
        width={220}
        style={{
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: 16,
          marginRight: 18,
          paddingTop: 14,
          boxShadow: 'var(--vf-shadow-sm)',
        }}
      >
        <div
          style={{
            padding: '0 18px 14px',
            fontFamily: 'var(--vf-font-display)',
            fontSize: 11,
            color: 'var(--vf-text-muted)',
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
          }}
        >
          Admin Center
        </div>
        <Menu
          mode="inline"
          selectedKeys={[getSelectedKey()]}
          items={menuItems}
          style={{
            background: 'transparent',
            borderRight: 'none',
            padding: '0 8px 12px',
          }}
        />
      </Sider>

      <Content style={{ background: 'transparent' }}>
        <Outlet />
      </Content>
    </Layout>
  )
}

export default AdminLayout
