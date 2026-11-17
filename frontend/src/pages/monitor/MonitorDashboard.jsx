import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Row,
  Col,
  Progress,
  Tag,
  Button,
  Space,
  Typography,
  message,
} from 'antd'
import {
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons'
import { monitorApi, modelsApi } from '../../services/api.js'

const { Text } = Typography

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return null
  return Math.round(Number(v))
}

function MonitorDashboard() {
  const navigate = useNavigate()
  const [snapshot, setSnapshot] = useState(null)
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [snap, svc] = await Promise.all([
        monitorApi.snapshot(),
        modelsApi.services().catch(() => []),
      ])
      setSnapshot(snap)
      setServices(svc || [])
    } catch (e) {
      message.error(`加载监控失败: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    let timer
    const tick = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const [snap, svc] = await Promise.all([
          monitorApi.snapshot(),
          modelsApi.services().catch(() => []),
        ])
        if (cancelled) return
        setSnapshot(snap)
        setServices(svc || [])
      } catch {
        /* keep last */
      }
    }
    tick()
    timer = setInterval(tick, 4000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const host = snapshot?.host || {}
  const gpu = snapshot?.gpu || {}
  const tasks = snapshot?.tasks || { generating: [], failed_recent: [], badge_count: 0 }
  const svcSnap = snapshot?.services || {}

  const cards = [
    { title: 'CPU', value: pct(host.cpu_percent), suffix: '%' },
    { title: '内存', value: pct(host.memory_percent), suffix: '%' },
    {
      title: 'GPU',
      value: gpu.available ? pct(gpu.utilization_percent) : null,
      suffix: '%',
      extra: gpu.available ? `${gpu.temperature_c}°C` : '不可用',
    },
    { title: '磁盘', value: pct(host.disk_percent), suffix: '%' },
  ]

  return (
    <div style={{ maxWidth: 1200 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 20,
        }}
      >
        <div className="bilingual-title">
          <span className="cn" style={{ fontSize: 20, fontWeight: 700 }}>
            监控面板
          </span>
          <span className="en">Monitor Dashboard</span>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
          刷新
        </Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {cards.map((c) => (
          <Col xs={24} sm={12} md={6} key={c.title}>
            <Card
              style={{
                background: 'var(--vf-surface)',
                border: '1px solid var(--vf-border)',
                borderRadius: 8,
              }}
            >
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: 13 }}>{c.title}</Text>
              <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--vf-text)', marginTop: 4 }}>
                {c.value == null ? '—' : `${c.value}${c.suffix}`}
              </div>
              {c.extra && (
                <div style={{ fontSize: 12, color: 'var(--vf-text-muted)', marginTop: 4 }}>
                  {c.extra}
                </div>
              )}
              {c.value != null && (
                <Progress
                  percent={c.value}
                  showInfo={false}
                  strokeColor="#0891b2"
                  style={{ marginTop: 8 }}
                />
              )}
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        style={{
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: 8,
          marginBottom: 16,
        }}
        title={
          <div className="bilingual-title">
            <span className="cn" style={{ fontSize: 15 }}>
              模型服务状态
            </span>
            <span className="en">Model Services</span>
          </div>
        }
      >
        <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--vf-text-secondary)' }}>
          ComfyUI:{' '}
          {svcSnap.comfyui?.online ? (
            <Tag color="success">在线 · 队列 {svcSnap.comfyui?.queue ?? 0}</Tag>
          ) : (
            <Tag>离线</Tag>
          )}
          Ollama:{' '}
          {svcSnap.ollama?.online ? (
            <Tag color="processing">{svcSnap.ollama?.model || 'online'}</Tag>
          ) : (
            <Tag>离线</Tag>
          )}
        </div>
        <Row gutter={[12, 12]}>
          {(services.length ? services : [{ id: 'sd', name: 'SD / Flux', status: 'offline', queue: 0 }]).map(
            (s) => (
              <Col xs={24} md={12} key={s.id}>
                <div
                  style={{
                    padding: 12,
                    background: 'var(--vf-surface-muted)',
                    borderRadius: 6,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontWeight: 600 }}>{s.name || s.id}</span>
                    {s.status === 'online' ? (
                      <Tag icon={<CheckCircleOutlined />} color="success">
                        online
                      </Tag>
                    ) : (
                      <Tag icon={<CloseCircleOutlined />}>offline</Tag>
                    )}
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, color: 'var(--vf-text-secondary)' }}>
                    队列 {s.queue ?? 0}
                    {s.id === 'sd' || s.id === 'flux' ? '' : ' · 视频能力尚未真实接入'}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12, color: 'var(--vf-text-muted)' }}>
                    GPU 占用见上方系统概览
                  </div>
                </div>
              </Col>
            ),
          )}
        </Row>
      </Card>

      <Card
        style={{
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: 8,
        }}
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="bilingual-title">
              <span className="cn" style={{ fontSize: 15 }}>
                实时任务队列
              </span>
              <span className="en">Task Queue</span>
            </div>
            <Tag>{tasks.badge_count || 0} 个关注中</Tag>
          </div>
        }
      >
        {[...(tasks.generating || []), ...(tasks.failed_recent || [])].length === 0 && (
          <Text type="secondary">暂无生成中或近期失败任务</Text>
        )}
        {[...(tasks.generating || []), ...(tasks.failed_recent || [])].map((t) => (
          <div
            key={`${t.status}-${t.id}`}
            style={{
              padding: '12px 0',
              borderBottom: '1px solid var(--vf-border)',
              display: 'flex',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div>
              <div style={{ fontWeight: 600 }}>{t.name}</div>
              <div style={{ fontSize: 12, color: 'var(--vf-text-secondary)' }}>
                {t.project_id} · {t.type} · {t.model}
              </div>
              {t.error && (
                <div style={{ fontSize: 12, color: '#e94560', marginTop: 4 }}>{t.error}</div>
              )}
            </div>
            <Space>
              <Tag color={t.status === 'generating' ? 'processing' : 'error'}>{t.status}</Tag>
              <Button
                size="small"
                onClick={() => navigate(`/workbench/${t.project_id}/assets`)}
              >
                打开
              </Button>
              <Button
                size="small"
                disabled
                title="尚未实现"
                onClick={() => message.info('任务暂停尚未实现')}
              >
                暂停
              </Button>
            </Space>
          </div>
        ))}
      </Card>
    </div>
  )
}

export default MonitorDashboard
