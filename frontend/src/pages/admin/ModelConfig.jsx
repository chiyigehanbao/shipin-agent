import React, { useEffect, useState } from 'react'
import { modelsApi, settingsApi, ttsApi } from '../../services/api.js'
import {
  Card,
  Button,
  Input,
  Select,
  Tabs,
  InputNumber,
  Slider,
  Switch,
  Space,
  Typography,
  Divider,
  message,
  Tag,
} from 'antd'
import {
  ExperimentOutlined,
  ThunderboltOutlined,
  SaveOutlined,
  ReloadOutlined,
  ApiOutlined,
  SoundOutlined,
  BulbOutlined,
} from '@ant-design/icons'

const { Option } = Select
const { Title, Text } = Typography

const SD_MODEL_KEYS = ['flux']
const SD_MODEL_OPTIONS = {
  flux: 'Flux GGUF · 1024×1024（默认 · 高质量）',
}

// 模型参数配置页面
// 四个 Tab：SD/Flux、LTX/Wan2.2、LLM、TTS
function ModelConfig() {
  // 当前 Tab
  const [activeTab, setActiveTab] = useState('sd')

  const [connectionStatus, setConnectionStatus] = useState({
    sd: 'offline',
    ltx: 'offline',
    llm: 'offline',
    tts: 'offline',
  })
  const [services, setServices] = useState([])
  const [readiness, setReadiness] = useState({})
  const [testing, setTesting] = useState(null) // serviceId | null
  const [sdApiUrl, setSdApiUrl] = useState('http://127.0.0.1:8000')
  const [sdModel, setSdModel] = useState('flux')

  const [ollamaBaseUrl, setOllamaBaseUrl] = useState('http://127.0.0.1:11434')
  const [ollamaModel, setOllamaModel] = useState('qwen2.5:7b')
  const [ollamaModels, setOllamaModels] = useState([])
  const [cloudBaseUrl, setCloudBaseUrl] = useState('')
  const [cloudApiKey, setCloudApiKey] = useState('')
  const [cloudModel, setCloudModel] = useState('gpt-4o-mini')
  const [llmTimeoutSec, setLlmTimeoutSec] = useState(60)
  const [apiKeySet, setApiKeySet] = useState(false)
  const [apiKeyMasked, setApiKeyMasked] = useState('')
  const [llmSaving, setLlmSaving] = useState(false)
  const [sdQueue, setSdQueue] = useState(0)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [list, ready, llm] = await Promise.all([
          modelsApi.services(),
          modelsApi.readiness(),
          settingsApi.getLlm(),
        ])
        if (cancelled) return
        setServices(list)
        setReadiness(ready.models || {})
        const map = { sd: 'offline', ltx: 'offline', llm: 'offline', tts: 'offline' }
        for (const s of list) {
          if (s.id === 'sd') {
            map.sd = s.status || 'offline'
          }
        }
        map.llm = llm.api_key_set || llm.ollama_base_url ? 'online' : 'offline'
        setConnectionStatus(map)
        const sd = list.find((s) => s.id === 'sd')
        if (sd?.api_url) setSdApiUrl(sd.api_url)
        if (sd?.queue != null) setSdQueue(sd.queue)
        setOllamaBaseUrl(llm.ollama_base_url || '')
        setOllamaModel(llm.ollama_model || '')
        setCloudBaseUrl(llm.cloud_llm_base_url || '')
        setCloudModel(llm.cloud_llm_model || '')
        setLlmTimeoutSec(Number(llm.llm_timeout_sec) || 60)
        setApiKeySet(Boolean(llm.api_key_set))
        setApiKeyMasked(llm.cloud_llm_api_key_masked || '')
        settingsApi.listOllamaModels().then((tags) => {
          if (!cancelled) setOllamaModels((tags.models || []).map((m) => m.name).filter(Boolean))
        }).catch(() => {})
      } catch (e) {
        message.error(`加载模型服务失败: ${e.message}`)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const handleTestConnection = async (serviceId) => {
    if (serviceId === 'ltx') {
      message.info('视频生成能力尚未真实接入')
      return
    }
    if (serviceId === 'tts') {
      setTesting('tts')
      try {
        const engine = 'edge'
        const res = await ttsApi.test(engine)
        setConnectionStatus((prev) => ({ ...prev, tts: 'online' }))
        message.success(`TTS 测试成功（${res.engine}，${res.bytes} bytes）`)
      } catch (e) {
        setConnectionStatus((prev) => ({ ...prev, tts: 'offline' }))
        message.error(`TTS 测试失败: ${e.message}`)
      } finally {
        setTesting(null)
      }
      return
    }
    if (serviceId === 'llm') {
      setTesting('llm')
      try {
        const res = await settingsApi.testLlm()
        setConnectionStatus((prev) => ({ ...prev, llm: 'online' }))
        message.success(`连接成功（${res.provider}）: ${res.sample || 'OK'}`)
      } catch (e) {
        setConnectionStatus((prev) => ({ ...prev, llm: 'offline' }))
        message.error(`测试失败: ${e.message}`)
      } finally {
        setTesting(null)
      }
      return
    }

    setTesting(serviceId)
    try {
      const res = await modelsApi.testConnection(serviceId)
      const ok = res.status === 'success'
      setConnectionStatus((prev) => ({ ...prev, [serviceId]: ok ? 'online' : 'offline' }))
      if (ok) message.success(res.message || '连接成功')
      else message.error(res.message || '连接失败')
    } catch (e) {
      setConnectionStatus((prev) => ({ ...prev, [serviceId]: 'offline' }))
      message.error(`测试失败: ${e.message}`)
    } finally {
      setTesting(null)
    }
  }

  // 保存配置
  const handleSave = async () => {
    if (activeTab === 'sd' || activeTab === 'image') {
      try {
        const res = await modelsApi.updateConfig('sd', { api_url: sdApiUrl })
        if (res.api_url) setSdApiUrl(res.api_url)
        message.success(
          res.online
            ? `ComfyUI 地址已保存并在线：${res.api_url}`
            : `ComfyUI 地址已保存：${res.api_url || sdApiUrl}（当前探活未通，请确认端口）`,
        )
      } catch (e) {
        message.error(`保存失败: ${e.message}`)
      }
      return
    }
    if (activeTab !== 'llm') {
      message.info('当前 Tab 参数为演示控件（未接入后端），无需保存')
      return
    }
    setLlmSaving(true)
    try {
      const payload = {
        ollama_base_url: ollamaBaseUrl,
        ollama_model: ollamaModel,
        cloud_llm_base_url: cloudBaseUrl,
        cloud_llm_model: cloudModel,
        llm_timeout_sec: llmTimeoutSec,
      }
      if (cloudApiKey) payload.cloud_llm_api_key = cloudApiKey
      const cfg = await settingsApi.putLlm(payload)
      setApiKeySet(Boolean(cfg.api_key_set))
      setApiKeyMasked(cfg.cloud_llm_api_key_masked || '')
      setCloudApiKey('')
      message.success('LLM 配置已保存')
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    } finally {
      setLlmSaving(false)
    }
  }

  // 恢复默认
  const handleReset = () => {
    message.info('已恢复默认配置')
  }

  // Tab 配置
  const tabItems = [
    {
      key: 'sd',
      label: (
        <span>
          <ExperimentOutlined /> SD / Flux 图像
        </span>
      ),
    },
    {
      key: 'ltx',
      label: (
        <span>
          <ThunderboltOutlined /> LTX / Wan2.2 视频
        </span>
      ),
    },
    {
      key: 'llm',
      label: (
        <span>
          <BulbOutlined /> LLM 大脑
        </span>
      ),
    },
    {
      key: 'tts',
      label: (
        <span>
          <SoundOutlined /> TTS 配音
        </span>
      ),
    },
  ]

  // 状态指示
  const StatusBadge = ({ status }) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
      <span className={`status-dot ${status === 'online' ? 'green' : status === 'busy' ? 'yellow' : 'red'}`}></span>
      <span style={{ fontSize: '12px', color: status === 'online' ? '#10b981' : status === 'busy' ? '#ffaa00' : '#ff4444' }}>
        {status === 'online' ? '在线' : status === 'busy' ? '繁忙' : '离线'}
      </span>
    </span>
  )

  return (
    <div>
      {/* 页面标题 */}
      <div className="bilingual-title" style={{ marginBottom: '20px' }}>
        <span className="cn" style={{ fontSize: '20px', fontWeight: 700 }}>
          模型参数配置
        </span>
        <span className="en">Model Configuration</span>
      </div>

      {/* Tab 切换 */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        style={{ marginBottom: '16px' }}
      />

      {/* ===== SD/Flux 图像模型 ===== */}
      {activeTab === 'sd' && (
        <div style={{ display: 'flex', gap: '16px' }}>
          {/* 左栏：连接设置 */}
          <Card
            style={{
              flex: '0 0 350px',
              background: 'var(--vf-surface)',
              border: '1px solid var(--vf-border)',
              borderRadius: '8px',
            }}
            title={
              <div className="bilingual-title">
                <span className="cn" style={{ fontSize: '15px' }}>
                  🔌 连接设置
                </span>
                <span className="en">Connection</span>
              </div>
            }
          >
            {/* 服务状态 */}
            <div
              style={{
                padding: '12px',
                background: 'var(--vf-surface-muted)',
                borderRadius: '6px',
                marginBottom: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                  服务状态
                </div>
                <StatusBadge status={connectionStatus.sd} />
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                  GPU 占用
                </div>
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#10b981' }}>
                  见监控
                </span>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                  队列
                </div>
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#ffaa00' }}>
                  {sdQueue}
                </span>
              </div>
            </div>

            {/* API 地址 */}
            <div style={{ marginBottom: '12px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>API 地址</Text>
              <Input value={sdApiUrl} onChange={(e) => setSdApiUrl(e.target.value)} style={{ marginTop: '4px' }} />
            </div>

            {/* API 密钥 */}
            <div style={{ marginBottom: '12px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>API 密钥</Text>
              <Input.Password defaultValue="sk-xxxxxxxxxx" style={{ marginTop: '4px' }} />
            </div>

            {/* 模型选择 */}
            <div style={{ marginBottom: '16px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>默认模型</Text>
              <Select value={sdModel} onChange={setSdModel} style={{ width: '100%', marginTop: '4px' }}>
                {SD_MODEL_KEYS.map((id) => {
                  const info = readiness[id] || { ready: false, missing_files: ['状态未知'] }
                  const label = SD_MODEL_OPTIONS[id] + (info.ready ? '' : '（未就绪）')
                  return (
                    <Option
                      key={id}
                      value={id}
                      disabled={!info.ready}
                      title={!info.ready ? `缺少: ${info.missing_files.join(', ')}` : undefined}
                    >
                      {label}
                    </Option>
                  )
                })}
              </Select>
            </div>

            <Button
              type="primary"
              icon={<ApiOutlined />}
              onClick={() => handleTestConnection('sd')}
              loading={testing === 'sd'}
              block
              style={{ background: '#0891b2', borderColor: '#0891b2' }}
            >
              测试连接
            </Button>
          </Card>

          {/* 右栏：参数设置 */}
          <Card
            style={{
              flex: 1,
              background: 'var(--vf-surface)',
              border: '1px solid var(--vf-border)',
              borderRadius: '8px',
            }}
            title={
              <div className="bilingual-title">
                <span className="cn" style={{ fontSize: '15px' }}>
                  ⚙️ 默认生成参数
                </span>
                <span className="en">Default Parameters</span>
              </div>
            }
          >
            <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px', display: 'block', marginBottom: '12px' }}>
              ⚠️ 以下参数为演示控件，未接入后端（实际出图用资产页 Flux 工作流配置），保存按钮仅保存上方 ComfyUI 地址
            </Text>
            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>采样步数</Text>
                <InputNumber defaultValue={30} min={1} max={100} style={{ width: '100%', marginTop: '4px' }} />
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>CFG Scale</Text>
                <InputNumber defaultValue={7.5} min={1} max={20} step={0.5} style={{ width: '100%', marginTop: '4px' }} />
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>采样器</Text>
                <Select defaultValue="dpmpp_2m" style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="dpmpp_2m">DPM++ 2M Karras</Option>
                  <Option value="euler">Euler a</Option>
                  <Option value="ddim">DDIM</Option>
                </Select>
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>默认分辨率</Text>
                <Select defaultValue="1024x1024" style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="512x512">512 × 512</Option>
                  <Option value="768x768">768 × 768</Option>
                  <Option value="1024x1024">1024 × 1024</Option>
                  <Option value="1024x768">1024 × 768</Option>
                </Select>
              </div>
            </div>

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '20px 0' }} />

            <Title level={5} style={{ color: 'var(--vf-text)', marginBottom: '12px' }}>
              高级设置 / Advanced
            </Title>

            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>VAE</Text>
                <Select defaultValue="auto" style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="auto">自动</Option>
                  <Option value="kl-f8">kl-f8-anime</Option>
                </Select>
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>LoRA 模型</Text>
                <Select mode="multiple" placeholder="选择 LoRA" style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="xianxia">修真风格</Option>
                  <Option value="cyberpunk">赛博朋克</Option>
                  <Option value="ink">水墨风</Option>
                </Select>
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>ControlNet</Text>
                <Select defaultValue="none" style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="none">关闭</Option>
                  <Option value="canny">Canny 边缘</Option>
                  <Option value="depth">深度图</Option>
                  <Option value="pose">姿态控制</Option>
                </Select>
              </div>
            </div>

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '20px 0' }} />

            {/* 预设切换 */}
            <div style={{ marginBottom: '16px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>快速预设</Text>
              <div style={{ marginTop: '8px' }}>
                <Space>
                  <Tag color="green" style={{ cursor: 'pointer', padding: '6px 12px' }}>
                    ⚡ 快速生成
                  </Tag>
                  <Tag color="blue" style={{ cursor: 'pointer', padding: '6px 12px' }}>
                    🎨 高质量
                  </Tag>
                  <Tag color="purple" style={{ cursor: 'pointer', padding: '6px 12px' }}>
                    🖼️ 艺术风格
                  </Tag>
                </Space>
              </div>
            </div>

            {/* 底部按钮 */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>恢复默认</Button>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                style={{ background: '#e94560', borderColor: '#e94560' }}
              >
                保存为默认
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* ===== LTX/Wan2.2 视频模型 ===== */}
      {activeTab === 'ltx' && (
        <div style={{ display: 'flex', gap: '16px' }}>
          <Card
            style={{
              flex: '0 0 350px',
              background: 'var(--vf-surface)',
              border: '1px solid var(--vf-border)',
              borderRadius: '8px',
            }}
            title={
              <div className="bilingual-title">
                <span className="cn" style={{ fontSize: '15px' }}>
                  🔌 连接设置
                </span>
                <span className="en">Connection</span>
              </div>
            }
          >
            <div
              style={{
                padding: '12px',
                background: 'var(--vf-surface-muted)',
                borderRadius: '6px',
                marginBottom: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                  服务状态
                </div>
                <StatusBadge status={connectionStatus.ltx} />
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                  GPU 占用
                </div>
                <span style={{ fontSize: '14px', fontWeight: 600, color: '#ffaa00' }}>
                  未接入
                </span>
              </div>
            </div>

            <div style={{ marginBottom: '12px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>视频模型</Text>
              <Select defaultValue="wan2.2" style={{ width: '100%', marginTop: '4px' }}>
                <Option value="wan2.2">Wan2.2</Option>
                <Option value="ltx">LTX Video</Option>
                <Option value="cogvideox">CogVideoX</Option>
              </Select>
            </div>

            <div style={{ marginBottom: '12px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>API 地址</Text>
              <Input defaultValue="http://127.0.0.1:8000" style={{ marginTop: '4px' }} />
            </div>

            <div style={{ marginBottom: '16px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>API 密钥</Text>
              <Input.Password defaultValue="sk-xxxxxxxxxx" style={{ marginTop: '4px' }} />
            </div>

            <Button
              type="primary"
              icon={<ApiOutlined />}
              onClick={() => handleTestConnection('ltx')}
              loading={testing === 'ltx'}
              block
              style={{ background: '#0891b2', borderColor: '#0891b2' }}
            >
              测试连接
            </Button>
          </Card>

          <Card
            style={{
              flex: 1,
              background: 'var(--vf-surface)',
              border: '1px solid var(--vf-border)',
              borderRadius: '8px',
            }}
            title={
              <div className="bilingual-title">
                <span className="cn" style={{ fontSize: '15px' }}>
                  ⚙️ 视频生成参数
                </span>
                <span className="en">Video Parameters</span>
              </div>
            }
          >
            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>默认时长（秒）</Text>
                <InputNumber defaultValue={5} min={1} max={30} style={{ width: '100%', marginTop: '4px' }} />
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>帧率</Text>
                <Select defaultValue="24" style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="16">16 fps</Option>
                  <Option value="24">24 fps</Option>
                  <Option value="30">30 fps</Option>
                </Select>
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>运动强度</Text>
                <Slider defaultValue={5} min={1} max={10} style={{ marginTop: '8px' }} />
              </div>
              <div style={{ flex: '1 1 200px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>分辨率</Text>
                <Select defaultValue="720p" style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="480p">480p</Option>
                  <Option value="720p">720p</Option>
                  <Option value="1080p">1080p</Option>
                </Select>
              </div>
            </div>

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '20px 0' }} />

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontSize: '13px', color: 'var(--vf-text-secondary)' }}>帧间平滑</span>
              <Switch defaultChecked />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontSize: '13px', color: 'var(--vf-text-secondary)' }}>首尾帧一致性增强</span>
              <Switch defaultChecked />
            </div>

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '20px 0' }} />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>恢复默认</Button>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                style={{ background: '#e94560', borderColor: '#e94560' }}
              >
                保存为默认
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* ===== LLM 大脑 ===== */}
      {activeTab === 'llm' && (
        <Card
          style={{
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          title={
            <div className="bilingual-title">
              <span className="cn" style={{ fontSize: '15px' }}>
                🧠 LLM 大脑配置
              </span>
              <span className="en">LLM Brain Config</span>
            </div>
          }
        >
          <div
            style={{
              padding: '12px',
              background: 'var(--vf-surface-muted)',
              borderRadius: '6px',
              marginBottom: '20px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              maxWidth: '500px',
            }}
          >
            <div>
              <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                服务状态
              </div>
              <StatusBadge status={connectionStatus.llm} />
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                当前模型
              </div>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#0891b2' }}>
                {ollamaModel || cloudModel || '未配置'}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', maxWidth: '800px' }}>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>Ollama 地址</Text>
              <Input
                value={ollamaBaseUrl}
                onChange={(e) => setOllamaBaseUrl(e.target.value)}
                style={{ marginTop: '4px' }}
              />
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>Ollama 模型</Text>
              <Select
                showSearch
                value={ollamaModel || undefined}
                onChange={setOllamaModel}
                onSearch={(v) => setOllamaModel(v)}
                placeholder="本机模型"
                style={{ width: '100%', marginTop: '4px' }}
                options={ollamaModels.map((n) => ({ value: n, label: n }))}
              />
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>云端 API 地址</Text>
              <Input
                value={cloudBaseUrl}
                onChange={(e) => setCloudBaseUrl(e.target.value)}
                placeholder="https://api.openai.com/v1"
                style={{ marginTop: '4px' }}
              />
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>
                云端 API 密钥{apiKeySet ? `（已配置 ${apiKeyMasked}）` : ''}
              </Text>
              <Input.Password
                value={cloudApiKey}
                onChange={(e) => setCloudApiKey(e.target.value)}
                placeholder={apiKeySet ? '留空则不修改' : 'sk-...'}
                style={{ marginTop: '4px' }}
              />
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>云端模型</Text>
              <Input
                value={cloudModel}
                onChange={(e) => setCloudModel(e.target.value)}
                style={{ marginTop: '4px' }}
              />
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>超时（秒）</Text>
              <InputNumber
                value={llmTimeoutSec}
                onChange={(v) => setLlmTimeoutSec(v || 60)}
                min={5}
                max={600}
                style={{ width: '100%', marginTop: '4px' }}
              />
            </div>
          </div>

          <Divider style={{ borderColor: 'var(--vf-border)', margin: '20px 0' }} />
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 12 }}>
            多云端 Profiles 请在「系统设置」中新建/切换；本页保存会写入当前启用云端的地址与密钥。
          </Text>

          <div style={{ display: 'flex', gap: '12px' }}>
            <Button
              type="primary"
              icon={<ApiOutlined />}
              onClick={() => handleTestConnection('llm')}
              loading={testing === 'llm'}
              style={{ background: '#0891b2', borderColor: '#0891b2' }}
            >
              测试连接
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleReset}>恢复默认</Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSave}
              loading={llmSaving}
              style={{ background: '#e94560', borderColor: '#e94560' }}
            >
              保存配置
            </Button>
          </div>
        </Card>
      )}

      {/* ===== TTS 配音 ===== */}
      {activeTab === 'tts' && (
        <Card
          style={{
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          title={
            <div className="bilingual-title">
              <span className="cn" style={{ fontSize: '15px' }}>
                🔊 TTS 配音配置
              </span>
              <span className="en">TTS Voice Config</span>
            </div>
          }
        >
          <div
            style={{
              padding: '12px',
              background: 'var(--vf-surface-muted)',
              borderRadius: '6px',
              marginBottom: '20px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              maxWidth: '500px',
            }}
          >
            <div>
              <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                服务状态
              </div>
              <StatusBadge status={connectionStatus.tts} />
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '13px', color: 'var(--vf-text-secondary)', marginBottom: '4px' }}>
                可用音色
              </div>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#10b981' }}>
                24 种
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', maxWidth: '800px' }}>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>TTS 引擎</Text>
              <Select defaultValue="edge-tts" style={{ width: '100%', marginTop: '4px' }}>
                <Option value="edge-tts">Edge TTS (免费)</Option>
                <Option value="openai">OpenAI TTS</Option>
                <Option value="xtts">XTTS v2</Option>
                <Option value="cosyvoice">CosyVoice</Option>
              </Select>
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>API 地址</Text>
              <Input defaultValue="http://127.0.0.1:9000" style={{ marginTop: '4px' }} />
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>默认音色（男）</Text>
              <Select defaultValue="zh-CN-YunxiNeural" style={{ width: '100%', marginTop: '4px' }}>
                <Option value="zh-CN-YunxiNeural">云希 - 温和男声</Option>
                <Option value="zh-CN-YunyangNeural">云扬 - 沉稳男声</Option>
                <Option value="zh-CN-YunjianNeural">云健 - 低沉男声</Option>
              </Select>
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>默认音色（女）</Text>
              <Select defaultValue="zh-CN-XiaoxiaoNeural" style={{ width: '100%', marginTop: '4px' }}>
                <Option value="zh-CN-XiaoxiaoNeural">晓晓 - 清脆女声</Option>
                <Option value="zh-CN-XiaoyiNeural">晓伊 - 温柔女声</Option>
                <Option value="zh-CN-XiaohanNeural">晓涵 - 知性女声</Option>
              </Select>
            </div>
            <div style={{ flex: '1 1 300px' }}>
              <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>默认语速</Text>
              <Slider defaultValue={1.0} min={0.5} max={2} step={0.1} style={{ marginTop: '8px' }} />
            </div>
          </div>

          <Divider style={{ borderColor: 'var(--vf-border)', margin: '20px 0' }} />

          <div style={{ display: 'flex', gap: '12px' }}>
            <Button
              type="primary"
              icon={<ApiOutlined />}
              onClick={() => handleTestConnection('tts')}
              loading={testing === 'tts'}
              style={{ background: '#0891b2', borderColor: '#0891b2' }}
            >
              测试连接
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleReset}>恢复默认</Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSave}
              style={{ background: '#e94560', borderColor: '#e94560' }}
            >
              保存配置
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}

export default ModelConfig
