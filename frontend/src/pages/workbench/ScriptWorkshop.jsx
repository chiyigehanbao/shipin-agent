import React, { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Card,
  Button,
  Input,
  Radio,
  Upload,
  Select,
  Tag,
  Space,
  Typography,
  Divider,
  message,
  Progress,
  Modal,
} from 'antd'
import {
  ArrowLeftOutlined,
  UploadOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  BulbOutlined,
  ReloadOutlined,
  LeftOutlined,
  RightOutlined,
} from '@ant-design/icons'
import StepProgress from '../../components/StepProgress.jsx'
import useProjectStore from '../../store/projectStore.js'
import { scriptsApi, jobsApi, ragApi } from '../../services/api.js'

const { TextArea } = Input
const { Option } = Select
const { Title, Text } = Typography

const SCENE_POLISH_DEFAULTS = {
  promptEn: '',
  negativePrompt: '',
  interpretationCn: '',
}

function mapSceneFromApi(s) {
  return {
    id: s.id,
    name: s.name || '',
    location: s.location || '',
    time: s.time || '',
    characters: s.characters || [],
    props: s.props || [],
    dialogueCount: s.dialogue_count ?? 0,
    narrationCount: s.narration_count ?? 0,
    description: s.description || '',
    promptEn: s.prompt_en || '',
    negativePrompt: s.negative_prompt || '',
    interpretationCn: s.interpretation_cn || '',
    lines: Array.isArray(s.lines) ? s.lines : [],
  }
}

function buildScenePolishText(scene) {
  const meta = [scene.name, scene.location, scene.time].filter(Boolean).join(' · ')
  return meta ? `${meta}\n${scene.description || ''}` : scene.description || ''
}

function buildFullScriptText(scenes) {
  if (!scenes?.length) return ''
  return scenes
    .map((s, i) => {
      const chars = (s.characters || []).join('、') || '—'
      const props = (s.props || []).join('、') || '—'
      const lineBlock = (s.lines || []).length
        ? [
            '',
            '台词：',
            ...(s.lines || []).map((line) => {
              const who =
                line.type === 'narration' ? '旁白' : (line.speaker || '角色')
              const emo = line.emotion ? `（${line.emotion}）` : ''
              return `${who}${emo}：${line.text || ''}`
            }),
          ]
        : ['', '台词：（无）']
      return [
        `【场景${i + 1} ${s.name || '未命名'}】`,
        `地点：${s.location || '—'} · 时间：${s.time || '—'}`,
        `人物：${chars}`,
        `道具：${props}`,
        '',
        s.description || '（暂无场面描述）',
        ...lineBlock,
      ].join('\n')
    })
    .join('\n\n────────\n\n')
}

function countUnique(scenes, key) {
  const set = new Set()
  for (const s of scenes || []) {
    for (const item of s[key] || []) set.add(item)
  }
  return set.size
}

// 第一步：剧本工坊
// 输入创意或上传剧本，LLM 解析拆解为场景列表，选择风格和输出参数
function ScriptWorkshop() {
  const navigate = useNavigate()
  const { projectId } = useParams()
  const { currentProject, setCurrentStep } = useProjectStore()
  const resolvedProjectId = projectId || currentProject?.id || ''

  // 输入方式：text = 文本生成, file = 文件上传
  const [inputMode, setInputMode] = useState('text')

  // 文本输入内容
  const [storyIdea, setStoryIdea] = useState('')

  // 生成状态
  const [isGenerating, setIsGenerating] = useState(false)
  const [generateProgress, setGenerateProgress] = useState(0)

  // 是否已解析出剧本
  const [scriptParsed, setScriptParsed] = useState(false)

  // 选中的风格
  const [selectedStyles, setSelectedStyles] = useState(['玄幻修真'])

  // 输出参数
  const [resolution, setResolution] = useState('1080p')
  const [aspectRatio, setAspectRatio] = useState('16:9')
  const [fps, setFps] = useState('24fps')

  // 电影感拆解：预览（按场景 id）与加载态
  const [polishPreviewById, setPolishPreviewById] = useState({})
  const [polishing, setPolishing] = useState(false)

  // 智能建议：真实后端分析结果
  const [suggestions, setSuggestions] = useState([])
  const [suggestProvider, setSuggestProvider] = useState('')
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [suggestHidden, setSuggestHidden] = useState(false)

  const loadSuggestions = useCallback(async (opts = {}) => {
    if (!resolvedProjectId) return
    setSuggestLoading(true)
    try {
      const res = await scriptsApi.suggestions(resolvedProjectId)
      const list = Array.isArray(res?.suggestions) ? res.suggestions : []
      setSuggestions(list)
      setSuggestProvider(res?.provider || '')
      if (list.length === 0 && !opts.force) {
        setSuggestHidden(true)
      } else {
        setSuggestHidden(false)
      }
    } catch (e) {
      if (!opts.silent) {
        message.warning(`智能建议获取失败：${e.message}`)
      }
      setSuggestHidden(true)
    } finally {
      setSuggestLoading(false)
    }
  }, [resolvedProjectId])

  const [scenes, setScenes] = useState([])
  const [fullScript, setFullScript] = useState('')
  const [selectedSceneId, setSelectedSceneId] = useState(null)

  useEffect(() => {
    if (!resolvedProjectId) return
    let cancelled = false
    ;(async () => {
      try {
        const list = await scriptsApi.listScenes(resolvedProjectId)
        if (cancelled) return
        const mapped = list.map(mapSceneFromApi)
        setScenes(mapped)
        setFullScript(buildFullScriptText(mapped))
        if (mapped.length) {
          setScriptParsed(true)
          setSelectedSceneId(mapped[0].id)
        }
      } catch (e) {
        message.error(`加载场景失败: ${e.message}`)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [resolvedProjectId])

  // scenes 变化且已有剧本时刷新智能建议
  useEffect(() => {
    if (!resolvedProjectId || !scenes.length) {
      setSuggestions([])
      setSuggestHidden(false)
      return
    }
    loadSuggestions()
  }, [resolvedProjectId, scenes, loadSuggestions])

  // 风格列表
  const styleOptions = [
    { label: '真人短剧', value: '真人短剧', en: 'Real Person' },
    { label: '动漫', value: '动漫', en: 'Anime' },
    { label: '玄幻修真', value: '玄幻修真', en: 'Xianxia Fantasy' },
    { label: '卡通', value: '卡通', en: 'Cartoon' },
    { label: '古装', value: '古装', en: 'Ancient Costume' },
    { label: '赛博朋克', value: '赛博朋克', en: 'Cyberpunk' },
    { label: '系统流', value: '系统流', en: 'System LitRPG' },
    { label: '都市异能', value: '都市异能', en: 'Urban Fantasy' },
    { label: '穿越异兽', value: '穿越异兽', en: 'Isekai Beasts' },
    { label: '水墨风', value: '水墨风', en: 'Ink Wash' },
    { label: '蒸汽波', value: '蒸汽波', en: 'Vaporwave' },
    { label: '末日废土', value: '末日废土', en: 'Post-Apocalyptic' },
  ]

  const reloadScenes = async () => {
    if (!resolvedProjectId) return
    try {
      const list = await scriptsApi.listScenes(resolvedProjectId)
      const mapped = list.map(mapSceneFromApi)
      setScenes(mapped)
      setFullScript(buildFullScriptText(mapped))
      if (mapped.length) {
        setScriptParsed(true)
        setSelectedSceneId((prev) => prev || mapped[0].id)
      }
    } catch (e) {
      message.error(`刷新场景失败: ${e.message}`)
    }
  }

  useEffect(() => {
    const onDone = (ev) => {
      const j = ev.detail
      if (!j || j.project_id !== resolvedProjectId) return
      if (
        j.type === 'script_expand' ||
        j.type === 'script_analyze' ||
        j.type === 'prompt_polish' ||
        j.type === 'prompt_polish_batch'
      ) {
        reloadScenes()
        setPolishPreviewById({})
      }
    }
    window.addEventListener('vf-job-completed', onDone)
    return () => window.removeEventListener('vf-job-completed', onDone)
  }, [resolvedProjectId])

  const confirmIfActive = async (type) => {
    try {
      const active = await jobsApi.list({
        status: 'active',
        project_id: resolvedProjectId,
      })
      const hit = (active || []).find((j) => j.type === type)
      if (!hit) return true
      return await new Promise((resolve) => {
        Modal.confirm({
          title: '已有进行中任务',
          content: '同类型任务仍在进行，仍要再提交？',
          okText: '继续提交',
          cancelText: '取消',
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        })
      })
    } catch {
      return true
    }
  }

  const handleGenerateScript = async () => {
    if (!storyIdea.trim()) {
      message.warning('请先输入故事创意')
      return
    }
    if (!resolvedProjectId) {
      message.error('缺少项目 ID，请从项目列表进入')
      return
    }
    if (!(await confirmIfActive('script_expand'))) return
    setIsGenerating(true)
    setGenerateProgress(20)
    try {
      await jobsApi.create({
        type: 'script_expand',
        project_id: resolvedProjectId,
        payload: {
          text: storyIdea,
          style: selectedStyles.join(',') || '',
        },
      })
      setGenerateProgress(100)
      message.success('已提交后台扩写，可切换页面等待')
    } catch (e) {
      message.error(`扩写提交失败: ${e.message}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleParseScript = async () => {
    if (!storyIdea.trim()) {
      message.warning('请先粘贴或输入剧本文本')
      return
    }
    if (!resolvedProjectId) {
      message.error('缺少项目 ID，请从项目列表进入')
      return
    }
    if (!(await confirmIfActive('script_analyze'))) return
    setIsGenerating(true)
    setGenerateProgress(20)
    try {
      await jobsApi.create({
        type: 'script_analyze',
        project_id: resolvedProjectId,
        payload: {
          text: storyIdea,
          style: selectedStyles.join(',') || '',
        },
      })
      setGenerateProgress(100)
      message.success('已提交后台解析，可切换页面等待')
    } catch (e) {
      message.error(`解析提交失败: ${e.message}`)
    } finally {
      setIsGenerating(false)
    }
  }

  // 读取上传的剧本文件内容（支持 .txt / .docx / .pdf）
  const handleFileBeforeUpload = (file) => {
    const name = (file.name || '').toLowerCase()
    const isText = name.endsWith('.txt')
    const isDocx = name.endsWith('.docx')
    const isPdf = name.endsWith('.pdf')
    if (!isText && !isDocx && !isPdf) {
      message.warning('仅支持 .txt / .docx / .pdf')
      return Upload.LIST_IGNORE
    }
    const reader = new FileReader()
    if (isText) {
      reader.onload = (e) => {
        const content = String(e.target?.result || '').replace(/^\uFEFF/, '')
        if (!content.trim()) {
          message.warning('文件内容为空')
          return
        }
        setStoryIdea(content.trim())
        setInputMode('text')
        message.success(`已读取 ${file.name}（${content.length} 字），请核对后解析`)
      }
      reader.readAsText(file, 'utf-8')
      return false
    }
    // .docx / .pdf：无解析库，引导切换到文本模式粘贴
    message.info('请在「文本输入」模式粘贴内容后解析（当前未内置 .docx/.pdf 解析）')
    return Upload.LIST_IGNORE
  }

  // 切换风格选择
  const toggleStyle = (style) => {
    setSelectedStyles((prev) => {
      if (prev.includes(style)) {
        return prev.filter((s) => s !== style)
      }
      return [...prev, style]
    })
  }

  // 单场景电影感拆解：后台 Job，直接写回场景
  const handlePolishScene = async (scene) => {
    if (!resolvedProjectId) {
      message.error('缺少项目 ID')
      return
    }
    setPolishing(scene.id)
    try {
      await jobsApi.create({
        type: 'prompt_polish',
        project_id: resolvedProjectId,
        payload: {
          title: `电影感拆解 · ${scene.name}`,
          stage: 'script_scene',
          text_cn: buildScenePolishText(scene),
          context: { title: scene.name },
          target: 'scene',
          target_id: scene.id,
          apply: true,
          return_interpretation: true,
        },
      })
      message.success(`「${scene.name}」已提交后台拆解`)
    } catch (e) {
      message.error(`电影感拆解提交失败：${e.message}`)
    } finally {
      setPolishing(false)
    }
  }

  const applyPolishPreview = async (sceneId, preview) => {
    if (!preview) return
    const payload = {
      interpretation_cn: preview.interpretation_cn || '',
      prompt_en: preview.prompt_en || '',
      negative_prompt: preview.avoid || '',
    }
    if (resolvedProjectId) {
      await scriptsApi.updateScene(resolvedProjectId, sceneId, payload)
    }
    setScenes((prev) =>
      prev.map((s) =>
        s.id === sceneId
          ? {
              ...s,
              ...SCENE_POLISH_DEFAULTS,
              interpretationCn: payload.interpretation_cn,
              promptEn: payload.prompt_en,
              negativePrompt: payload.negative_prompt,
            }
          : s,
      ),
    )
  }

  const handleApplyPolish = async (sceneId) => {
    const preview = polishPreviewById[sceneId]
    if (!preview) {
      message.warning('暂无预览可应用')
      return
    }
    try {
      await applyPolishPreview(sceneId, preview)
      message.success('已应用到场景并保存')
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    }
  }

  const handlePolishAll = async () => {
    if (!scenes.length) {
      message.warning('暂无场景可润色')
      return
    }
    if (!resolvedProjectId) {
      message.error('缺少项目 ID')
      return
    }
    if (!(await confirmIfActive('prompt_polish_batch'))) return
    setPolishing('all')
    try {
      await jobsApi.create({
        type: 'prompt_polish_batch',
        project_id: resolvedProjectId,
        payload: {
          items: scenes.map((scene) => ({
            stage: 'script_scene',
            text_cn: buildScenePolishText(scene),
            context: { title: scene.name },
            target: 'scene',
            target_id: scene.id,
            apply: true,
            return_interpretation: true,
          })),
        },
      })
      message.success('本集润色已提交后台，可切换页面等待')
    } catch (e) {
      message.error(`本集润色提交失败：${e.message}`)
    } finally {
      setPolishing(false)
    }
  }

  const handleIngestScene = async (scene) => {
    if (!resolvedProjectId) {
      message.error('缺少项目 ID')
      return
    }
    try {
      await ragApi.ingest({
        source_type: 'scene',
        project_id: resolvedProjectId,
        ref_id: scene.id,
        title: scene.name,
      })
      message.success(`「${scene.name}」已存入知识库`)
    } catch (e) {
      message.error(`入库失败: ${e.message}`)
    }
  }

  const handleApplyAllPolish = async () => {
    const ids = Object.keys(polishPreviewById)
    if (!ids.length) {
      message.warning('暂无预览可应用')
      return
    }
    try {
      for (const id of ids) {
        await applyPolishPreview(id, polishPreviewById[id])
      }
      message.success(`已全部应用并保存（${ids.length} 个预览）`)
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    }
  }

  // 下一步
  const handleNext = () => {
    if (!scriptParsed) {
      message.warning('请先生成或解析剧本')
      return
    }
    setCurrentStep(2)
    navigate(`/workbench/${projectId}/assets`)
  }

  // 返回项目列表
  const handleBack = () => {
    navigate('/workbench')
  }

  // 步骤点击回退
  const handleStepChange = (step) => {
    // 只能回退到已完成的步骤
    if (step < 1) return
    setCurrentStep(step + 1)
    if (step === 0) navigate(`/workbench/${projectId}/script`)
  }

  return (
    <div>
      {/* 返回按钮 */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={handleBack}
        style={{ marginBottom: '16px', color: 'var(--vf-text-secondary)' }}
      >
        返回项目列表
      </Button>

      {/* 步骤进度条 */}
      <StepProgress current={1} onChange={handleStepChange} />

      {/* 主体内容 - 左右分栏 */}
      <div style={{ display: 'flex', gap: '20px', minHeight: '500px' }}>
        {/* ===== 左栏：输入区 (55%) ===== */}
        <Card
          style={{
            flex: '0 0 55%',
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '20px' }}
        >
          <div className="bilingual-title" style={{ marginBottom: '20px' }}>
            <span className="cn" style={{ fontSize: '18px', fontWeight: 600 }}>
              剧本工坊
            </span>
            <span className="en">Script Workshop</span>
          </div>

          {/* 输入方式切换 */}
          <Radio.Group
            value={inputMode}
            onChange={(e) => setInputMode(e.target.value)}
            style={{ marginBottom: '20px' }}
            buttonStyle="solid"
          >
            <Radio.Button value="text">✨ 文本生成</Radio.Button>
            <Radio.Button value="file">📎 文件上传</Radio.Button>
          </Radio.Group>

          {/* 文本生成模式 */}
          {inputMode === 'text' && (
            <div>
              <TextArea
                value={storyIdea}
                onChange={(e) => setStoryIdea(e.target.value)}
                placeholder="输入你的故事创意...&#10;&#10;例如：穿越女将军在都市开甜品店，用兵法经营生意，同时寻找回家的方法"
                autoSize={{ minRows: 8, maxRows: 12 }}
                style={{
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  color: 'var(--vf-text)',
                  borderRadius: '6px',
                  marginBottom: '12px',
                }}
              />
              <div style={{ fontSize: '12px', color: 'var(--vf-text-muted)', marginBottom: '16px' }}>
                支持一句话创意，AI 将自动扩写为完整剧本
              </div>

              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={handleGenerateScript}
                loading={isGenerating}
                block
                style={{
                  background: 'linear-gradient(135deg, #e94560, #ff6b8a)',
                  border: 'none',
                  height: '44px',
                  fontSize: '15px',
                }}
              >
                {isGenerating ? 'AI 正在创作中...' : 'AI 扩写剧本'}
              </Button>

              {isGenerating && (
                <Progress
                  percent={generateProgress}
                  status="active"
                  strokeColor="#e94560"
                  style={{ marginTop: '12px' }}
                />
              )}

              {scriptParsed && fullScript && (
                <div style={{ marginTop: 16 }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 8,
                    }}
                  >
                    <Text style={{ color: 'var(--vf-text)', fontSize: 13, fontWeight: 600 }}>
                      完整剧本
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      由场景列表汇总，可复制
                    </Text>
                  </div>
                  <TextArea
                    value={fullScript}
                    readOnly
                    autoSize={{ minRows: 12, maxRows: 24 }}
                    style={{
                      background: 'var(--vf-surface-muted)',
                      borderColor: 'var(--vf-border)',
                      color: 'var(--vf-text)',
                      borderRadius: 6,
                      fontSize: 13,
                      lineHeight: 1.6,
                    }}
                  />
                </div>
              )}
            </div>
          )}

          {/* 文件上传模式 */}
          {inputMode === 'file' && (
            <div>
              <Upload.Dragger
                accept=".txt,.pdf,.docx"
                beforeUpload={handleFileBeforeUpload}
                showUploadList={false}
                style={{
                  background: 'var(--vf-surface-muted)',
                  borderColor: 'var(--vf-border)',
                  borderRadius: '6px',
                  marginBottom: '16px',
                }}
              >
                <p className="ant-upload-drag-icon">
                  <UploadOutlined style={{ color: '#e94560', fontSize: '40px' }} />
                </p>
                <p className="ant-upload-text" style={{ color: 'var(--vf-text)' }}>
                  点击或拖拽文件到此处上传
                </p>
                <p className="ant-upload-hint" style={{ color: 'var(--vf-text-muted)' }}>
                  支持 .txt / .pdf / .docx 格式
                </p>
              </Upload.Dragger>

              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={handleParseScript}
                loading={isGenerating}
                block
                style={{
                  background: 'linear-gradient(135deg, #e94560, #ff6b8a)',
                  border: 'none',
                  height: '44px',
                  fontSize: '15px',
                }}
              >
                {isGenerating ? '正在解析剧本...' : '解析剧本'}
              </Button>

              {isGenerating && (
                <Progress
                  percent={generateProgress}
                  status="active"
                  strokeColor="#e94560"
                  style={{ marginTop: '12px' }}
                />
              )}

              {scriptParsed && fullScript && (
                <div style={{ marginTop: 16 }}>
                  <Text style={{ color: 'var(--vf-text)', fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 8 }}>
                    完整剧本
                  </Text>
                  <TextArea
                    value={fullScript}
                    readOnly
                    autoSize={{ minRows: 12, maxRows: 24 }}
                    style={{
                      background: 'var(--vf-surface-muted)',
                      borderColor: 'var(--vf-border)',
                      color: 'var(--vf-text)',
                      borderRadius: 6,
                      fontSize: 13,
                      lineHeight: 1.6,
                    }}
                  />
                </div>
              )}
            </div>
          )}
        </Card>

        {/* ===== 右栏：解析结果 (45%) ===== */}
        <Card
          style={{
            flex: 1,
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
            display: 'flex',
            flexDirection: 'column',
          }}
          bodyStyle={{ padding: '20px', flex: 1, display: 'flex', flexDirection: 'column' }}
        >
          <div className="bilingual-title" style={{ marginBottom: '16px' }}>
            <span className="cn" style={{ fontSize: '18px', fontWeight: 600 }}>
              剧本解析结果
            </span>
            <span className="en">Script Parsing Result</span>
          </div>

          {scriptParsed ? (
            <>
              {/* 统计信息 */}
              <div
                style={{
                  display: 'flex',
                  gap: '16px',
                  marginBottom: '16px',
                  padding: '12px',
                  background: 'var(--vf-surface-muted)',
                  borderRadius: '6px',
                }}
              >
                <div style={{ textAlign: 'center', flex: 1 }}>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#e94560' }}>
                    {scenes.length}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>场景</div>
                </div>
                <div style={{ textAlign: 'center', flex: 1 }}>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#0891b2' }}>
                    {countUnique(scenes, 'characters')}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>角色</div>
                </div>
                <div style={{ textAlign: 'center', flex: 1 }}>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#10b981' }}>
                    {countUnique(scenes, 'props')}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>道具</div>
                </div>
              </div>

              {/* 场景列表 */}
              <div
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  marginBottom: '16px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '8px',
                    marginBottom: '12px',
                    flexWrap: 'wrap',
                  }}
                >
                  <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '13px' }}>
                    场景列表
                  </Text>
                  <Space size="small" wrap>
                    <Button
                      size="small"
                      loading={polishing === 'all'}
                      disabled={!!polishing && polishing !== 'all'}
                      onClick={handlePolishAll}
                    >
                      本集全部润色
                    </Button>
                    {Object.keys(polishPreviewById).length > 0 && (
                      <Button
                        size="small"
                        type="primary"
                        disabled={!!polishing}
                        onClick={handleApplyAllPolish}
                        style={{ background: '#e94560', borderColor: '#e94560' }}
                      >
                        全部应用
                      </Button>
                    )}
                  </Space>
                </div>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {scenes.map((scene, index) => {
                    const preview = polishPreviewById[scene.id]
                    const isPolishingThis = polishing === scene.id
                    const selected = selectedSceneId === scene.id
                    return (
                      <Card
                        key={scene.id}
                        size="small"
                        hoverable
                        onClick={() =>
                          setSelectedSceneId((prev) => (prev === scene.id ? null : scene.id))
                        }
                        style={{
                          background: 'var(--vf-surface-muted)',
                          border: selected
                            ? '1px solid #e94560'
                            : '1px solid var(--vf-border)',
                          borderRadius: '6px',
                          cursor: 'pointer',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            marginBottom: '8px',
                          }}
                        >
                          <Tag color="#e94560" style={{ margin: 0 }}>
                            场景{index + 1}
                          </Tag>
                          <span
                            style={{
                              fontWeight: 600,
                              color: 'var(--vf-text)',
                              fontSize: '14px',
                              flex: 1,
                            }}
                          >
                            {scene.name}
                          </span>
                          <Button
                            size="small"
                            loading={isPolishingThis}
                            disabled={!!polishing && !isPolishingThis}
                            onClick={(e) => {
                              e.stopPropagation()
                              handlePolishScene(scene)
                            }}
                          >
                            电影感拆解
                          </Button>
                          <Button
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleIngestScene(scene)
                            }}
                          >
                            存入知识库
                          </Button>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                          📍 {scene.location} · ⏰ {scene.time}
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                          👤 {(scene.characters || []).join('、') || '—'}
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>
                          💬 {scene.dialogueCount}条对话 · 🎙️ {scene.narrationCount}条旁白
                          <span style={{ marginLeft: 8, color: 'var(--vf-text-muted)' }}>
                            {selected ? '点击收起' : '点击查看内容'}
                          </span>
                        </div>
                        {(scene.lines || []).length === 0 ? (
                          <div style={{ fontSize: 12, color: 'var(--vf-text-muted)', marginTop: 4 }}>
                            重新扩写/解析以生成台词
                          </div>
                        ) : (
                          (scene.lines || []).slice(0, 4).map((line) => (
                            <div
                              key={line.id}
                              style={{ fontSize: 12, color: 'var(--vf-text-secondary)', marginTop: 2 }}
                            >
                              {line.type === 'narration' ? '旁白' : (line.speaker || '角色')}：{line.text}
                              {line.emotion ? `（${line.emotion}）` : ''}
                            </div>
                          ))
                        )}
                        {(scene.lines || []).length > 4 && (
                          <div style={{ fontSize: 12, color: 'var(--vf-text-muted)', marginTop: 2 }}>
                            还有 {(scene.lines || []).length - 4} 条
                          </div>
                        )}

                        {selected && (
                          <div
                            style={{
                              marginTop: 10,
                              padding: 10,
                              background: 'var(--vf-surface)',
                              border: '1px solid var(--vf-border)',
                              borderRadius: 6,
                            }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Text style={{ fontSize: 12, fontWeight: 600, color: 'var(--vf-text)' }}>
                              场面描述
                            </Text>
                            <div
                              style={{
                                marginTop: 6,
                                fontSize: 13,
                                lineHeight: 1.7,
                                color: 'var(--vf-text)',
                                whiteSpace: 'pre-wrap',
                              }}
                            >
                              {scene.description || '（暂无场面描述）'}
                            </div>
                            {(scene.props || []).length > 0 && (
                              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--vf-text-secondary)' }}>
                                道具：{scene.props.join('、')}
                              </div>
                            )}
                            {scene.promptEn && (
                              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--vf-text-secondary)' }}>
                                已应用英文提示词：{scene.promptEn.slice(0, 120)}
                                {scene.promptEn.length > 120 ? '…' : ''}
                              </div>
                            )}
                          </div>
                        )}

                        {preview && (
                          <div
                            style={{
                              marginTop: '10px',
                              padding: '10px',
                              background: 'var(--vf-surface)',
                              border: '1px solid var(--vf-border)',
                              borderRadius: '6px',
                            }}
                            onClick={(e) => e.stopPropagation()}
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
                                {preview.provider ? (
                                  <Tag style={{ marginLeft: 8 }} color="blue">
                                    {preview.provider}
                                  </Tag>
                                ) : null}
                              </Text>
                              <Button
                                size="small"
                                type="primary"
                                disabled={!!polishing}
                                onClick={() => handleApplyPolish(scene.id)}
                                style={{ background: '#e94560', borderColor: '#e94560' }}
                              >
                                应用
                              </Button>
                            </div>
                            {preview.interpretation_cn ? (
                              <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                                <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>理解 · </Text>
                                {preview.interpretation_cn}
                              </div>
                            ) : null}
                            <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                              <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>EN · </Text>
                              {preview.prompt_en}
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>
                              <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>Avoid · </Text>
                              {preview.avoid}
                            </div>
                          </div>
                        )}
                      </Card>
                    )
                  })}
                </Space>
              </div>
            </>
          ) : (
            <div
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--vf-text-muted)',
              }}
            >
              <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.5 }}>
                📜
              </div>
              <div>生成或解析剧本后，这里会显示场景列表</div>
            </div>
          )}

          {/* 风格与输出设置 */}
          <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

          <div>
            <Title level={5} style={{ color: 'var(--vf-text)', marginBottom: '12px' }}>
              🎨 视觉风格 / Visual Style
            </Title>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
              {styleOptions.map((style) => {
                const isSelected = selectedStyles.includes(style.value)
                return (
                  <Tag.CheckableTag
                    key={style.value}
                    checked={isSelected}
                    onChange={() => toggleStyle(style.value)}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '4px',
                      fontSize: '13px',
                      background: isSelected ? 'rgba(233, 69, 96, 0.1)' : 'var(--vf-surface-muted)',
                      border: isSelected ? '1px solid #e94560' : '1px solid var(--vf-border)',
                      color: isSelected ? '#e94560' : 'var(--vf-text-secondary)',
                    }}
                  >
                    <div style={{ textAlign: 'center' }}>
                      <div>{style.label}</div>
                      <div style={{ fontSize: '10px', opacity: 0.7 }}>{style.en}</div>
                    </div>
                  </Tag.CheckableTag>
                )
              })}
            </div>
          </div>

          {/* 输出参数 */}
          <div>
            <Title level={5} style={{ color: 'var(--vf-text)', marginBottom: '12px' }}>
              ⚙️ 输出参数 / Output Settings
            </Title>
            <div style={{ display: 'flex', gap: '12px' }}>
              <div style={{ flex: 1 }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>清晰度</Text>
                <Select value={resolution} onChange={setResolution} style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="720p">720p</Option>
                  <Option value="1080p">1080p</Option>
                  <Option value="4K">4K</Option>
                </Select>
              </div>
              <div style={{ flex: 1 }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>比例</Text>
                <Select value={aspectRatio} onChange={setAspectRatio} style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="16:9">16:9 横屏</Option>
                  <Option value="9:16">9:16 竖屏</Option>
                  <Option value="1:1">1:1 方形</Option>
                  <Option value="21:9">21:9 宽屏</Option>
                </Select>
              </div>
              <div style={{ flex: 1 }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>帧率</Text>
                <Select value={fps} onChange={setFps} style={{ width: '100%', marginTop: '4px' }}>
                  <Option value="24fps">24fps</Option>
                  <Option value="30fps">30fps</Option>
                  <Option value="60fps">60fps</Option>
                </Select>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* 智能建议栏（后端真实分析：LLM + 规则兜底） */}
      {scriptParsed && !suggestHidden && (
        <div className="smart-suggestion" style={{ marginTop: '16px' }}>
          <div className="content" style={{ flex: 1 }}>
            {suggestLoading ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="loading-spinner" style={{ width: '14px', height: '14px' }} />
                <span>正在分析剧本…</span>
              </div>
            ) : suggestions.length ? (
              <div>
                {suggestions.map((s, idx) => (
                  <div key={`${s.issue}-${idx}`} style={{ marginBottom: idx < suggestions.length - 1 ? 6 : 0 }}>
                    <Tag
                      color={
                        s.severity === 'error' ? 'red' : s.severity === 'warning' ? 'orange' : 'green'
                      }
                      style={{ marginRight: 6 }}
                    >
                      {s.severity === 'error' ? '阻塞' : s.severity === 'warning' ? '建议' : '提示'}
                    </Tag>
                    <span>{s.issue}</span>
                    {s.suggestion ? <span style={{ color: 'var(--vf-text-muted)' }}> — {s.suggestion}</span> : null}
                  </div>
                ))}
                {suggestProvider === 'llm' ? (
                  <div style={{ marginTop: 6, fontSize: '11px', color: 'var(--vf-text-muted)', opacity: 0.7 }}>
                    由 LLM 分析 · 已在场景列表落库后自动刷新
                  </div>
                ) : null}
              </div>
            ) : (
              <span>
                <BulbOutlined style={{ marginRight: '8px' }} />
                剧本结构没有明显缺口。可手动补充角色动机与反派背景，进一步提升冲突张力。
              </span>
            )}
          </div>
          <Space>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={suggestLoading}
              onClick={() => loadSuggestions({ force: true })}
            >
              重新检测
            </Button>
            <Button size="small" onClick={() => setSuggestHidden(true)}>
              忽略
            </Button>
          </Space>
        </div>
      )}

      {/* 底部操作栏 */}
      <div className="bottom-bar">
        <Button icon={<LeftOutlined />} onClick={handleBack}>
          上一步
        </Button>
        <div style={{ color: 'var(--vf-text-muted)', fontSize: '13px' }}>
          当前步骤完成度：{scriptParsed ? '100%' : '0%'}
        </div>
        <Button
          type="primary"
          icon={<RightOutlined />}
          onClick={handleNext}
          style={{ background: '#e94560', borderColor: '#e94560' }}
        >
          下一步：角色与场景配置
        </Button>
      </div>
    </div>
  )
}

export default ScriptWorkshop
