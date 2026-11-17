import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Progress, Typography } from 'antd'
import { useJobTracker } from '../hooks/useJobTracker.js'

const { Text } = Typography

export default function ActiveJobsBar() {
  const { activeJobs } = useJobTracker(3000)
  const navigate = useNavigate()

  if (!activeJobs.length) return null

  const primary = activeJobs[0]
  const extra = activeJobs.length - 1

  return (
    <div
      role="status"
      onClick={() => primary.link_path && navigate(primary.link_path)}
      style={{
        marginBottom: 16,
        padding: '10px 14px',
        borderRadius: 8,
        border: '1px solid var(--vf-border)',
        background: 'var(--vf-surface)',
        cursor: primary.link_path ? 'pointer' : 'default',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <Text strong style={{ fontSize: 13 }}>
          进行中：{primary.title || primary.type}
          {extra > 0 ? ` 等 ${activeJobs.length} 项` : ''}
        </Text>
        <div style={{ fontSize: 12, color: 'var(--vf-text-secondary)' }}>
          {primary.status === 'queued' ? '排队中' : '生成中'}
          {primary.project_id ? ` · 项目 ${primary.project_id}` : ''}
        </div>
      </div>
      <div style={{ width: 120 }}>
        <Progress
          percent={Number(primary.progress) || (primary.status === 'running' ? 30 : 5)}
          size="small"
          status="active"
          strokeColor="#e94560"
        />
      </div>
    </div>
  )
}
