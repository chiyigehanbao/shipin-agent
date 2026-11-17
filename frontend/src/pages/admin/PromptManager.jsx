import React, { useEffect, useMemo, useState } from 'react'
import {
  Card,
  Button,
  Input,
  Select,
  Tree,
  Tag,
  Space,
  Typography,
  Divider,
  InputNumber,
  message,
  Modal,
  Spin,
  Alert,
} from 'antd'
import {
  PlusOutlined,
  SaveOutlined,
  CopyOutlined,
  DeleteOutlined,
  HistoryOutlined,
  SearchOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { promptsApi } from '../../services/api.js'

const { TextArea } = Input
const { Option } = Select
const { Text } = Typography

function mapApiTemplate(t) {
  return {
    id: t.id,
    name: t.name,
    nameEn: t.name_en,
    category: t.category,
    categoryName: t.category_name,
    version: t.version,
    usageCount: t.usage_count,
    updatedAt: t.updated_at,
    systemPromptCn: t.system_prompt_cn,
    systemPromptEn: t.system_prompt_en,
    userPromptCn: t.user_prompt_cn,
    userPromptEn: t.user_prompt_en,
    negativePromptCn: t.negative_prompt_cn || '',
    negativePromptEn: t.negative_prompt_en || '',
    defaultSteps: t.default_steps,
    defaultCfg: t.default_cfg,
    defaultSampler: t.default_sampler || 'euler',
    defaultScheduler: t.default_scheduler || 'simple',
    defaultModel: t.default_model || 'flux',
  }
}

function PromptManager() {
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [searchText, setSearchText] = useState('')
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const list = await promptsApi.list()
      const mapped = (list || []).map(mapApiTemplate)
      setTemplates(mapped)
      setSelectedTemplate((prev) => {
        if (prev && mapped.some((t) => t.id === prev)) return prev
        return mapped[0]?.id || null
      })
    } catch (e) {
      message.error(`加载模板失败：${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const currentTemplate = useMemo(
    () => templates.find((t) => t.id === selectedTemplate) || null,
    [templates, selectedTemplate],
  )

  useEffect(() => {
    if (currentTemplate) setDraft({ ...currentTemplate })
    else setDraft(null)
  }, [currentTemplate?.id])

  const treeData = useMemo(() => {
    const cats = [
      { title: '剧本生成', key: 'script' },
      { title: '角色生成', key: 'character' },
      { title: '场景生成', key: 'scene' },
      { title: '道具生成', key: 'prop' },
      { title: '分镜生成', key: 'storyboard' },
    ]
    const q = searchText.trim().toLowerCase()
    return cats
      .map((c) => ({
        ...c,
        children: templates
          .filter((t) => t.category === c.key)
          .filter(
            (t) =>
              !q ||
              t.name.toLowerCase().includes(q) ||
              (t.nameEn || '').toLowerCase().includes(q),
          )
          .map((t) => ({ title: t.name, key: t.id })),
      }))
      .filter((c) => c.children.length > 0)
  }, [templates, searchText])

  const patchDraft = (fields) => setDraft((d) => (d ? { ...d, ...fields } : d))

  const handleSave = async () => {
    if (!draft) return
    setSaving(true)
    try {
      await promptsApi.update(draft.id, {
        name: draft.name,
        name_en: draft.nameEn,
        category: draft.category,
        category_name: draft.categoryName,
        version: draft.version,
        system_prompt_cn: draft.systemPromptCn,
        system_prompt_en: draft.systemPromptEn,
        user_prompt_cn: draft.userPromptCn,
        user_prompt_en: draft.userPromptEn,
        negative_prompt_cn: draft.negativePromptCn,
        negative_prompt_en: draft.negativePromptEn,
        default_steps: draft.defaultSteps,
        default_cfg: draft.defaultCfg,
        default_sampler: draft.defaultSampler,
        default_scheduler: draft.defaultScheduler,
        default_model: draft.defaultModel,
      })
      message.success('模板已保存（持久化生效，重启不丢失）')
      await load()
    } catch (e) {
      message.error(`保存失败：${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = () => {
    if (!currentTemplate?.id) return
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个模板吗？内置默认模板删除后仍会回退到原始内容。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await promptsApi.remove(currentTemplate.id)
          message.success('已删除')
          setDraft(null)
          await load()
        } catch (e) {
          message.error(`删除失败：${e.message}`)
        }
      },
    })
  }

  const handleCreateNew = async () => {
    try {
      const tpl = await promptsApi.create({
        name: '未命名模板',
        name_en: 'Untitled',
        category: 'asset',
        category_name: '通用',
        version: 'v1.0',
        system_prompt_cn: '',
        system_prompt_en: '',
        user_prompt_cn: '',
        user_prompt_en: '',
      })
      await load()
      setDraft({ ...tpl })
      message.success('已新建模板')
    } catch (e) {
      message.error(`新建失败：${e.message}`)
    }
  }

  return (
    <div style={{ display: 'flex', gap: '16px', minHeight: '600px' }}>
      <Card
        style={{
          flex: '0 0 280px',
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: '8px',
        }}
        bodyStyle={{ padding: '16px', height: '100%' }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '12px',
          }}
        >
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--vf-text)' }}>
            模板库
          </span>
          <Space size="small">
            <Button size="small" icon={<ReloadOutlined />} onClick={load} />
            <Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleCreateNew}>
              新建
            </Button>
          </Space>
        </div>
        <Input
          placeholder="搜索模板..."
          prefix={<SearchOutlined style={{ color: 'var(--vf-text-muted)' }} />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ marginBottom: '12px' }}
          allowClear
        />
        {loading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : (
          <Tree
            treeData={treeData}
            defaultExpandAll
            selectedKeys={selectedTemplate ? [selectedTemplate] : []}
            onSelect={(keys) => {
              if (keys.length > 0 && String(keys[0]).startsWith('tpl_')) {
                setSelectedTemplate(keys[0])
              }
            }}
            style={{ background: 'transparent', color: 'var(--vf-text-secondary)' }}
          />
        )}
      </Card>

      <Card
        style={{
          flex: 1,
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: '8px',
        }}
        bodyStyle={{ padding: '20px', height: '100%', overflowY: 'auto' }}
      >
        {draft ? (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              message="这些是出图/润色的种子模板"
              description="角色/场景/道具出图会自动套用同类模板的负面词与采样参数（默认按 Flux：步数约 10、CFG 1.0、euler）。真正写锁仍走工作台「润色」pack；此处可改种子文案。"
            />
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                marginBottom: '20px',
              }}
            >
              <div>
                <div className="bilingual-title">
                  <span className="cn" style={{ fontSize: '20px', fontWeight: 700 }}>
                    {draft.name}
                  </span>
                  <span className="en">{draft.nameEn}</span>
                </div>
                <div style={{ marginTop: '8px' }}>
                  <Tag color="blue">{draft.categoryName}</Tag>
                  <Tag color="green">{draft.version}</Tag>
                  <span style={{ fontSize: '12px', color: 'var(--vf-text-muted)', marginLeft: '8px' }}>
                    使用 {draft.usageCount} 次 · 更新于 {draft.updatedAt}
                  </span>
                </div>
              </div>
              <Space>
                <Button icon={<HistoryOutlined />} disabled>
                  历史版本
                </Button>
                <Button icon={<CopyOutlined />} disabled>
                  复制
                </Button>
                <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
                  删除
                </Button>
              </Space>
            </div>

            <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
              <div style={{ flex: 1 }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>模板名称</Text>
                <Input
                  value={draft.name}
                  onChange={(e) => patchDraft({ name: e.target.value })}
                  style={{ marginTop: '4px' }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>所属分类</Text>
                <Select
                  value={draft.category}
                  onChange={(v) => patchDraft({ category: v })}
                  style={{ width: '100%', marginTop: '4px' }}
                >
                  <Option value="script">剧本生成</Option>
                  <Option value="character">角色生成</Option>
                  <Option value="scene">场景生成</Option>
                  <Option value="prop">道具生成</Option>
                  <Option value="storyboard">分镜生成</Option>
                </Select>
              </div>
            </div>

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '16px 0' }} />

            <div style={{ marginBottom: '16px' }}>
              <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                系统提示词 / System Prompt
              </Text>
              <TextArea
                value={draft.systemPromptCn}
                onChange={(e) => patchDraft({ systemPromptCn: e.target.value })}
                autoSize={{ minRows: 3, maxRows: 6 }}
                style={{
                  marginTop: '6px',
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  color: 'var(--vf-text)',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                }}
              />
              <TextArea
                value={draft.systemPromptEn}
                onChange={(e) => patchDraft({ systemPromptEn: e.target.value })}
                autoSize={{ minRows: 2, maxRows: 5 }}
                style={{
                  marginTop: '6px',
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  color: 'var(--vf-text-secondary)',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                }}
              />
            </div>

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '16px 0' }} />

            <div style={{ marginBottom: '16px' }}>
              <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                用户提示词模板 / User Prompt Template
              </Text>
              <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)', marginTop: '4px' }}>
                使用 {'{{变量名}}'} 作为占位符
              </div>
              <TextArea
                value={draft.userPromptCn}
                onChange={(e) => patchDraft({ userPromptCn: e.target.value })}
                autoSize={{ minRows: 4, maxRows: 8 }}
                style={{
                  marginTop: '6px',
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  color: 'var(--vf-text)',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                }}
              />
              <TextArea
                value={draft.userPromptEn}
                onChange={(e) => patchDraft({ userPromptEn: e.target.value })}
                autoSize={{ minRows: 3, maxRows: 7 }}
                style={{
                  marginTop: '6px',
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  color: 'var(--vf-text-secondary)',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                }}
              />
            </div>

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '16px 0' }} />

            <div style={{ marginBottom: '16px' }}>
              <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                负面提示词 / Negative Prompt
              </Text>
              <TextArea
                value={draft.negativePromptCn}
                onChange={(e) => patchDraft({ negativePromptCn: e.target.value })}
                autoSize={{ minRows: 2, maxRows: 4 }}
                style={{
                  marginTop: '6px',
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  color: 'var(--vf-text)',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                }}
              />
              <TextArea
                value={draft.negativePromptEn}
                onChange={(e) => patchDraft({ negativePromptEn: e.target.value })}
                autoSize={{ minRows: 2, maxRows: 5 }}
                style={{
                  marginTop: '6px',
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  color: 'var(--vf-text-secondary)',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                }}
              />
            </div>

            {['character', 'scene', 'prop'].includes(draft.category) && (
              <>
                <Divider style={{ borderColor: 'var(--vf-border)', margin: '16px 0' }} />
                <div style={{ marginBottom: '16px' }}>
                  <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                    默认生成参数（Flux）
                  </Text>
                  <div style={{ display: 'flex', gap: '16px', marginTop: '12px' }}>
                    <div style={{ flex: 1 }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>采样步数</Text>
                      <InputNumber
                        value={draft.defaultSteps}
                        onChange={(v) => patchDraft({ defaultSteps: v })}
                        min={1}
                        max={100}
                        style={{ width: '100%', marginTop: '2px' }}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>CFG Scale</Text>
                      <InputNumber
                        value={draft.defaultCfg}
                        onChange={(v) => patchDraft({ defaultCfg: v })}
                        min={0.5}
                        max={20}
                        step={0.5}
                        style={{ width: '100%', marginTop: '2px' }}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>采样器</Text>
                      <Select
                        value={draft.defaultSampler}
                        onChange={(v) => patchDraft({ defaultSampler: v })}
                        style={{ width: '100%', marginTop: '2px' }}
                      >
                        <Option value="euler">euler（Flux 推荐）</Option>
                        <Option value="dpmpp_2m">DPM++ 2M</Option>
                        <Option value="ddim">DDIM</Option>
                      </Select>
                    </div>
                  </div>
                </div>
              </>
            )}

            <Divider style={{ borderColor: 'var(--vf-border)', margin: '16px 0' }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                type="primary"
                size="large"
                icon={<SaveOutlined />}
                loading={saving}
                onClick={handleSave}
                style={{ background: '#e94560', borderColor: '#e94560' }}
              >
                保存模板
              </Button>
            </div>
          </>
        ) : (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--vf-text-muted)' }}>
            {loading ? <Spin /> : '请从左侧选择一个模板进行编辑'}
          </div>
        )}
      </Card>
    </div>
  )
}

export default PromptManager
