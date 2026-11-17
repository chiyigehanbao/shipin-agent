import React, { useEffect, useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Badge, Avatar, Space, Popover, Typography } from 'antd'
import {
  VideoCameraOutlined,
  SettingOutlined,
  DashboardOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { monitorApi } from '../services/api.js'
import ActiveJobsBar from '../components/ActiveJobsBar.jsx'

const { Header, Content } = Layout
const { Text } = Typography

function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden>
      <svg viewBox="0 0 24 24" fill="none">
        <rect x="3" y="5" width="18" height="14" rx="2.5" fill="white" fillOpacity="0.95" />
        <path d="M3 8.5h18" stroke="#e94560" strokeWidth="1.6" />
        <path
          d="M7 5V3.8a1 1 0 0 1 1-1h2.2a1 1 0 0 1 1 1V5"
          stroke="white"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        <path
          d="M12.8 5V3.8a1 1 0 0 1 1-1H16a1 1 0 0 1 1 1V5"
          stroke="white"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        <circle cx="9" cy="13.5" r="1.3" fill="#0891b2" />
        <circle cx="15" cy="13.5" r="1.3" fill="#e94560" />
      </svg>
    </div>
  )
}

function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [snapshot, setSnapshot] = useState(null)

  useEffect(() => {
    let cancelled = false
    let timer

    const tick = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const snap = await monitorApi.snapshot()
        if (!cancelled) setSnapshot(snap)
      } catch {
        /* keep last good snapshot; never fake 78% */
      }
    }

    tick()
    timer = setInterval(tick, 4000)
    const onVis = () => {
      if (document.visibilityState === 'visible') tick()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelled = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  const getSelectedKey = () => {
    if (location.pathname.startsWith('/workbench')) return 'workbench'
    if (location.pathname.startsWith('/admin')) return 'admin'
    if (location.pathname.startsWith('/monitor')) return 'monitor'
    return 'workbench'
  }

  const menuItems = [
    {
      key: 'workbench',
      icon: <VideoCameraOutlined />,
      label: '工作台',
      onClick: () => navigate('/workbench'),
    },
    {
      key: 'admin',
      icon: <SettingOutlined />,
      label: '管理中心',
      onClick: () => navigate('/admin/prompts'),
    },
    {
      key: 'monitor',
      icon: <DashboardOutlined />,
      label: '监控面板',
      onClick: () => navigate('/monitor'),
    },
  ]

  const gpu = snapshot?.gpu
  const gpuAvailable = Boolean(gpu?.available)
  const gpuLabel = gpuAvailable
    ? `${gpu.temperature_c}°C · ${gpu.utilization_percent}%`
    : snapshot
      ? 'GPU 不可用'
      : 'GPU …'
  const badgeCount = snapshot?.tasks?.badge_count ?? 0
  const generating = snapshot?.tasks?.generating || []
  const failed = snapshot?.tasks?.failed_recent || []

  const taskContent = (
    <div style={{ width: 280, maxHeight: 320, overflow: 'auto' }}>
      {!generating.length && !failed.length && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          暂无进行中或近期失败任务
        </Text>
      )}
      {generating.map((t) => (
        <div
          key={`g-${t.id}`}
          style={{ padding: '6px 0', cursor: 'pointer', borderBottom: '1px solid var(--vf-border)' }}
          onClick={() =>
            navigate(t.link_path || `/workbench/${t.project_id}/assets`)
          }
        >
          <div style={{ fontSize: 13, color: 'var(--vf-text)' }}>{t.name}</div>
          <div style={{ fontSize: 11, color: '#0891b2' }}>
            生成中 · {t.progress != null ? `${t.progress}% · ` : ''}
            {t.model || t.type}
          </div>
        </div>
      ))}
      {failed.map((t) => (
        <div
          key={`f-${t.id}`}
          style={{ padding: '6px 0', cursor: 'pointer', borderBottom: '1px solid var(--vf-border)' }}
          onClick={() =>
            navigate(t.link_path || `/workbench/${t.project_id}/assets`)
          }
        >
          <div style={{ fontSize: 13, color: 'var(--vf-text)' }}>{t.name}</div>
          <div style={{ fontSize: 11, color: '#e94560' }}>
            失败 · {(t.error || '').slice(0, 48) || 'unknown'}
          </div>
        </div>
      ))}
    </div>
  )

  return (
    <Layout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 28px',
          height: 64,
          position: 'sticky',
          top: 0,
          zIndex: 100,
          background: 'rgba(255,255,255,0.82)',
          borderBottom: '1px solid var(--vf-border)',
          backdropFilter: 'blur(14px)',
        }}
      >
        <div
          className="brand-lockup"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate('/')}
        >
          <BrandMark />
          <div className="brand-lockup__text">
            <span className="brand-lockup__cn">幻帧工坊</span>
            <span className="brand-lockup__en">VisionForge Studio</span>
          </div>
        </div>

        <Menu
          mode="horizontal"
          selectedKeys={[getSelectedKey()]}
          items={menuItems}
          style={{
            flex: 1,
            justifyContent: 'center',
            background: 'transparent',
            borderBottom: 'none',
            fontSize: 15,
            minWidth: 0,
          }}
        />

        <Space size="middle">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className={`status-dot ${gpuAvailable ? 'green' : 'red'}`} />
            <span style={{ fontSize: 13, color: 'var(--vf-text-secondary)', fontWeight: 500 }}>
              {gpuLabel}
            </span>
          </div>

          <Popover content={taskContent} title="任务提醒" trigger="click" placement="bottomRight">
            <Badge count={badgeCount} size="small" color="#e94560" overflowCount={99}>
              <span
                style={{
                  fontSize: 13,
                  color: 'var(--vf-text-secondary)',
                  fontWeight: 500,
                  paddingRight: 4,
                  cursor: 'pointer',
                }}
              >
                任务
              </span>
            </Badge>
          </Popover>

          <Avatar
            size={34}
            icon={<UserOutlined />}
            style={{
              background: 'linear-gradient(135deg, #e94560, #ff7a8a)',
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(233,69,96,0.25)',
            }}
          />
        </Space>
      </Header>

      <Content
        style={{
          padding: '28px 28px 88px',
          minHeight: 'calc(100vh - 64px)',
          background: 'transparent',
        }}
      >
        <ActiveJobsBar />
        <Outlet />
      </Content>
    </Layout>
  )
}

export default MainLayout
