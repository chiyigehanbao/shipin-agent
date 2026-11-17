import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Card,
  Button,
  Input,
  Select,
  Tabs,
  List,
  Tag,
  Space,
  Typography,
  Divider,
  Slider,
  message,
  Tooltip,
  Empty,
  Spin,
  Alert,
} from 'antd'
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  CheckOutlined,
  UploadOutlined,
  ZoomInOutlined,
  RotateRightOutlined,
  SwapOutlined,
  DownloadOutlined,
  BulbOutlined,
  LeftOutlined,
  RightOutlined,
  UserOutlined,
  EnvironmentOutlined,
  AppstoreOutlined,
  SoundOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import StepProgress from '../../components/StepProgress.jsx'
import IdentityReferencePanel from '../../components/IdentityReferencePanel.jsx'
import useProjectStore from '../../store/projectStore.js'
import { assetsApi, mediaUrl, modelsApi, promptsApi, ragApi } from '../../services/api.js'

const { TextArea } = Input
const { Option } = Select
const { Text } = Typography

const TYPE_META = {
  character: { label: '角色', icon: <UserOutlined />, placeholder: '👤' },
  scene: { label: '场景', icon: <EnvironmentOutlined />, placeholder: '🏞️' },
  prop: { label: '道具', icon: <AppstoreOutlined />, placeholder: '🔧' },
}

const STATUS_TEXT = {
  completed: '生成完成',
  generating: '生成中...',
  pending: '待生成',
  failed: '生成失败',
}

const STATUS_DOT = {
  completed: 'green',
  generating: 'yellow',
  pending: 'gray',
  failed: 'red',
}

const MODEL_OPTIONS = {
  flux: 'Flux GGUF · 1024×1024（默认 · 高质量）',
}

const MODEL_KEYS = ['flux']
const DEFAULT_MODEL = 'flux'

const ASPECT_OPTIONS = [
  { value: 'portrait', label: '竖幅 3:4（832×1216）', hint: '角色定妆 / 场景，短剧竖构图首选' },
  { value: 'square', label: '方形 1:1（1024×1024）', hint: '通用横竖均可' },
  { value: 'landscape', label: '横幅 4:3（1216×832）', hint: '宽场景 / 大景' },
]

function defaultAspectForType(type) {
  return type === 'character' || type === 'scene' ? 'portrait' : 'square'
}

const COMFY_HINT =
  '生成经本地 ComfyUI 串行队列自动提交内置工作流，无需在 Comfy 里手动跑图。'

function pickPreferredAsset(takes) {
  return (
    takes.find((t) => t.selection_status === 'selected') ||
    takes.find((t) => t.status === 'completed' && t.image_url) ||
    takes.find((t) => t.status === 'generating') ||
    takes[0]
  )
}

/** 同名多次出图收成一组，左侧只显示一个人物/场景。 */
function groupAssetsByName(list) {
  const map = new Map()
  for (const item of list || []) {
    const key = (item.name || '').trim() || item.id
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(item)
  }
  return [...map.entries()].map(([name, takes]) => ({
    name,
    takes,
    preferred: pickPreferredAsset(takes),
    count: takes.length,
    ready: takes.some(
      (t) =>
        t.type === 'character' &&
        !!(t.lock_en || t.lockEn || '').trim() &&
        t.status === 'completed' &&
        !!(t.image_url || '').trim() &&
        !['candidate', 'rejected'].includes(t.selection_status || 'legacy'),
    ),
  }))
}

function characterReadyHint(takes) {
  const selected = takes.find((t) => t.selection_status === 'selected')
  if (selected?.status === 'completed' && selected.image_url && (selected.lock_en || selected.lockEn)) {
    return '已定妆'
  }
  if (takes.some((t) => t.selection_status === 'candidate')) return '选角中·请选择一版'
  const usable = takes.filter((t) => !['candidate', 'rejected'].includes(t.selection_status || 'legacy'))
  const hasLock = usable.some((t) => !!(t.lock_en || t.lockEn || '').trim())
  const hasImage = usable.some((t) => t.status === 'completed' && !!(t.image_url || '').trim())
  if (hasLock && hasImage) return '可用'
  if (!hasLock && !hasImage) return '待定妆·缺锁缺图'
  if (!hasLock) return '待定妆·缺身份锁'
  return '待定妆·缺定妆图'
}

function mapAssetError(err, comfyUrl = 'http://127.0.0.1:8000') {
  const msg = String(err?.message || err || '')
  if (msg.includes('comfyui_unavailable')) {
    return `ComfyUI 不可用：请启动服务并确认地址（当前：${comfyUrl}）。若界面能开但 API 返回 503，多为仍在加载，请稍后重试。`
  }
  if (msg.includes('model not ready')) {
    return `模型权重未就绪：${msg}`
  }
  return msg || '生成失败'
}

// 第二步：资产生成
// 三个 Tab：角色 / 场景 / 道具
// 三栏布局：左侧列表 + 中间预览 + 右侧编辑
// 数据来自后端 /api/assets/{projectId}/assets，生成走真实 ComfyUI 队列
function AssetGeneration() {
  const navigate = useNavigate()
  const { projectId } = useParams()
  const { setCurrentStep } = useProjectStore()

  const [activeTab, setActiveTab] = useState('character')
  const [assetsByType, setAssetsByType] = useState({ character: [], scene: [], prop: [] })
  const [selectedAssetId, setSelectedAssetId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [casting, setCasting] = useState(false)
  const [promptCn, setPromptCn] = useState('')
  const [promptEn, setPromptEn] = useState('')
  const [lockEn, setLockEn] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [polishPreview, setPolishPreview] = useState(null)
  const [polishing, setPolishing] = useState(false)
  const [model, setModel] = useState(DEFAULT_MODEL)
  const [aspect, setAspect] = useState('square')
  const [readiness, setReadiness] = useState({
    flux: { ready: true, missing_files: [] },
  })
  const [comfyOnline, setComfyOnline] = useState(null)
  const [comfyUrl, setComfyUrl] = useState('http://127.0.0.1:8000')
  const [syncing, setSyncing] = useState(false)
  const [ragHits, setRagHits] = useState([])
  const [ragLoading, setRagLoading] = useState(false)
  const pollRef = useRef(null)

  const refreshComfy = useCallback(async () => {
    setComfyOnline(null)
    try {
      const services = await modelsApi.services()
      const sd = (services || []).find((s) => s.id === 'sd')
      if (sd?.api_url) setComfyUrl(sd.api_url)
      setComfyOnline(sd?.status === 'online' || sd?.status === 'busy')
    } catch {
      setComfyOnline(false)
    }
  }, [])

  const currentList = assetsByType[activeTab] || []
  const groupedAssets = useMemo(() => groupAssetsByName(currentList), [currentList])
  const currentAsset = currentList.find((i) => i.id === selectedAssetId) || null

  // 拉取某个 Tab 的资产列表
  const loadTab = useCallback(
    async (type, keepSelection = true) => {
      setLoading(true)
      try {
        const list = await assetsApi.list(projectId, type)
        setAssetsByType((prev) => ({ ...prev, [type]: list }))
        setSelectedAssetId((prev) => {
          if (keepSelection && list.some((i) => i.id === prev)) return prev
          return groupAssetsByName(list)[0]?.preferred?.id || list[0]?.id || null
        })
      } catch (e) {
        message.error(`加载${TYPE_META[type].label}列表失败：${e.message}`)
      } finally {
        setLoading(false)
      }
    },
    [projectId],
  )

  // 轮询：每 1.5s 拉详情；completed/failed 停止；单次失败不中断
  // 超时依赖后端任务 failed，前端不另设硬超时（与 poll_timeout_sec 对齐由后端负责）
  const pollAsset = useCallback(
    (assetId) => {
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const asset = await assetsApi.get(projectId, assetId)
          setAssetsByType((prev) => ({
            ...prev,
            [asset.type]: (prev[asset.type] || []).map((i) => (i.id === asset.id ? asset : i)),
          }))
          if (asset.status === 'completed') {
            clearInterval(pollRef.current)
            pollRef.current = null
            message.success('生成完成！')
          } else if (asset.status === 'failed') {
            clearInterval(pollRef.current)
            pollRef.current = null
            message.error(
              `生成失败：${mapAssetError({ message: asset.error || '未知错误' }, comfyUrl)}`,
            )
          }
        } catch (e) {
          // 单次查询失败不打断轮询
        }
      }, 1500)
    },
    [projectId, comfyUrl],
  )

  useEffect(() => {
    refreshComfy()
  }, [refreshComfy])

  // 首屏 + Tab 切换时加载
  useEffect(() => {
    loadTab(activeTab)
  }, [activeTab, loadTab])

  // 挂载时拉取模型权重就绪状态；失败不阻塞页面
  useEffect(() => {
    let cancelled = false
    modelsApi
      .readiness()
      .then((data) => {
        if (cancelled) return
        const models = data?.models || {}
        setReadiness({
          flux: models.flux ?? { ready: true, missing_files: [] },
        })
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // 当前选中模型未就绪时，自动切到第一个可用模型
  useEffect(() => {
    if (readiness[model]?.ready) return
    const firstReady = MODEL_KEYS.find((key) => readiness[key]?.ready)
    if (firstReady) setModel(firstReady)
  }, [readiness, model])

  // 卸载时清理轮询
  useEffect(() => () => clearInterval(pollRef.current), [])

  // 选中资产时同步编辑区
  useEffect(() => {
    if (currentAsset) {
      setPromptCn(currentAsset.prompt_cn || '')
      setPromptEn(currentAsset.prompt_en || '')
      setLockEn(currentAsset.lock_en || currentAsset.lockEn || '')
      setNegativePrompt(currentAsset.negative_prompt || '')
      setModel(currentAsset.model || DEFAULT_MODEL)
      setAspect(currentAsset.aspect || defaultAspectForType(currentAsset.type))
      setPolishPreview(null)
    }
  }, [currentAsset?.id])

  // 选中资产时检索相似案例（RAG）
  useEffect(() => {
    if (!currentAsset?.prompt_en) {
      setRagHits([])
      return
    }
    let cancelled = false
    setRagLoading(true)
    ragApi
      .search({ query: currentAsset.prompt_en, top_k: 3, type: currentAsset.type })
      .then((hits) => {
        if (!cancelled) setRagHits(hits || [])
      })
      .catch(() => {
        if (!cancelled) setRagHits([])
      })
      .finally(() => {
        if (!cancelled) setRagLoading(false)
      })
    return () => { cancelled = true }
  }, [currentAsset?.id, currentAsset?.prompt_en, currentAsset?.type])

  const polishStage = () => {
    if (activeTab === 'character') return 'character_lock'
    if (activeTab === 'scene') return 'scene_lock'
    return 'asset'
  }

  const applyPolishPreview = (preview) => {
    if (!preview) return { promptCn, promptEn, negativePrompt, lockEn }
    const nextEn = preview.prompt_en || ''
    const nextAvoid = preview.avoid || ''
    const nextCn = preview.prompt_cn
    const nextLock = preview.lock_en || lockEn
    setPromptEn(nextEn)
    setNegativePrompt(nextAvoid)
    if (nextCn) setPromptCn(nextCn)
    if (nextLock) setLockEn(nextLock)
    return {
      promptCn: nextCn || promptCn,
      promptEn: nextEn,
      negativePrompt: nextAvoid,
      lockEn: nextLock,
    }
  }

  const handlePolish = async () => {
    if (!currentAsset) return
    setPolishing(true)
    try {
      const result = await promptsApi.polish({
        stage: polishStage(),
        project_id: projectId,
        input: {
          text_cn: promptCn,
          text_en: promptEn,
            context: {
            type: activeTab,
            name: currentAsset?.name,
            asset_name: currentAsset?.name,
            lock_en: lockEn,
            model,
          },
        },
        options: { return_interpretation: true },
      })
      setPolishPreview(result)
      const providerHint = result?.provider ? `（${result.provider}）` : ''
      message.success(`电影感润色完成${providerHint}`)
    } catch (e) {
      message.error(`润色失败：${e.message}`)
    } finally {
      setPolishing(false)
    }
  }

  const handleApplyPolish = () => {
    if (!polishPreview) {
      message.warning('暂无预览可应用')
      return
    }
    applyPolishPreview(polishPreview)
    message.success('已应用到提示词')
  }

  const submitGenerate = async ({
    id,
    name,
    type,
    prompt_cn,
    prompt_en,
    negative_prompt,
    lock_en,
    model: genModel,
    aspect: genAspect,
  }) => {
    if (comfyOnline === false) {
      const tip = mapAssetError({ message: 'comfyui_unavailable' }, comfyUrl)
      message.error(tip)
      throw new Error(tip)
    }
    const asset = await assetsApi.generate(projectId, {
      asset_id: id || undefined,
      name,
      type,
      prompt_cn,
      prompt_en,
      model: genModel,
      negative_prompt: negative_prompt || '',
      lock_en: lock_en || '',
      aspect: genAspect || defaultAspectForType(type),
    })
    setAssetsByType((prev) => {
      const list = prev[activeTab] || []
      const exists = list.some((i) => i.id === asset.id)
      return {
        ...prev,
        [activeTab]: exists
          ? list.map((i) => (i.id === asset.id ? asset : i))
          : [asset, ...list],
      }
    })
    setSelectedAssetId(asset.id)
    message.loading('已提交，生成中...', 1)
    pollAsset(asset.id)
    return asset
  }

  const handleRegenerate = async () => {
    if (!currentAsset) return
    setSubmitting(true)
    try {
      await submitGenerate({
        id: currentAsset.id,
        name: currentAsset.name,
        type: currentAsset.type,
        prompt_cn: promptCn,
        prompt_en: promptEn,
        negative_prompt: negativePrompt || '',
        lock_en: lockEn,
        model,
        aspect,
      })
    } catch (e) {
      message.error(`提交失败：${mapAssetError(e, comfyUrl)}`)
    } finally {
      setSubmitting(false)
    }
  }

  const handleCastCharacter = async () => {
    if (!currentAsset || activeTab !== 'character') return
    setCasting(true)
    try {
      const result = await assetsApi.castCharacter(projectId, currentAsset.id)
      const candidates = result.candidates || []
      if (candidates[0]?.id) setSelectedAssetId(candidates[0].id)
      message.success('已提交 4 版 AI 选角；四张使用同一机位和光线，便于只比较长相与气质')
      const groupId = result.candidate_group_id
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const list = await assetsApi.list(projectId, 'character')
          setAssetsByType((prev) => ({ ...prev, character: list }))
          const group = list.filter((item) => item.candidate_group_id === groupId)
          if (group.length === 4 && group.every((item) => item.status !== 'generating')) {
            clearInterval(pollRef.current)
            pollRef.current = null
            setCasting(false)
          }
        } catch {
          // 单次刷新失败不打断本地生成队列。
        }
      }, 1500)
    } catch (e) {
      setCasting(false)
      message.error(`AI 选角失败：${mapAssetError(e, comfyUrl)}`)
    }
  }

  const handleSelectCasting = async () => {
    if (!currentAsset) return
    setCasting(true)
    try {
      const selected = await assetsApi.selectCharacter(projectId, currentAsset.id)
      await loadTab('character', true)
      setSelectedAssetId(selected.id)
      message.success('已锁定这版长相与气质，后续分镜只引用该身份锚点')
    } catch (e) {
      message.error(`选定失败：${e.message}`)
    } finally {
      setCasting(false)
    }
  }

  const handleIdentityChanged = useCallback(async () => {
    await loadTab('character', true)
  }, [loadTab])

  const handlePolishAndGenerate = async () => {
    if (!currentAsset) return
    setSubmitting(true)
    try {
      const result = await promptsApi.polish({
        stage: polishStage(),
        project_id: projectId,
        input: {
          text_cn: promptCn,
          text_en: promptEn,
            context: {
            type: activeTab,
            name: currentAsset?.name,
            asset_name: currentAsset?.name,
            lock_en: lockEn,
            model,
          },
        },
        options: { return_interpretation: true },
      })
      setPolishPreview(result)
      const applied = applyPolishPreview(result)
      await submitGenerate({
        id: currentAsset.id,
        name: currentAsset.name,
        type: currentAsset.type,
        prompt_cn: applied.promptCn,
        prompt_en: applied.promptEn,
        negative_prompt: applied.negativePrompt || '',
        lock_en: applied.lockEn || lockEn,
        model,
        aspect,
      })
      message.success('润色已应用并开始生成')
    } catch (e) {
      message.error(`润色并生成失败：${mapAssetError(e, comfyUrl)}`)
    } finally {
      setSubmitting(false)
    }
  }

  // 新增资产
  const handleAdd = async () => {
    const typeMeta = TYPE_META[activeTab]
    const used = new Set(currentList.map((i) => i.name))
    let seq = groupedAssets.length + 1
    let name = `新${typeMeta.label}${seq}`
    while (used.has(name)) {
      seq += 1
      name = `新${typeMeta.label}${seq}`
    }
    setSubmitting(true)
    try {
      await submitGenerate({
        name,
        type: activeTab,
        prompt_cn: '',
        prompt_en: '',
        negative_prompt: negativePrompt || '',
        model,
        aspect: defaultAspectForType(activeTab),
      })
    } catch (e) {
      message.error(`添加失败：${mapAssetError(e, comfyUrl)}`)
    } finally {
      setSubmitting(false)
    }
  }

  const handleSyncFromScript = async () => {
    setSyncing(true)
    try {
      // 默认 enrich=true：同步即用 character_lock/scene_lock 高质量提示词（后端并发 LLM，失败降级模板）
      const result = await assetsApi.syncFromScript(projectId, {
        enrich: true,
        types: ['character', 'scene'],
      })
      message.success(
        `已同步：新建 ${result.created || 0}，更新 ${result.updated || 0}，跳过 ${result.skipped || 0}；提示词已生成，可直接出图`,
      )
      if (result.enrich_fallback) {
        message.warning('部分提示词使用了降级模板（LLM 不可用或超限）')
      }
      const all = await assetsApi.list(projectId)
      setAssetsByType({
        character: all.filter((a) => a.type === 'character'),
        scene: all.filter((a) => a.type === 'scene'),
        prop: all.filter((a) => a.type === 'prop'),
      })
      const prefer =
        (result.assets || []).find((a) => a.type === activeTab) ||
        all.find((a) => a.type === activeTab)
      if (prefer?.id) setSelectedAssetId(prefer.id)
      else if (all[0]?.id) setSelectedAssetId(all[0].id)
    } catch (e) {
      message.error(`同步失败：${e.message}`)
    } finally {
      setSyncing(false)
    }
  }

  const handleBatchGeneratePending = async () => {
    if (comfyOnline === false) {
      message.error(mapAssetError({ message: 'comfyui_unavailable' }, comfyUrl))
      return
    }
    const pending = currentList.filter((i) => i.status === 'pending')
    if (!pending.length) {
      message.info('当前 Tab 没有待出图资产')
      return
    }
    setSubmitting(true)
    let ok = 0
    try {
      for (const item of pending) {
        await submitGenerate({
          id: item.id,
          name: item.name,
          type: item.type,
          prompt_cn: item.prompt_cn || '',
          prompt_en: item.prompt_en || '',
          negative_prompt: item.negative_prompt || '',
          model: item.model || model,
          aspect: item.aspect || defaultAspectForType(item.type),
        })
        ok += 1
      }
      message.success(`已提交 ${ok} 个待出图任务`)
    } catch (e) {
      message.error(`批量生成中断（已提交 ${ok}）：${mapAssetError(e, comfyUrl)}`)
    } finally {
      setSubmitting(false)
    }
  }

  const handleNext = () => {
    if (activeTab === 'character') {
      const unready = groupedAssets.filter((g) => !g.ready)
      if (unready.length) {
        const names = unready.map((g) => g.name).join('、')
        // eslint-disable-next-line no-alert
        const ok = window.confirm(
          `还有未完成定妆的角色：${names}\n建议先润色并生成定妆图，否则分镜规划会被拦截。\n仍要进入分镜吗？`,
        )
        if (!ok) return
      }
    }
    setCurrentStep(3)
    navigate(`/workbench/${projectId}/storyboard`)
  }

  const handlePrev = () => {
    setCurrentStep(1)
    navigate(`/workbench/${projectId}/script`)
  }

  const handleStepChange = (step) => {
    if (step === 0) {
      setCurrentStep(1)
      navigate(`/workbench/${projectId}/script`)
    }
  }

  const tabItems = Object.entries(TYPE_META).map(([key, meta]) => {
    const n = groupAssetsByName(assetsByType[key] || []).length
    const en = key === 'character' ? 'Characters' : key === 'scene' ? 'Scenes' : 'Props'
    return {
      key,
      label: (
        <span>
          {meta.icon} {meta.label} {n ? n : ''} / {en}
        </span>
      ),
    }
  })

  return (
    <div>
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/workbench')}
        style={{ marginBottom: '16px', color: 'var(--vf-text-secondary)' }}
      >
        返回项目列表
      </Button>

      <StepProgress current={2} onChange={handleStepChange} />

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
        }}
      >
        <div className="bilingual-title">
          <span className="cn" style={{ fontSize: '18px', fontWeight: 600 }}>
            资产生成
          </span>
          <span className="en">Asset Generation</span>
        </div>
        <Space>
          <Button size="small" icon={<ThunderboltOutlined />} loading={syncing} onClick={handleSyncFromScript}>
            从剧本同步
          </Button>
          <Button
            size="small"
            disabled={comfyOnline === false}
            loading={submitting}
            onClick={handleBatchGeneratePending}
          >
            批量生成待出图
          </Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => loadTab(activeTab, false)}>
            刷新列表
          </Button>
        </Space>
      </div>

      {comfyOnline === null ? (
        <Alert type="info" showIcon message="正在检测 ComfyUI 连接…" style={{ marginBottom: 12 }} />
      ) : comfyOnline ? (
        <Alert
          type="success"
          showIcon
          message={`ComfyUI 在线（${comfyUrl}）`}
          description={COMFY_HINT}
          style={{ marginBottom: 12 }}
        />
      ) : (
        <Alert
          type="error"
          showIcon
          message={`ComfyUI 不可用（${comfyUrl}）`}
          description="请先启动 ComfyUI；若页面能打开但 API 返回 503，多为仍在加载，请稍后点重试。"
          action={
            <Button size="small" onClick={refreshComfy}>
              重试
            </Button>
          }
          style={{ marginBottom: 12 }}
        />
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} style={{ marginBottom: '16px' }} />

      <div style={{ display: 'flex', gap: '16px', minHeight: '550px' }}>
        {/* ===== 左栏：资产列表 ===== */}
        <Card
          style={{
            flex: '0 0 240px',
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '12px', height: '100%' }}
        >
          <div
            style={{
              fontSize: '13px',
              color: 'var(--vf-text-secondary)',
              marginBottom: '12px',
              fontWeight: 600,
            }}
          >
            资产列表 · {groupedAssets.length}
          </div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '30px 0' }}>
              <Spin size="small" />
            </div>
          ) : groupedAssets.length > 0 ? (
            <List
              dataSource={groupedAssets}
              renderItem={(group) => {
                const selected = group.takes.some((t) => t.id === selectedAssetId)
                const item = selected
                  ? group.takes.find((t) => t.id === selectedAssetId)
                  : group.preferred
                const chronological = [...group.takes].reverse()
                return (
                  <List.Item
                    key={group.name}
                    onClick={() => {
                      if (!selected) setSelectedAssetId(group.preferred.id)
                    }}
                    style={{
                      padding: '10px 12px',
                      marginBottom: '4px',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      background: selected ? 'rgba(233, 69, 96, 0.15)' : 'transparent',
                      border: selected ? '1px solid #e94560' : '1px solid transparent',
                      transition: 'all 0.2s',
                    }}
                  >
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className={`status-dot ${STATUS_DOT[item?.status] || 'gray'}`}></span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontSize: '13px',
                              color: 'var(--vf-text)',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}
                          >
                            {group.name}
                            {group.count > 1 ? (
                              <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--vf-text-muted)' }}>
                                ×{group.count}
                              </span>
                            ) : null}
                          </div>
                          <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)' }}>
                            {activeTab === 'character' ? (
                              <span style={{ color: group.ready ? '#16a34a' : '#b45309' }}>
                                {characterReadyHint(group.takes)}
                              </span>
                            ) : group.count > 1 ? (
                              `${group.count} 个版本`
                            ) : item?.status === 'failed' ? (
                              item.error?.slice(0, 18)
                            ) : (
                              item?.model
                            )}
                          </div>
                        </div>
                      </div>
                      {group.count > 1 ? (
                        <div
                          style={{
                            display: 'flex',
                            flexWrap: 'wrap',
                            gap: 4,
                            marginTop: 8,
                            paddingLeft: 16,
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {chronological.map((take, idx) => {
                            const active = selectedAssetId === take.id
                            return (
                              <button
                                type="button"
                                key={take.id}
                                onClick={() => setSelectedAssetId(take.id)}
                                title={`${STATUS_TEXT[take.status] || take.status}${take.model ? ` · ${take.model}` : ''}`}
                                style={{
                                  width: 22,
                                  height: 22,
                                  padding: 0,
                                  fontSize: 11,
                                  lineHeight: '20px',
                                  borderRadius: 4,
                                  cursor: 'pointer',
                                  color: active ? '#fff' : 'var(--vf-text-secondary)',
                                  background: active ? '#e94560' : 'var(--vf-surface-muted)',
                                  border: take.status === 'failed' && !active
                                    ? '1px solid #e94560'
                                    : active
                                      ? '1px solid #e94560'
                                      : '1px solid var(--vf-border)',
                                }}
                              >
                                {idx + 1}
                              </button>
                            )
                          })}
                        </div>
                      ) : null}
                    </div>
                  </List.Item>
                )
              }}
            />
          ) : (
            <Empty
              description="暂无资产，请先从剧本同步角色/场景"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
              <Button type="primary" loading={syncing} onClick={handleSyncFromScript}>
                从剧本同步
              </Button>
            </Empty>
          )}
          <Button
            type="dashed"
            block
            icon={<PlusOutlined />}
            onClick={handleAdd}
            loading={submitting}
            disabled={comfyOnline === false}
            style={{
              marginTop: '12px',
              borderColor: 'var(--vf-border)',
              color: 'var(--vf-text-secondary)',
            }}
          >
            添加{TYPE_META[activeTab].label}
          </Button>
        </Card>

        {/* ===== 中栏：预览区 ===== */}
        <Card
          style={{
            flex: 1,
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '16px', height: '100%', display: 'flex', flexDirection: 'column' }}
        >
          <div style={{ flex: 1, position: 'relative' }}>
            <div
              className="preview-placeholder"
              style={{
                height: '100%',
                minHeight: '350px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                background: currentAsset
                  ? 'linear-gradient(135deg, #f8fafc 0%, #eef2f7 50%, #f8fafc 100%)'
                  : 'var(--vf-surface-muted)',
              }}
            >
              {currentAsset && mediaUrl(currentAsset.image_url) ? (
                <img
                  src={mediaUrl(currentAsset.image_url)}
                  alt={currentAsset.name}
                  style={{
                    maxWidth: '100%',
                    maxHeight: '100%',
                    objectFit: 'contain',
                    borderRadius: '6px',
                  }}
                />
              ) : currentAsset?.status === 'generating' ? (
                <div style={{ textAlign: 'center' }}>
                  <div
                    className="loading-spinner"
                    style={{ width: '40px', height: '40px', borderWidth: '3px', margin: '0 auto 12px' }}
                  ></div>
                  <div style={{ color: 'var(--vf-text-secondary)' }}>生成中...</div>
                </div>
              ) : currentAsset ? (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '64px', marginBottom: '12px' }}>
                    {TYPE_META[activeTab].placeholder}
                  </div>
                  <div style={{ color: 'var(--vf-text-secondary)', fontSize: '14px' }}>
                    {currentAsset.name} 预览图
                  </div>
                  {currentAsset.status === 'failed' && (
                    <div style={{ color: '#e94560', fontSize: '13px', marginTop: '8px', maxWidth: '320px' }}>
                      生成失败：{mapAssetError({ message: currentAsset.error }, comfyUrl)}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ color: 'var(--vf-text-muted)' }}>请选择资产</div>
              )}
            </div>

            {mediaUrl(currentAsset?.image_url) && (
              <div
                style={{
                  position: 'absolute',
                  top: '12px',
                  right: '12px',
                  display: 'flex',
                  gap: '8px',
                }}
              >
                <Tooltip title="放大">
                  <Button size="small" icon={<ZoomInOutlined />} />
                </Tooltip>
                <Tooltip title="旋转">
                  <Button size="small" icon={<RotateRightOutlined />} />
                </Tooltip>
                <Tooltip title="镜像">
                  <Button size="small" icon={<SwapOutlined />} />
                </Tooltip>
                <Tooltip title="下载">
                  <a href={mediaUrl(currentAsset.image_url)} download target="_blank" rel="noreferrer">
                    <Button size="small" icon={<DownloadOutlined />} />
                  </a>
                </Tooltip>
              </div>
            )}
          </div>

          {currentAsset && (
            <div
              style={{
                marginTop: '12px',
                padding: '10px 12px',
                background: 'var(--vf-surface-muted)',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className={`status-dot ${STATUS_DOT[currentAsset.status] || 'gray'}`}></span>
                <span style={{ fontSize: '13px', color: 'var(--vf-text-secondary)' }}>
                  {STATUS_TEXT[currentAsset.status] || currentAsset.status}
                </span>
                {currentAsset.status === 'completed' && currentAsset.image_url && (
                  <span style={{ fontSize: '12px', color: 'var(--vf-text-muted)' }}>
                    {currentAsset.model}
                  </span>
                )}
              </div>
              <span style={{ fontSize: '12px', color: 'var(--vf-text-muted)' }}>
                创建于 {currentAsset.created_at}
              </span>
            </div>
          )}
        </Card>

        {/* ===== 右栏：编辑区 ===== */}
        <Card
          style={{
            flex: 1,
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '16px', height: '100%', overflowY: 'auto' }}
        >
          {currentAsset ? (
            <>
              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>资产名称</Text>
                <div
                  style={{
                    fontSize: '18px',
                    fontWeight: 600,
                    color: 'var(--vf-text)',
                    marginTop: '4px',
                  }}
                >
                  {currentAsset.name}
                  <Tag color="#e94560" style={{ marginLeft: '8px' }}>
                    {TYPE_META[activeTab].label}
                  </Tag>
                  {currentAsset.selection_status === 'selected' ? (
                    <Tag color="green">已定妆</Tag>
                  ) : currentAsset.selection_status === 'candidate' ? (
                    <Tag color="gold">候选 {currentAsset.candidate_index}/4</Tag>
                  ) : currentAsset.selection_status === 'rejected' ? (
                    <Tag>未选中</Tag>
                  ) : null}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--vf-text-muted)' }}>
                  {currentAsset.name_en}
                </div>
              </div>

              <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

              {activeTab === 'character' && (
                <div style={{ marginBottom: 16 }}>
                  <Text style={{ color: 'var(--vf-text)', fontSize: 13, fontWeight: 600 }}>
                    🎭 AI 选角 / Casting
                  </Text>
                  <div style={{ fontSize: 11, color: 'var(--vf-text-muted)', margin: '6px 0 10px' }}>
                    生成四种精致但真实的商业短剧演员方案；剧情中的淋雨、疲惫和受伤不会写进永久长相。
                  </div>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button
                      type="primary"
                      icon={<UserOutlined />}
                      block
                      loading={casting}
                      disabled={comfyOnline === false || currentAsset.status === 'generating'}
                      onClick={handleCastCharacter}
                      style={{ background: '#722ed1', borderColor: '#722ed1' }}
                    >
                      AI 选角 · 生成 4 版
                    </Button>
                    {currentAsset.selection_status === 'candidate' ? (
                      <Button
                        icon={<CheckOutlined />}
                        block
                        loading={casting}
                        disabled={currentAsset.status !== 'completed' || !currentAsset.image_url}
                        onClick={handleSelectCasting}
                      >
                        选定此版长相与气质
                      </Button>
                    ) : null}
                  </Space>
                </div>
              )}

              <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

              <div style={{ marginBottom: '16px' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '8px',
                    marginBottom: '6px',
                  }}
                >
                  <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                    ✨ 正向提示词 / Positive Prompt
                  </Text>
                  <Space size="small">
                    <Button
                      size="small"
                      icon={<ThunderboltOutlined />}
                      loading={polishing}
                      disabled={polishing || submitting || currentAsset.status === 'generating'}
                      onClick={handlePolish}
                    >
                      润色
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      loading={submitting}
                      disabled={
                        polishing ||
                        submitting ||
                        currentAsset.status === 'generating' ||
                        comfyOnline === false
                      }
                      onClick={handlePolishAndGenerate}
                      style={{ background: '#e94560', borderColor: '#e94560' }}
                    >
                      润色并生成
                    </Button>
                  </Space>
                </div>
                <TextArea
                  value={promptCn}
                  onChange={(e) => setPromptCn(e.target.value)}
                  placeholder="输入中文提示词，将翻译或直接用于生成"
                  autoSize={{ minRows: 4, maxRows: 6 }}
                  style={{
                    marginTop: '6px',
                    background: 'var(--vf-surface-muted)',
                    borderColor: 'var(--vf-border)',
                    color: 'var(--vf-text)',
                    borderRadius: '4px 4px 0 0',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                  }}
                />
                <div className="prompt-translation">
                  🔄 {promptEn}
                </div>
              </div>

              {polishPreview && (
                <div
                  style={{
                    marginBottom: '16px',
                    padding: '10px',
                    background: 'var(--vf-surface-muted)',
                    border: '1px solid var(--vf-border)',
                    borderRadius: '6px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '8px',
                      gap: '8px',
                    }}
                  >
                    <Text style={{ color: 'var(--vf-text)', fontSize: '12px', fontWeight: 600 }}>
                      电影感预览
                      {polishPreview.provider ? (
                        <Tag style={{ marginLeft: 8 }} color="blue">
                          {polishPreview.provider}
                        </Tag>
                      ) : null}
                    </Text>
                    <Button
                      size="small"
                      type="primary"
                      disabled={polishing}
                      onClick={handleApplyPolish}
                      style={{ background: '#e94560', borderColor: '#e94560' }}
                    >
                      应用
                    </Button>
                  </div>
                  {polishPreview.interpretation_cn ? (
                    <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>理解 · </Text>
                      {polishPreview.interpretation_cn}
                    </div>
                  ) : null}
                  {polishPreview.lock_en ? (
                    <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>Lock · </Text>
                      {polishPreview.lock_en}
                    </div>
                  ) : null}
                  {polishPreview.prompt_cn ? (
                    <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>CN · </Text>
                      {polishPreview.prompt_cn}
                    </div>
                  ) : null}
                  <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>EN · </Text>
                    {polishPreview.prompt_en}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>Avoid · </Text>
                    {polishPreview.avoid}
                  </div>
                </div>
              )}

              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🔒 身份锁 / Identity lock
                </Text>
                <TextArea
                  value={lockEn}
                  onChange={(e) => setLockEn(e.target.value)}
                  placeholder="冻结外貌或场景锚点（英文）。后续分镜会原样粘贴，不要在这里写剧情。"
                  autoSize={{ minRows: 2, maxRows: 4 }}
                  style={{
                    marginTop: '6px',
                    background: 'var(--vf-surface-muted)',
                    borderColor: 'var(--vf-border)',
                    color: 'var(--vf-text)',
                    borderRadius: '4px',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                  }}
                />
              </div>

              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🖼 画幅比例 / Aspect
                </Text>
                <Select
                  size="small"
                  value={aspect}
                  onChange={setAspect}
                  style={{ width: '100%', marginTop: '6px' }}
                  options={ASPECT_OPTIONS.map((o) => ({
                    value: o.value,
                    label: o.label,
                  }))}
                />
                <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)', marginTop: '4px' }}>
                  {ASPECT_OPTIONS.find((o) => o.value === aspect)?.hint}
                </div>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🌐 英文提示词 / English Prompt
                </Text>
                <TextArea
                  value={promptEn}
                  onChange={(e) => setPromptEn(e.target.value)}
                  placeholder="ComfyUI 将使用英文提示词出图"
                  autoSize={{ minRows: 3, maxRows: 5 }}
                  style={{
                    marginTop: '6px',
                    background: 'var(--vf-surface-muted)',
                    borderColor: 'var(--vf-border)',
                    color: 'var(--vf-text)',
                    borderRadius: '4px 4px 0 0',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                  }}
                />
              </div>

              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🚫 负面提示词 / Negative Prompt
                </Text>
                <TextArea
                  value={negativePrompt}
                  onChange={(e) => setNegativePrompt(e.target.value)}
                  placeholder="Avoid / negative prompt（可由润色结果应用）"
                  autoSize={{ minRows: 2, maxRows: 4 }}
                  style={{
                    marginTop: '6px',
                    background: 'var(--vf-surface-muted)',
                    borderColor: 'var(--vf-border)',
                    color: 'var(--vf-text)',
                    borderRadius: '4px',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                  }}
                />
              </div>

              <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  ⚙️ 出图模型 / Model
                </Text>
                <Select
                  value={model}
                  onChange={setModel}
                  style={{ width: '100%', marginTop: '6px' }}
                  disabled={currentAsset.status === 'generating'}
                >
                  {MODEL_KEYS.map((key) => {
                    const info = readiness[key]
                    const label = MODEL_OPTIONS[key] + (info.ready ? '' : '（未就绪）')
                    const title = info.ready
                      ? undefined
                      : `缺少文件：${info.missing_files.join(', ')}`
                    return (
                      <Option key={key} value={key} disabled={!info.ready} title={title}>
                        {label}
                      </Option>
                    )
                  })}
                </Select>
                <Text
                  style={{
                    color: 'var(--vf-text-muted)',
                    fontSize: '11px',
                    display: 'block',
                    marginTop: '4px',
                  }}
                >
                  生成通过本地 ComfyUI 串行队列执行，一次一个任务。
                </Text>
              </div>

              {activeTab === 'character' && (
                <>
                  <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />
                  <div style={{ marginBottom: '16px' }}>
                    <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                      <SoundOutlined /> 角色配音 / Voice
                    </Text>
                    <div style={{ marginTop: '8px' }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>音色</Text>
                      <Select size="small" defaultValue="温和男声" style={{ width: '100%', marginTop: '2px' }}>
                        <Option value="温和男声">温和男声</Option>
                        <Option value="沉稳男声">沉稳男声</Option>
                        <Option value="低沉男声">低沉男声</Option>
                        <Option value="清脆女声">清脆女声</Option>
                        <Option value="温柔女声">温柔女声</Option>
                      </Select>
                    </div>
                    <div style={{ marginTop: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>语速</Text>
                        <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '11px' }}>1.0x</Text>
                      </div>
                      <Slider min={0.5} max={2} step={0.1} defaultValue={1.0} style={{ marginTop: '4px' }} />
                    </div>
                    <Button size="small" style={{ marginTop: '8px' }}>
                      🎵 试听
                    </Button>
                  </div>
                </>
              )}

              <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

              <Space direction="vertical" style={{ width: '100%' }}>
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  onClick={handleRegenerate}
                  loading={submitting || currentAsset.status === 'generating'}
                  disabled={comfyOnline === false}
                  block
                  style={{ background: '#e94560', borderColor: '#e94560' }}
                >
                  {currentAsset.status === 'generating' ? '生成中...' : '重新生成'}
                </Button>
                <Button icon={<CheckOutlined />} block>
                  确认使用
                </Button>
                <Button icon={<UploadOutlined />} block>
                  本地上传
                </Button>
              </Space>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--vf-text-muted)' }}>
              请从左侧选择一个资产
            </div>
          )}
        </Card>
      </div>

      {activeTab === 'character' &&
      currentAsset?.selection_status === 'selected' &&
      currentAsset?.status === 'completed' &&
      currentAsset?.image_url ? (
        <IdentityReferencePanel
          projectId={projectId}
          asset={currentAsset}
          mediaUrl={mediaUrl}
          onChanged={handleIdentityChanged}
        />
      ) : null}

      {/* RAG 参考栏 */}
      {ragHits.length > 0 && (
        <div
          className="smart-suggestion"
          style={{ marginTop: '16px', background: 'rgba(0, 217, 255, 0.08)', borderColor: 'rgba(0, 217, 255, 0.2)' }}
        >
          <div className="content" style={{ color: '#0891b2' }}>
            <BulbOutlined style={{ marginRight: '8px' }} />
            📚 RAG 参考：找到 {ragHits.length} 个相似案例，最高相似度 {(ragHits[0].similarity * 100).toFixed(0)}%
          </div>
          <Tooltip
            title={
              <div style={{ maxWidth: 260 }}>
                {ragHits.map((h) => (
                  <div key={h.case.id} style={{ marginBottom: 4 }}>
                    <strong>{h.case.title}</strong>（{h.case.type_name}，相似度 {(h.similarity * 100).toFixed(0)}%）
                    {h.case.description && <div style={{ fontSize: 11, opacity: 0.8 }}>{h.case.description.slice(0, 80)}...</div>}
                  </div>
                ))}
              </div>
            }
          >
            <Button size="small" type="primary">
              查看参考
            </Button>
          </Tooltip>
        </div>
      )}
      {ragLoading && currentAsset?.prompt_en && (
        <div style={{ marginTop: '16px', color: 'var(--vf-text-muted)', fontSize: '12px' }}>
          <Spin size="small" style={{ marginRight: 6 }} />检索相似案例中…
        </div>
      )}

      {/* 底部操作栏 */}
      <div className="bottom-bar">
        <Button icon={<LeftOutlined />} onClick={handlePrev}>
          上一步
        </Button>
        <div style={{ color: 'var(--vf-text-muted)', fontSize: '13px' }}>
          生成中 {currentList.filter((i) => i.status === 'generating').length} 个任务
        </div>
        <Button
          type="primary"
          icon={<RightOutlined />}
          onClick={handleNext}
          style={{ background: '#e94560', borderColor: '#e94560' }}
        >
          下一步：分镜设计
        </Button>
      </div>
    </div>
  )
}

export default AssetGeneration
