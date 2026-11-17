import React, { useEffect, useState } from 'react'
import {
  Card,
  Button,
  Input,
  Select,
  InputNumber,
  Space,
  Typography,
  Divider,
  message,
} from 'antd'
import { settingsApi } from '../../services/api.js'

const { Option } = Select
const { Title, Text } = Typography

// 系统设置页面
// LLM配置、存储路径、并发控制、界面设置、日志数据
function SystemSettings() {
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState('http://127.0.0.1:11434')
  const [ollamaModel, setOllamaModel] = useState('qwen3.5:9b')
  const [ollamaModels, setOllamaModels] = useState([])
  const [llmTimeoutSec, setLlmTimeoutSec] = useState(60)
  const [activeCloudId, setActiveCloudId] = useState('deepseek')
  const [profiles, setProfiles] = useState([])
  const [paths, setPaths] = useState({ modelhub_root: '', outputs_dir: '', sqlite_path: '' })
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmTesting, setLlmTesting] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [cfg, p] = await Promise.all([
          settingsApi.getLlm(),
          settingsApi.getPaths().catch(() => null),
        ])
        if (cancelled) return
        setOllamaBaseUrl(cfg.ollama_base_url || '')
        setOllamaModel(cfg.ollama_model || '')
        setLlmTimeoutSec(Number(cfg.llm_timeout_sec) || 60)
        setActiveCloudId(cfg.active_cloud_id || 'deepseek')
        setProfiles(
          (cfg.cloud_profiles || []).map((x) => ({
            id: x.id,
            name: x.name || x.id,
            base_url: x.base_url || '',
            model: x.model || '',
            api_key: '',
            api_key_set: Boolean(x.api_key_set),
            api_key_masked: x.api_key_masked || '',
          })),
        )
        if (p) setPaths(p)
        const installed = Array.isArray(cfg.ollama_installed)
          ? cfg.ollama_installed.filter(Boolean)
          : []
        if (installed.length) {
          setOllamaModels(installed)
        } else {
          try {
            const tags = await settingsApi.listOllamaModels()
            if (!cancelled) setOllamaModels((tags.models || []).map((m) => m.name).filter(Boolean))
          } catch {
            /* allow manual model name */
          }
        }
        if (cfg.ollama_model_auto_fixed) {
          message.info(
            `本机未安装「${cfg.ollama_model_was}」，已自动切换为「${cfg.ollama_model}」`,
          )
        }
      } catch (e) {
        message.error(`加载 LLM 配置失败: ${e.message}`)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const handleSaveLlm = async () => {
    setLlmLoading(true)
    try {
      const payload = {
        ollama_base_url: ollamaBaseUrl,
        ollama_model: ollamaModel,
        llm_timeout_sec: llmTimeoutSec,
        active_cloud_id: activeCloudId,
        cloud_profiles: profiles.map((p) => ({
          id: p.id,
          name: p.name,
          base_url: p.base_url,
          model: p.model,
          api_key: p.api_key || '',
        })),
      }
      const cfg = await settingsApi.putLlm(payload)
      setActiveCloudId(cfg.active_cloud_id || activeCloudId)
      setProfiles(
        (cfg.cloud_profiles || []).map((x) => ({
          id: x.id,
          name: x.name || x.id,
          base_url: x.base_url || '',
          model: x.model || '',
          api_key: '',
          api_key_set: Boolean(x.api_key_set),
          api_key_masked: x.api_key_masked || '',
        })),
      )
      message.success('LLM 配置已保存')
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    } finally {
      setLlmLoading(false)
    }
  }

  const handleTestLlm = async () => {
    setLlmTesting(true)
    try {
      const res = await settingsApi.testLlm()
      message.success(`连接成功（${res.provider}）: ${res.sample || 'OK'}`)
    } catch (e) {
      message.error(`连接失败: ${e.message}`)
    } finally {
      setLlmTesting(false)
    }
  }

  const addProfile = () => {
    const id = `cloud_${Date.now().toString(36)}`
    setProfiles((prev) => [
      ...prev,
      { id, name: '新云端', base_url: '', model: '', api_key: '', api_key_set: false, api_key_masked: '' },
    ])
    setActiveCloudId(id)
  }

  const updateProfile = (id, patch) => {
    setProfiles((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p)))
  }

  const removeProfile = (id) => {
    setProfiles((prev) => prev.filter((p) => p.id !== id))
    if (activeCloudId === id) {
      setActiveCloudId((prev) => {
        const rest = profiles.filter((p) => p.id !== id)
        return rest[0]?.id || ''
      })
    }
  }

  return (
    <div style={{ maxWidth: '800px' }}>
      {/* 页面标题 */}
      <div className="bilingual-title" style={{ marginBottom: '20px' }}>
        <span className="cn" style={{ fontSize: '20px', fontWeight: 700 }}>
          系统设置
        </span>
        <span className="en">System Settings</span>
      </div>

      {/* ===== LLM 服务配置 ===== */}
      <Card
        style={{
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: '8px',
          marginBottom: '16px',
        }}
        title={
          <div className="bilingual-title">
            <span className="cn" style={{ fontSize: '16px' }}>
              🧠 LLM 服务配置
            </span>
            <span className="en">LLM Service</span>
          </div>
        }
      >
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
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
              placeholder="选择或输入本机模型名"
              style={{ width: '100%', marginTop: '4px' }}
              options={ollamaModels.map((n) => ({ value: n, label: n }))}
              allowClear
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
          <div style={{ flex: '1 1 300px' }}>
            <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>当前云端</Text>
            <Select
              value={activeCloudId || undefined}
              onChange={setActiveCloudId}
              style={{ width: '100%', marginTop: '4px' }}
              options={profiles.map((p) => ({ value: p.id, label: p.name || p.id }))}
            />
          </div>
        </div>

        <Divider style={{ borderColor: 'var(--vf-border)', margin: '16px 0' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <Text style={{ color: 'var(--vf-text-secondary)', fontSize: 12 }}>云端 Profiles（Ollama 优先，失败降级到当前启用）</Text>
          <Button size="small" onClick={addProfile}>
            新建
          </Button>
        </div>
        {profiles.map((p) => (
          <div
            key={p.id}
            style={{
              padding: 12,
              marginBottom: 8,
              background: 'var(--vf-surface-muted)',
              borderRadius: 6,
              border: p.id === activeCloudId ? '1px solid #0891b2' : '1px solid transparent',
            }}
          >
            <Space wrap style={{ width: '100%' }}>
              <Input
                style={{ width: 120 }}
                value={p.name}
                onChange={(e) => updateProfile(p.id, { name: e.target.value })}
                placeholder="名称"
              />
              <Input
                style={{ width: 220 }}
                value={p.base_url}
                onChange={(e) => updateProfile(p.id, { base_url: e.target.value })}
                placeholder="https://api.deepseek.com/v1"
              />
              <Input
                style={{ width: 140 }}
                value={p.model}
                onChange={(e) => updateProfile(p.id, { model: e.target.value })}
                placeholder="model"
              />
              <Input.Password
                style={{ width: 160 }}
                value={p.api_key}
                onChange={(e) => updateProfile(p.id, { api_key: e.target.value })}
                placeholder={p.api_key_set ? `已配置 ${p.api_key_masked}` : 'API Key'}
              />
              <Button size="small" type={p.id === activeCloudId ? 'primary' : 'default'} onClick={() => setActiveCloudId(p.id)}>
                {p.id === activeCloudId ? '当前' : '设为当前'}
              </Button>
              <Button size="small" danger onClick={() => removeProfile(p.id)}>
                删除
              </Button>
            </Space>
          </div>
        ))}

        <Space style={{ marginTop: '12px' }}>
          <Button
            type="primary"
            size="small"
            loading={llmTesting}
            onClick={handleTestLlm}
            style={{ background: '#0891b2', borderColor: '#0891b2' }}
          >
            测试连接
          </Button>
          <Button size="small" loading={llmLoading} onClick={handleSaveLlm}>
            保存 LLM 配置
          </Button>
        </Space>
      </Card>

      {/* ===== 存储路径设置 ===== */}
      <Card
        style={{
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: '8px',
          marginBottom: '16px',
        }}
        title={
          <div className="bilingual-title">
            <span className="cn" style={{ fontSize: '16px' }}>
              📁 存储路径
            </span>
            <span className="en">Storage Paths（只读，改 MODELHUB_ROOT 环境变量）</span>
          </div>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>MODELHUB_ROOT</Text>
            <Input value={paths.modelhub_root} readOnly style={{ marginTop: '4px' }} />
          </div>
          <div>
            <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>输出目录</Text>
            <Input value={paths.outputs_dir} readOnly style={{ marginTop: '4px' }} />
          </div>
          <div>
            <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>SQLite</Text>
            <Input value={paths.sqlite_path} readOnly style={{ marginTop: '4px' }} />
          </div>
        </div>
      </Card>
    </div>
  )
}

export default SystemSettings
