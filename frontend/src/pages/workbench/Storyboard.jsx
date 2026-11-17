import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Card,
  Button,
  Input,
  Select,
  Tag,
  Space,
  Typography,
  Divider,
  message,
  Tooltip,
  Checkbox,
  Modal,
} from 'antd'
import {
  ArrowLeftOutlined,
  ReloadOutlined,
  CheckOutlined,
  PlusOutlined,
  BulbOutlined,
  LeftOutlined,
  RightOutlined,
  CopyOutlined,
  DeleteOutlined,
  ExportOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import StepProgress from '../../components/StepProgress.jsx'
import IdentityRiskPanel from '../../components/IdentityRiskPanel.jsx'
import useProjectStore from '../../store/projectStore.js'
import {
  mediaUrl,
  jobsApi,
  promptsApi,
  promptArchitectureApi,
  storyboardApi,
  assetsApi,
  scriptsApi,
} from '../../services/api.js'

const { TextArea } = Input
const { Option } = Select
const { Text } = Typography
const H3_VIDEO_LENGTH = 124
const H3_VIDEO_FPS = 24
const H3_DURATION_SEC = H3_VIDEO_LENGTH / H3_VIDEO_FPS
const LOOK_FIELDS = [
  ['wardrobe', '服装'],
  ['makeup', '妆容'],
  ['hair_state', '发型状态'],
  ['injury', '伤情'],
  ['wetness', '湿润程度'],
  ['dirt', '脏污'],
  ['fatigue', '疲态'],
]
const REJECTION_OPTIONS = [
  ['identity_drift', '人物身份跑偏'],
  ['appearance_unrefined', '长相不精致'],
  ['wrong_temperament', '气质不符'],
  ['wrong_look_state', '服装或状态错误'],
  ['wrong_action', '动作错误'],
  ['wrong_composition', '构图错误'],
  ['other', '其他'],
]

/** API snake_case → UI camelCase */
function normalizeFrame(apiFrame) {
  if (!apiFrame) return null
  return {
    id: apiFrame.id,
    number: apiFrame.number,
    description: apiFrame.description || '',
    descriptionEn: apiFrame.description_en ?? apiFrame.descriptionEn ?? '',
    character: apiFrame.character || '',
    scene: apiFrame.scene || '',
    sceneId: apiFrame.scene_id ?? apiFrame.sceneId ?? null,
    props: apiFrame.props || [],
    shotType: apiFrame.shot_type ?? apiFrame.shotType ?? '中景',
    angle: apiFrame.angle || '平视',
    movement: apiFrame.movement || '固定',
    duration: apiFrame.duration ?? 3,
    promptCn: apiFrame.prompt_cn ?? apiFrame.promptCn ?? '',
    promptEn: apiFrame.prompt_en ?? apiFrame.promptEn ?? '',
    motionPromptEn: apiFrame.motion_prompt_en ?? apiFrame.motionPromptEn ?? '',
    negativePrompt: apiFrame.negative_prompt ?? apiFrame.negativePrompt ?? '',
    status: apiFrame.status || 'pending',
    imageUrl: apiFrame.image_url ?? apiFrame.imageUrl ?? null,
    assetId: apiFrame.asset_id ?? apiFrame.assetId ?? null,
    error: apiFrame.error ?? null,
    model: apiFrame.model || 'flux',
    videoUrl: apiFrame.video_url ?? apiFrame.videoUrl ?? null,
    videoStatus: apiFrame.video_status ?? apiFrame.videoStatus ?? 'pending',
    videoError: apiFrame.video_error ?? apiFrame.videoError ?? null,
    videoJobId: apiFrame.video_job_id ?? apiFrame.videoJobId ?? null,
    acceptedRenderAttemptId:
      apiFrame.accepted_render_attempt_id ?? apiFrame.acceptedRenderAttemptId ?? null,
    lines: Array.isArray(apiFrame.lines) ? apiFrame.lines : [],
  }
}

// 第三步：分镜故事板
// 顶部时间轴 + 左右分栏（预览 + 编辑）
// 底部一致性检测 + 批量操作
function Storyboard() {
  const navigate = useNavigate()
  const { projectId } = useParams()
  const { setCurrentStep } = useProjectStore()

  const [currentFrame, setCurrentFrame] = useState(0)
  const [isGenerating, setIsGenerating] = useState(false)
  const [onionSkin, setOnionSkin] = useState(false)
  const [currentScene, setCurrentScene] = useState(null)
  const [frames, setFrames] = useState([])
  const [breakdownLoading, setBreakdownLoading] = useState(false)
  const [polishPreview, setPolishPreview] = useState(null)
  const [polishing, setPolishing] = useState(false)
  const [consistencyIssues, setConsistencyIssues] = useState([])
  const [linkCharacters, setLinkCharacters] = useState([])
  const [linkScenes, setLinkScenes] = useState([])
  const [characterAssets, setCharacterAssets] = useState([])
  const [sceneRecords, setSceneRecords] = useState([])
  const [renderState, setRenderState] = useState(null)
  const [renderBusy, setRenderBusy] = useState(false)
  const [rejectReason, setRejectReason] = useState('identity_drift')
  const [rejectNote, setRejectNote] = useState('')
  const [reuseSeed, setReuseSeed] = useState(false)
  const [lookDraft, setLookDraft] = useState({})
  const [lookSaving, setLookSaving] = useState(false)
  const [selectedFrameIds, setSelectedFrameIds] = useState([])
  const [h3Artifact, setH3Artifact] = useState(null)
  const [h3Content, setH3Content] = useState('')
  const [h3Edited, setH3Edited] = useState(false)
  const [h3Compiling, setH3Compiling] = useState(false)
  const [h3Saving, setH3Saving] = useState(false)
  const pollRef = useRef(null)
  const renderPollRef = useRef(null)
  const currentFrameIdRef = useRef(null)

  const currentFrameData = frames[currentFrame]
  currentFrameIdRef.current = currentFrameData?.id || null

  // 切换场景时定位到该场景第一帧；返回全部场景保留原选择
  useEffect(() => {
    if (!currentScene) return
    const first = frames.find((f) => (f.sceneId || f.scene) === currentScene)
    if (first) {
      const gi = frames.findIndex((f) => f.id === first.id)
      if (gi >= 0) setCurrentFrame(gi)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentScene, frames])

  const scenesFromFrames = useMemo(() => {
    const seen = new Map()
    for (const f of frames) {
      const key = f.sceneId || f.scene
      if (key && !seen.has(key)) seen.set(key, { key, name: f.scene })
    }
    return Array.from(seen.values())
  }, [frames])
  const visibleFrames = useMemo(() => {
    if (!currentScene) return frames
    return frames.filter((f) => (f.sceneId || f.scene) === currentScene)
  }, [frames, currentScene])
  const visibleFrameData = currentFrameData
  const visibleIndex = Math.max(0, frames.findIndex((f) => f.id === visibleFrameData?.id))

  const mergeFrame = useCallback((updated) => {
    const normalized = normalizeFrame(updated)
    if (!normalized?.id) return
    setFrames((prev) => {
      const idx = prev.findIndex((f) => f.id === normalized.id)
      if (idx < 0) return [...prev, normalized]
      const next = [...prev]
      next[idx] = { ...prev[idx], ...normalized }
      return next
    })
  }, [])

  const updateCurrentField = (field, value) => {
    if (['description', 'promptCn', 'promptEn', 'motionPromptEn', 'character', 'scene', 'shotType', 'angle', 'movement', 'duration'].includes(field)) {
      setH3Artifact((prev) => (prev ? { ...prev, stale: true } : prev))
    }
    setFrames((prev) => {
      const next = [...prev]
      if (!next[currentFrame]) return prev
      next[currentFrame] = { ...next[currentFrame], [field]: value }
      return next
    })
  }

  // 挂载：拉取分镜列表；空列表显示空态（不再用本地 SEED 当真数据）
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!projectId) return
      try {
        const list = await storyboardApi.list(projectId)
        if (cancelled) return
        if (Array.isArray(list)) {
          setFrames(list.map(normalizeFrame))
          setCurrentFrame(0)
        }
      } catch (e) {
        if (!cancelled) {
          message.warning(`分镜列表加载失败：${e.message}`)
          setFrames([])
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  // 拉取项目真实角色/场景资产，供「关联资产」下拉选择
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!projectId) return
      try {
        const [chars, scenes, scriptScenes] = await Promise.all([
          assetsApi.list(projectId, 'character'),
          assetsApi.list(projectId, 'scene'),
          scriptsApi.listScenes(projectId),
        ])
        if (cancelled) return
        setCharacterAssets(Array.isArray(chars) ? chars : [])
        setSceneRecords(Array.isArray(scriptScenes) ? scriptScenes : [])
        setLinkCharacters(Array.isArray(chars) ? chars.map((c) => c.name) : [])
        setLinkScenes(Array.from(new Set([
          ...(Array.isArray(scenes) ? scenes.map((s) => s.name) : []),
          ...(Array.isArray(scriptScenes) ? scriptScenes.map((s) => s.name) : []),
        ].filter(Boolean))))
      } catch {
        if (!cancelled) {
          setCharacterAssets([])
          setSceneRecords([])
          setLinkCharacters([])
          setLinkScenes([])
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const refreshFrames = useCallback(async () => {
    if (!projectId) return
    const list = await storyboardApi.list(projectId)
    setFrames(Array.isArray(list) ? list.map(normalizeFrame) : [])
    setCurrentFrame(0)
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!projectId || !frames.length) {
        setConsistencyIssues([])
        return
      }
      try {
        const issues = await storyboardApi.consistencyCheck(projectId)
        if (!cancelled) setConsistencyIssues(Array.isArray(issues) ? issues : [])
      } catch {
        if (!cancelled) setConsistencyIssues([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId, frames])

  const handleBreakdown = async () => {
    if (!projectId) return
    setBreakdownLoading(true)
    try {
      const job = await jobsApi.create({
        type: 'storyboard_breakdown',
        project_id: projectId,
        payload: { mode: 'replace_empty', title: '分镜规划' },
      })
      message.loading('分镜规划进行中…', 1)
      let final = job
      for (let i = 0; i < 90; i++) {
        await new Promise((r) => setTimeout(r, 1500))
        final = await jobsApi.get(job.id)
        if (final.status === 'completed') {
          await refreshFrames()
          message.success('分镜规划已完成')
          return
        }
        if (final.status === 'failed') {
          const err = final.error || '未知错误'
          if (String(err).includes('characters_not_ready')) {
            message.error({
              content: `${err}（请回资产生成：润色 → 生成定妆图）`,
              duration: 8,
            })
          } else {
            message.error(`分镜规划失败：${err}`)
          }
          return
        }
      }
      message.warning('分镜规划仍在进行，请稍后刷新')
    } catch (e) {
      const msg = e.message || ''
      if (msg.includes('characters_not_ready')) {
        message.error(`${msg}（请回资产生成完成定妆）`)
      } else {
        message.error(`分镜规划失败：${msg}`)
      }
    } finally {
      setBreakdownLoading(false)
    }
  }
  // 切换帧时清空润色预览
  useEffect(() => {
    setPolishPreview(null)
  }, [currentFrameData?.id])

  useEffect(() => {
    let cancelled = false
    setH3Artifact(null)
    setH3Content('')
    setH3Edited(false)
    if (!projectId || !currentFrameData?.id) return () => {}
    ;(async () => {
      try {
        const artifact = await promptArchitectureApi.latestH3(
          projectId,
          'frame',
          currentFrameData.id,
          H3_DURATION_SEC,
        )
        if (!cancelled) {
          setH3Artifact(artifact)
          setH3Content(artifact.content || '')
          setH3Edited(false)
        }
      } catch {
        // 首次进入该帧时没有编译产物是正常状态。
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId, currentFrameData?.id])

  const loadRenderState = useCallback(async (frameId) => {
    if (!projectId || !frameId) return null
    const state = await storyboardApi.renderState(projectId, frameId)
    setRenderState(state)
    const newest = state?.attempts?.[0]
    setRenderBusy(['queued', 'running'].includes(newest?.status))
    return state
  }, [projectId])

  const startRenderPolling = useCallback((frameId) => {
    if (renderPollRef.current) clearTimeout(renderPollRef.current)
    const tick = async () => {
      if (currentFrameIdRef.current !== frameId) return
      try {
        const state = await loadRenderState(frameId)
        if (currentFrameIdRef.current !== frameId) return
        const newest = state?.attempts?.[0]
        if (['queued', 'running'].includes(newest?.status)) {
          renderPollRef.current = setTimeout(tick, 1500)
        } else if (newest?.status === 'candidate' || newest?.status === 'failed') {
          const frame = await storyboardApi.get(projectId, frameId)
          if (currentFrameIdRef.current === frameId) mergeFrame(frame)
        }
      } catch (e) {
        if (currentFrameIdRef.current === frameId && e.status !== 404) {
          message.warning(`渲染状态读取失败：${e.message}`)
        }
      }
    }
    tick()
  }, [loadRenderState, mergeFrame, projectId])

  // 每个分镜拥有独立的请求/候选状态；只在正式 attempt 执行中轮询。
  useEffect(() => {
    if (renderPollRef.current) clearTimeout(renderPollRef.current)
    setRenderState(null)
    setRenderBusy(false)
    setRejectReason('identity_drift')
    setRejectNote('')
    setReuseSeed(false)
    if (!projectId || !currentFrameData?.id) return () => {}
    startRenderPolling(currentFrameData.id)
    return () => {
      if (renderPollRef.current) clearTimeout(renderPollRef.current)
    }
  }, [projectId, currentFrameData?.id, startRenderPolling])

  const currentSceneRecord = useMemo(() => sceneRecords.find(
    (scene) => scene.id === currentFrameData?.sceneId || scene.name === currentFrameData?.scene,
  ) || null, [sceneRecords, currentFrameData?.sceneId, currentFrameData?.scene])

  useEffect(() => {
    setLookDraft(currentSceneRecord?.look_states || {})
  }, [currentSceneRecord?.id, currentFrameData?.id])

  // 轮询：每 1.5s 拉详情，直到 completed|failed
  const pollFrame = useCallback(
    (frameId, { kind = 'image' } = {}) => {
      if (pollRef.current) clearInterval(pollRef.current)
      setIsGenerating(true)
      pollRef.current = setInterval(async () => {
        try {
          const frame = await storyboardApi.get(projectId, frameId)
          mergeFrame(frame)
          if (kind === 'video') {
            if (frame.videoStatus === 'completed') {
              clearInterval(pollRef.current)
              pollRef.current = null
              setIsGenerating(false)
              message.success('镜头视频生成完成！')
            } else if (frame.videoStatus === 'failed') {
              clearInterval(pollRef.current)
              pollRef.current = null
              setIsGenerating(false)
              message.error(`镜头视频失败：${frame.videoError || '未知错误'}`)
            }
            return
          }
          if (frame.status === 'completed') {
            clearInterval(pollRef.current)
            pollRef.current = null
            setIsGenerating(false)
            message.success('分镜生成完成！')
          } else if (frame.status === 'failed') {
            clearInterval(pollRef.current)
            pollRef.current = null
            setIsGenerating(false)
            message.error(`分镜生成失败：${frame.error || '未知错误'}`)
          }
        } catch (e) {
          // 单次查询失败不打断轮询
        }
      }, 1500)
    },
    [projectId, mergeFrame],
  )

  useEffect(() => () => {
    clearInterval(pollRef.current)
    clearTimeout(renderPollRef.current)
  }, [])

  const getStatusDot = (status) => {
    switch (status) {
      case 'completed':
        return <span className="status-dot green"></span>
      case 'generating':
        return <span className="status-dot yellow"></span>
      case 'failed':
        return <span className="status-dot red"></span>
      case 'pending':
        return <span className="status-dot gray"></span>
      default:
        return <span className="status-dot gray"></span>
    }
  }

  const handlePolish = async () => {
    if (!currentFrameData) return
    setPolishing(true)
    try {
      const result = await promptsApi.polish({
        stage: 'storyboard_frame',
        project_id: projectId,
        input: {
          text_cn: currentFrameData.promptCn || currentFrameData.description || '',
          text_en: currentFrameData.promptEn || '',
          context: {
            shot_type: currentFrameData.shotType,
            angle: currentFrameData.angle,
            movement: currentFrameData.movement,
            frame_id: currentFrameData.id,
            number: currentFrameData.number,
            character: currentFrameData.character,
            scene: currentFrameData.scene,
          },
        },
        options: { return_interpretation: true },
      })
      let motion = {}
      try {
        motion = await promptsApi.polish({
          stage: 'i2v_motion',
          project_id: projectId,
          input: {
            text_cn: currentFrameData.description || currentFrameData.promptCn || '',
            text_en: result.prompt_en || currentFrameData.promptEn || '',
            context: {
              movement: currentFrameData.movement,
              duration: currentFrameData.duration,
              shot_type: currentFrameData.shotType,
            },
          },
          options: { return_interpretation: false },
        })
      } catch {
        motion = {}
      }
      setPolishPreview({ ...result, motion_prompt_en: motion.motion_prompt_en || '' })
      const providerHint = result?.provider ? `（${result.provider}）` : ''
      message.success(`电影感润色完成${providerHint}`)
    } catch (e) {
      message.error(`润色失败：${e.message}`)
    } finally {
      setPolishing(false)
    }
  }

  const handleApplyPolish = async () => {
    if (!currentFrameData) return
    if (!polishPreview) {
      message.warning('暂无预览可应用')
      return
    }
    const promptEn = polishPreview.prompt_en || ''
    const negativePrompt = polishPreview.avoid || ''
    const promptCn = polishPreview.prompt_cn || currentFrameData.promptCn || ''
    const motionPromptEn = polishPreview.motion_prompt_en || currentFrameData.motionPromptEn || ''
    const payload = {
      prompt_en: promptEn,
      negative_prompt: negativePrompt,
      prompt_cn: promptCn,
      motion_prompt_en: motionPromptEn,
    }
    try {
      const updated = await storyboardApi.update(projectId, currentFrameData.id, payload)
      mergeFrame(updated)
      setH3Artifact((prev) => (prev ? { ...prev, stale: true } : prev))
      message.success('已应用到分镜提示词')
    } catch (e) {
      setFrames((prev) => {
        const next = [...prev]
        if (!next[currentFrame]) return prev
        next[currentFrame] = {
          ...next[currentFrame],
          promptEn,
          negativePrompt,
          promptCn,
          motionPromptEn,
        }
        return next
      })
      setH3Artifact((prev) => (prev ? { ...prev, stale: true } : prev))
      message.warning(`已本地应用，同步失败：${e.message}`)
    }
  }

  const compileH3 = async () => {
    if (!currentFrameData) return null
    setH3Compiling(true)
    try {
      await storyboardApi.update(projectId, currentFrameData.id, {
        prompt_cn: currentFrameData.promptCn || '',
        prompt_en: currentFrameData.promptEn || '',
        negative_prompt: currentFrameData.negativePrompt || '',
        motion_prompt_en: currentFrameData.motionPromptEn || '',
        description: currentFrameData.description || '',
        duration: currentFrameData.duration || H3_DURATION_SEC,
      })
      const artifact = await promptArchitectureApi.compileH3({
        project_id: projectId,
        source_type: 'frame',
        source_id: currentFrameData.id,
        mode: 'i2va',
        duration_sec: H3_DURATION_SEC,
      })
      setH3Artifact(artifact)
      setH3Content(artifact.content || '')
      setH3Edited(false)
      if (artifact.validation_json?.valid) {
        message.success('H3 I2VA 提示词已按官方结构编译并通过校验')
      } else {
        message.warning('H3 编译完成，但结构校验仍有问题；请查看下方错误')
      }
      return artifact
    } catch (e) {
      message.error(`H3 编译失败：${e.message}`)
      return null
    } finally {
      setH3Compiling(false)
    }
  }

  const saveH3 = async (status = 'draft') => {
    if (!h3Artifact?.id || !h3Content.trim()) return null
    if (h3Artifact.stale) {
      message.warning('上游分镜已经变化，请先重新编译 H3，再保存或锁定')
      return null
    }
    setH3Saving(true)
    try {
      const artifact = await promptArchitectureApi.updateH3(h3Artifact.id, {
        content: h3Content,
        status,
        duration_sec: H3_DURATION_SEC,
      })
      setH3Artifact({ ...artifact, stale: false })
      setH3Content(artifact.content || '')
      setH3Edited(false)
      if (!artifact.validation_json?.valid) {
        message.warning('已保存，但未通过 H3 结构校验，暂不能生成视频')
      } else {
        message.success(status === 'locked' ? 'H3 提示词已锁定' : 'H3 提示词已保存')
      }
      return { ...artifact, stale: false }
    } catch (e) {
      message.error(`保存 H3 提示词失败：${e.message}`)
      return null
    } finally {
      setH3Saving(false)
    }
  }

  const syncCurrentFrame = async () => {
    if (!currentFrameData) return null
    return storyboardApi.update(projectId, currentFrameData.id, {
      prompt_cn: currentFrameData.promptCn || '',
      prompt_en: currentFrameData.promptEn || '',
      negative_prompt: currentFrameData.negativePrompt || '',
      motion_prompt_en: currentFrameData.motionPromptEn || '',
      description: currentFrameData.description || '',
      character: currentFrameData.character || '',
      scene: currentFrameData.scene || '',
      shot_type: currentFrameData.shotType || '',
      angle: currentFrameData.angle || '',
      movement: currentFrameData.movement || '',
      duration: currentFrameData.duration || 3,
    })
  }

  const submitRenderAttempt = async (temporaryDegradation = false) => {
    const attempt = await storyboardApi.submitRender(projectId, currentFrameData.id, {
      temporary_degradation: temporaryDegradation,
    })
    setRenderState((prev) => ({
      ...(prev || {}),
      attempts: [attempt, ...(prev?.attempts || []).filter((item) => item.id !== attempt.id)],
    }))
    setRenderBusy(true)
    message.loading(
      temporaryDegradation
        ? '已提交临时纯文本生成；此候选会标记为身份不可信…'
        : '已提交 Kontext 身份一致性生成…',
      1,
    )
    startRenderPolling(currentFrameData.id)
    return attempt
  }

  const handleGenerateFrame = async () => {
    if (!currentFrameData) return
    setRenderBusy(true)
    try {
      const updated = await syncCurrentFrame()
      if (updated) mergeFrame(updated)
      await submitRenderAttempt(false)
    } catch (e) {
      setRenderBusy(false)
      const degradable = [
        'kontext_model_unavailable',
        'kontext_workflow_unavailable',
        'reference_upload_invalid',
      ].includes(e.code)
      if (degradable) {
        Modal.confirm({
          title: 'Kontext 正式生成暂不可用',
          content: e.message,
          okText: '返回检查身份链路',
          cancelText: '忽略身份一致性，临时生成',
          onCancel: async () => {
            try {
              setRenderBusy(true)
              await submitRenderAttempt(true)
            } catch (fallbackError) {
              setRenderBusy(false)
              message.error(`临时生成提交失败：${fallbackError.message}`)
            }
          },
        })
      } else {
        message.error(`提交失败：${e.message || '未知错误'}`)
      }
    }
  }

  const handleAcceptCandidate = async (attemptId) => {
    setRenderBusy(true)
    try {
      await storyboardApi.acceptRender(projectId, currentFrameData.id, attemptId)
      const [frame] = await Promise.all([
        storyboardApi.get(projectId, currentFrameData.id),
        loadRenderState(currentFrameData.id),
      ])
      mergeFrame(frame)
      message.success('候选已通过，已设为 H3 正式首帧')
    } catch (e) {
      message.error(`接受失败：${e.message}`)
    } finally {
      setRenderBusy(false)
    }
  }

  const handleRejectCandidate = async (attemptId) => {
    setRenderBusy(true)
    try {
      await storyboardApi.rejectRender(projectId, currentFrameData.id, attemptId, {
        reason: rejectReason,
        note: rejectNote,
      })
      await loadRenderState(currentFrameData.id)
      setRejectNote('')
      message.success('已记录驳回原因，可按原身份重新生成')
    } catch (e) {
      message.error(`驳回失败：${e.message}`)
    } finally {
      setRenderBusy(false)
    }
  }

  const handleRetryCandidate = async (attemptId) => {
    setRenderBusy(true)
    try {
      const attempt = await storyboardApi.retryRender(
        projectId,
        currentFrameData.id,
        attemptId,
        reuseSeed,
      )
      setRenderState((prev) => ({
        ...(prev || {}),
        attempts: [attempt, ...(prev?.attempts || [])],
      }))
      message.loading(reuseSeed ? '已复用 seed 重试…' : '已用新 seed 重试…', 1)
      startRenderPolling(currentFrameData.id)
    } catch (e) {
      setRenderBusy(false)
      message.error(`重试失败：${e.message}`)
    }
  }

  const updateLookField = (assetId, field, value) => {
    setLookDraft((prev) => ({
      ...prev,
      [assetId]: { ...(prev[assetId] || {}), [field]: value },
    }))
  }

  const saveLookState = async () => {
    if (!currentSceneRecord?.id) {
      message.warning('当前分镜没有关联可保存的剧本场景')
      return
    }
    setLookSaving(true)
    try {
      const scene = await scriptsApi.updateScene(projectId, currentSceneRecord.id, {
        look_states: lookDraft,
      })
      setSceneRecords((prev) => prev.map((item) => (item.id === scene.id ? scene : item)))
      await loadRenderState(currentFrameData.id)
      message.success('场景 Look State 已保存；旧候选会自动标记过期')
    } catch (e) {
      message.error(`Look State 保存失败：${e.message}`)
    } finally {
      setLookSaving(false)
    }
  }

  const handleGenerateVideo = async () => {
    if (!currentFrameData) return
    if (!canGenerateVideo) {
      message.warning('请先审核并通过一张候选图，H3 只消费正式首帧')
      return
    }
    if (!currentFrameData.imageUrl) {
      message.warning('请先生成分镜静图')
      return
    }
    setIsGenerating(true)
    try {
      let artifact = h3Artifact
      if (artifact && h3Edited && !artifact.stale) {
        artifact = await saveH3('draft')
      } else if (!artifact || artifact.stale || !artifact.validation_json?.valid) {
        artifact = await compileH3()
        setIsGenerating(false)
        if (artifact?.validation_json?.valid) {
          message.info('最终 H3 提示词已显示，请确认内容后再次点击“生成镜头视频”')
        }
        return
      }
      if (!artifact?.validation_json?.valid || artifact.stale) {
        throw new Error('H3 提示词未通过校验，无法提交 MiniMax H3')
      }
      const updated = await storyboardApi.generateVideo(projectId, currentFrameData.id, {
        compiled_prompt_id: artifact.id,
        auto_compile: false,
        length: H3_VIDEO_LENGTH,
        width: 960,
        height: 544,
      })
      mergeFrame(updated)
      message.loading('已提交镜头视频生成...', 1)
      pollFrame(currentFrameData.id, { kind: 'video' })
    } catch (e) {
      setIsGenerating(false)
      message.error(`视频提交失败：${e.message}`)
    }
  }

  const handleNext = () => {
    setCurrentStep(4)
    navigate(`/workbench/${projectId}/render`)
  }

  const handlePrev = () => {
    setCurrentStep(2)
    navigate(`/workbench/${projectId}/assets`)
  }

  // 新增分镜帧（空帧，用户可补提示词后出图）
  const handleAddFrame = async () => {
    if (!projectId) return
    try {
      const frame = await storyboardApi.createFrame(projectId, {})
      setFrames((prev) => [...prev, normalizeFrame(frame)])
      setCurrentFrame(frames.length)
      setSelectedFrameIds([])
      message.success('已新增一空分镜')
    } catch (e) {
      message.error(`新增失败：${e.message}`)
    }
  }

  // 复制当前帧为新帧（含全部提示词与镜头参数）
  const handleDuplicateFrame = async () => {
    if (!currentFrameData?.id) return
    try {
      const src = currentFrameData
      const frame = await storyboardApi.createFrame(projectId, {
        description: src.description || '',
        description_en: src.descriptionEn || '',
        character: src.character || '',
        scene: src.scene || '',
      })
      const copy = { ...frame, ...src, id: frame.id }
      setFrames((prev) => [...prev, normalizeFrame(copy)])
      setCurrentFrame(frames.length)
      message.success('已复制当前分镜')
    } catch (e) {
      message.error(`复制失败：${e.message}`)
    }
  }

  // 确认：把当前帧的提示词/镜头参数落库
  const handleConfirmFrame = async () => {
    if (!currentFrameData?.id) return
    try {
      const d = currentFrameData
      const updated = await storyboardApi.update(projectId, d.id, {
        description: d.description,
        description_en: d.descriptionEn,
        prompt_cn: d.promptCn,
        prompt_en: d.promptEn,
        motion_prompt_en: d.motionPromptEn,
        negative_prompt: d.negativePrompt,
        shot_type: d.shotType,
        angle: d.angle,
        movement: d.movement,
        character: d.character,
        scene: d.scene,
        duration: d.duration,
      })
      mergeFrame(updated)
      message.success('已保存当前分镜')
    } catch (e) {
      message.error(`保存失败：${e.message}`)
    }
  }

  // 导出全部帧提示词（JSON + txt）
  const handleExportPrompts = () => {
    if (!frames.length) {
      message.info('暂无分镜可导出')
      return
    }
    const rows = frames.map((f, idx) => ({
      number: idx + 1,
      character: f.character,
      scene: f.scene,
      shotType: f.shotType,
      promptEn: f.promptEn,
      promptCn: f.promptCn,
    }))
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `storyboard-${projectId}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    message.success(`已导出 ${rows.length} 条分镜提示词`)
  }

  // 删除选中帧
  const handleDeleteSelected = async () => {
    if (!selectedFrameIds.length) {
      message.info('请先勾选要删除的分镜')
      return
    }
    try {
      for (const fid of selectedFrameIds) {
        await storyboardApi.deleteFrame(projectId, fid)
      }
      setFrames((prev) => prev.filter((f) => !selectedFrameIds.includes(f.id)))
      setSelectedFrameIds([])
      setCurrentFrame(0)
      message.success(`已删除 ${selectedFrameIds.length} 帧`)
    } catch (e) {
      message.error(`删除失败：${e.message}`)
    }
  }

  const toggleFrameSelected = (id) => {
    setSelectedFrameIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const toggleSelectAll = () => {
    setSelectedFrameIds((prev) =>
      prev.length === frames.length ? [] : frames.map((f) => f.id)
    )
  }

  const handleStepChange = (step) => {
    if (step === 0) {
      setCurrentStep(1)
      navigate(`/workbench/${projectId}/script`)
    } else if (step === 1) {
      setCurrentStep(2)
      navigate(`/workbench/${projectId}/assets`)
    }
  }

  const shotTypes = ['远景', '全景', '中景', '近景', '特写', '过肩镜头', '双人中景', '跟拍']
  const angles = ['平视', '俯视', '仰视', '侧视', '鸟瞰']
  const movements = ['固定', '推镜', '拉镜', '摇镜', '跟镜', '升降']

  const renderRequest = renderState?.current_request || renderState?.latest_request?.request || null
  const renderIdentities = renderRequest?.character_identities || []
  const renderAttempts = renderState?.attempts || []
  const newestAttempt = renderAttempts[0] || null
  const candidateAttempt = renderAttempts.find((attempt) => attempt.status === 'candidate') || null
  const candidateImageUrl = candidateAttempt?.image_url || ''
  const hasRenderHistory = renderAttempts.length > 0
  const canGenerateVideo = Boolean(
    currentFrameData?.acceptedRenderAttemptId
      || (!hasRenderHistory && currentFrameData?.status === 'completed' && currentFrameData?.imageUrl),
  )

  const previewBusy =
    isGenerating
    || renderBusy
    || ['queued', 'running'].includes(newestAttempt?.status)
    || currentFrameData?.status === 'generating'

  return (
    <div>
      {/* 返回按钮 */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/workbench')}
        style={{ marginBottom: '16px', color: 'var(--vf-text-secondary)' }}
      >
        返回项目列表
      </Button>

      {/* 步骤进度条 */}
      <StepProgress current={3} onChange={handleStepChange} />

      {/* 顶部场景切换 */}
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
            分镜故事板
          </span>
          <span className="en">Storyboard</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Button
            icon={<ThunderboltOutlined />}
            loading={breakdownLoading}
            onClick={handleBreakdown}
          >
            从剧本生成分镜
          </Button>
          <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '13px' }}>场景：</Text>
          <Select
            value={currentScene || 'all'}
            onChange={(v) => {
              setCurrentScene(v === 'all' ? null : v)
            }}
            style={{ width: '180px' }}
            placeholder="全部场景"
          >
            <Option value="all">全部场景</Option>
            {scenesFromFrames.map((s) => (
              <Option key={s.key} value={s.key}>
                {s.name}
              </Option>
            ))}
          </Select>
        </div>
      </div>

      {/* ===== 顶部时间轴 ===== */}
      {frames.length === 0 ? (
        <Card
          style={{
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
            marginBottom: '16px',
          }}
          bodyStyle={{ padding: '32px', textAlign: 'center' }}
        >
          <div style={{ color: 'var(--vf-text-secondary)', marginBottom: 12 }}>
            暂无分镜。请先完成剧本台词，再点击「从剧本生成分镜」。
          </div>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={breakdownLoading} onClick={handleBreakdown}>
            从剧本生成分镜
          </Button>
        </Card>
      ) : null}
      <Card
        style={{
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: '8px',
          marginBottom: '16px',
          display: frames.length ? undefined : 'none',
        }}
        bodyStyle={{ padding: '16px' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', overflowX: 'auto', paddingBottom: '8px' }}>
          {visibleFrames.map((frame) => {
            const globalIndex = frames.findIndex((f) => f.id === frame.id)
            return (
            <div
              key={frame.id}
              onClick={() => setCurrentFrame(globalIndex)}
              style={{
                flex: '0 0 120px',
                cursor: 'pointer',
                border: currentFrame === globalIndex ? '2px solid #e94560' : '1px solid var(--vf-border)',
                borderRadius: '6px',
                overflow: 'hidden',
                transition: 'all 0.2s',
                boxShadow: currentFrame === globalIndex ? '0 0 15px rgba(233, 69, 96, 0.3)' : 'none',
              }}
            >
              {/* 缩略图 */}
              <div
                style={{
                  height: '70px',
                  background: frame.status === 'completed'
                    ? 'linear-gradient(135deg, #eef2f7, #e2e8f0)'
                    : frame.status === 'generating'
                    ? 'linear-gradient(135deg, #f8fafc, #eef2f7)'
                    : 'var(--vf-surface-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {mediaUrl(frame.imageUrl) ? (
                  <img
                    src={mediaUrl(frame.imageUrl)}
                    alt={`#${frame.number}`}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : frame.status === 'generating' ? (
                  <div className="loading-spinner" style={{ width: '20px', height: '20px' }}></div>
                ) : frame.status === 'completed' ? (
                  <span style={{ fontSize: '24px', opacity: 0.6 }}>🎞️</span>
                ) : (
                  <span style={{ fontSize: '20px', color: 'var(--vf-text-muted)' }}>⏳</span>
                )}
                {/* 帧号 */}
                <div
                  style={{
                    position: 'absolute',
                    top: '4px',
                    left: '4px',
                    background: 'rgba(0,0,0,0.6)',
                    color: '#fff',
                    fontSize: '10px',
                    padding: '1px 4px',
                    borderRadius: '2px',
                  }}
                >
                  #{frame.number}
                </div>
                {/* 状态点 */}
                <div style={{ position: 'absolute', top: '4px', right: '4px' }}>
                  {getStatusDot(frame.status)}
                </div>
                {/* 时长 */}
                <div
                  style={{
                    position: 'absolute',
                    bottom: '4px',
                    right: '4px',
                    background: 'rgba(0,0,0,0.6)',
                    color: '#fff',
                    fontSize: '10px',
                    padding: '1px 4px',
                    borderRadius: '2px',
                  }}
                >
                  {frame.duration}s
                </div>
              </div>
              {/* 描述 */}
              <div
                style={{
                  padding: '6px 8px',
                  background: 'var(--vf-surface-muted)',
                  fontSize: '11px',
                  color: 'var(--vf-text-secondary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {frame.description}
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '2px 8px 4px',
                  background: 'var(--vf-surface-muted)',
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <Checkbox
                  size="small"
                  checked={selectedFrameIds.includes(frame.id)}
                  onChange={() => toggleFrameSelected(frame.id)}
                >
                  <span style={{ fontSize: '10px', color: 'var(--vf-text-muted)' }}>选择</span>
                </Checkbox>
              </div>
            </div>
            )
          })}

          {/* 添加按钮 */}
          <div
            role="button"
            tabIndex={0}
            onClick={handleAddFrame}
            style={{
              flex: '0 0 80px',
              height: '100px',
              border: '2px dashed var(--vf-border-strong)',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--vf-text-muted)',
              cursor: 'pointer',
            }}
          >
            <PlusOutlined style={{ fontSize: '20px' }} />
          </div>
        </div>
      </Card>

      {/* 左右分栏 */}
      <div style={{ display: 'flex', gap: '16px', minHeight: '450px' }}>
        {/* ===== 左栏：分镜预览 (45%) ===== */}
        <Card
          style={{
            flex: '0 0 45%',
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '16px', height: '100%', display: 'flex', flexDirection: 'column' }}
        >
          {/* 预览图 */}
          <div style={{ flex: 1, position: 'relative' }}>
            <div
              className="preview-placeholder"
              style={{
                height: '100%',
                minHeight: '300px',
                aspectRatio: '16/9',
                overflow: 'hidden',
              }}
            >
              {previewBusy && !mediaUrl(candidateImageUrl || currentFrameData?.imageUrl) && currentFrameData?.videoStatus !== 'generating' ? (
                <div style={{ textAlign: 'center' }}>
                  <div className="loading-spinner" style={{ width: '40px', height: '40px', borderWidth: '3px', margin: '0 auto 12px' }}></div>
                  <div style={{ color: 'var(--vf-text-secondary)' }}>Kontext 正在绑定人物身份…</div>
                </div>
              ) : mediaUrl(candidateImageUrl) ? (
                <img
                  src={mediaUrl(candidateImageUrl)}
                  alt={`候选分镜 #${currentFrameData?.number || ''}`}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                />
              ) : mediaUrl(currentFrameData?.videoUrl) ? (
                <video
                  src={mediaUrl(currentFrameData.videoUrl)}
                  controls
                  style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', background: '#000' }}
                />
              ) : mediaUrl(currentFrameData?.imageUrl) ? (
                <img
                  src={mediaUrl(currentFrameData.imageUrl)}
                  alt={`分镜 #${currentFrameData.number}`}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                />
              ) : currentFrameData ? (
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '64px', marginBottom: '12px' }}>🎬</div>
                  <div style={{ color: 'var(--vf-text-secondary)', fontSize: '14px' }}>
                    分镜 #{currentFrameData.number}
                  </div>
                  <div style={{ color: 'var(--vf-text-muted)', fontSize: '12px', marginTop: '4px' }}>
                    {currentFrameData.shotType} · {currentFrameData.angle}
                  </div>
                  {currentFrameData.status === 'failed' && currentFrameData.error ? (
                    <div style={{ color: '#e94560', fontSize: '12px', marginTop: '8px' }}>
                      {currentFrameData.error}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div style={{ color: 'var(--vf-text-muted)' }}>请选择分镜</div>
              )}
            </div>

            {candidateAttempt ? (
              <div
                style={{
                  position: 'absolute',
                  left: 12,
                  top: 12,
                  padding: '6px 10px',
                  border: '1px solid rgba(255,255,255,.2)',
                  background: 'rgba(9, 12, 18, .82)',
                  color: '#fff6e8',
                  fontSize: 11,
                  letterSpacing: '.08em',
                  textTransform: 'uppercase',
                  backdropFilter: 'blur(8px)',
                }}
              >
                Candidate · 待导演审核
              </div>
            ) : null}

            {/* 洋葱皮模式切换 */}
            <div
              style={{
                position: 'absolute',
                top: '12px',
                right: '12px',
              }}
            >
              <Tooltip title={onionSkin ? '关闭洋葱皮' : '洋葱皮模式'}>
                <Button
                  size="small"
                  type={onionSkin ? 'primary' : 'default'}
                  icon={onionSkin ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                  onClick={() => setOnionSkin(!onionSkin)}
                >
                  洋葱皮
                </Button>
              </Tooltip>
            </div>
          </div>

          {/* 帧信息 */}
          {currentFrameData && (
            <div
              style={{
                marginTop: '12px',
                padding: '12px',
                background: 'var(--vf-surface-muted)',
                borderRadius: '6px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--vf-text)' }}>
                    #{currentFrameData.number} {currentFrameData.description}
                  </span>
                </div>
                <Tag color="blue">{currentFrameData.duration}秒</Tag>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)', marginTop: '4px' }}>
                {currentFrameData.descriptionEn}
              </div>
            </div>
          )}

          {currentFrameData ? (
            <div
              style={{
                marginTop: 12,
                padding: 14,
                border: '1px solid rgba(233, 69, 96, .28)',
                background: 'linear-gradient(145deg, rgba(15,18,26,.96), rgba(30,24,27,.93))',
                boxShadow: 'inset 3px 0 0 #e94560',
                color: '#f6efe5',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                <div>
                  <div style={{ fontFamily: 'Georgia, serif', fontSize: 15, letterSpacing: '.04em' }}>
                    Identity Continuity Desk
                  </div>
                  <div style={{ color: '#9997a2', fontSize: 11, marginTop: 2 }}>
                    参考身份是事实；服装、雨水与疲态是本场状态
                  </div>
                </div>
                <Space size={4} wrap>
                  {newestAttempt ? (
                    <Tag color={newestAttempt.is_degraded ? 'warning' : 'success'}>
                      {newestAttempt.is_degraded ? '临时降级·身份不可信' : 'Kontext 正式生成'}
                    </Tag>
                  ) : <Tag>尚未生成</Tag>}
                  {renderState?.stale ? <Tag color="orange">输入已变化·需重新生成</Tag> : null}
                </Space>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8, marginTop: 12 }}>
                {renderIdentities.map((identity) => {
                  const asset = characterAssets.find((item) => item.id === identity.reference_asset_id)
                  return (
                    <div
                      key={identity.reference_asset_id}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '44px 1fr',
                        gap: 9,
                        padding: 8,
                        border: '1px solid rgba(255,255,255,.1)',
                        background: 'rgba(255,255,255,.035)',
                      }}
                    >
                      <div style={{ width: 44, height: 54, overflow: 'hidden', background: '#11151d' }}>
                        {identity.reference_image_url || asset?.image_url ? (
                          <img
                            src={mediaUrl(identity.reference_image_url || asset?.image_url)}
                            alt={identity.character_name}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          />
                        ) : null}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 700 }}>{identity.character_name}</div>
                        <div style={{ fontSize: 10, color: '#8e8c96', marginTop: 2 }}>
                          Reference {identity.reference_order}{identity.legacy_reference ? ' · Legacy' : ' · Selected'}
                        </div>
                        <div style={{ fontSize: 10, color: '#c8c1b8', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {identity.identity_anchor}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {candidateAttempt ? (
                <IdentityRiskPanel
                  attempt={candidateAttempt}
                  identities={renderIdentities}
                  candidateImageUrl={candidateImageUrl}
                  mediaUrl={mediaUrl}
                />
              ) : null}

              {candidateAttempt ? (
                <div style={{ marginTop: 12, borderTop: '1px solid rgba(255,255,255,.1)', paddingTop: 12 }}>
                  <Button
                    type="primary"
                    icon={<CheckOutlined />}
                    block
                    loading={renderBusy}
                    onClick={() => handleAcceptCandidate(candidateAttempt.id)}
                    style={{ background: '#e94560', borderColor: '#e94560', fontWeight: 700 }}
                  >
                    通过并设为正式分镜
                  </Button>
                  <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr', gap: 8, marginTop: 8 }}>
                    <Select value={rejectReason} onChange={setRejectReason} size="small">
                      {REJECTION_OPTIONS.map(([value, label]) => (
                        <Option key={value} value={value}>{label}</Option>
                      ))}
                    </Select>
                    <Input
                      size="small"
                      value={rejectNote}
                      onChange={(event) => setRejectNote(event.target.value)}
                      placeholder="可选：记录具体偏差，供下一轮判断"
                    />
                  </div>
                  <Space style={{ marginTop: 8 }} wrap>
                    <Button size="small" danger onClick={() => handleRejectCandidate(candidateAttempt.id)}>
                      驳回候选
                    </Button>
                    <Button size="small" onClick={() => handleRetryCandidate(candidateAttempt.id)}>
                      按原身份重试
                    </Button>
                    <Checkbox checked={reuseSeed} onChange={(event) => setReuseSeed(event.target.checked)}>
                      <span style={{ color: '#b8b4bd', fontSize: 11 }}>复用 seed</span>
                    </Checkbox>
                  </Space>
                </div>
              ) : newestAttempt?.status === 'failed' ? (
                <div style={{ marginTop: 12, color: '#ff9a9a', fontSize: 11 }}>
                  生成失败：{newestAttempt.error?.message || newestAttempt.error?.code || '未知错误'}
                </div>
              ) : null}
            </div>
          ) : null}
        </Card>

        {/* ===== 右栏：分镜编辑 (55%) ===== */}
        <Card
          style={{
            flex: 1,
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '16px', height: '100%', overflowY: 'auto' }}
        >
          {currentFrameData ? (
            <>
              {/* 分镜编号 */}
              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '12px' }}>分镜编号</Text>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#e94560', marginTop: '2px' }}>
                  #{currentFrameData.number} / {frames.length}
                </div>
              </div>

              {/* 分镜描述 */}
              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  📝 分镜描述 / Description
                </Text>
                <TextArea
                  value={currentFrameData.description}
                  onChange={(e) => updateCurrentField('description', e.target.value)}
                  autoSize={{ minRows: 2, maxRows: 3 }}
                  style={{
                    marginTop: '6px',
                    background: 'var(--vf-surface-muted)',
                    borderColor: 'var(--vf-border)',
                    color: 'var(--vf-text)',
                    borderRadius: '4px 4px 0 0',
                  }}
                />
                <div className="prompt-translation">
                  🔄 {currentFrameData.descriptionEn}
                </div>
              </div>

              <div
                style={{
                  marginBottom: 16,
                  padding: 12,
                  border: '1px solid rgba(219, 173, 87, .32)',
                  background: 'linear-gradient(135deg, rgba(219,173,87,.06), rgba(233,69,96,.035))',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <div>
                    <Text style={{ color: 'var(--vf-text)', fontSize: 13, fontWeight: 700 }}>
                      Scene Look State
                    </Text>
                    <div style={{ color: 'var(--vf-text-muted)', fontSize: 10, marginTop: 2 }}>
                      只描述本场可变外观，不写脸型、年龄或体型
                    </div>
                  </div>
                  <Button
                    size="small"
                    loading={lookSaving}
                    disabled={!currentSceneRecord?.id || !renderIdentities.length}
                    onClick={saveLookState}
                  >
                    保存本场状态
                  </Button>
                </div>
                {renderIdentities.map((identity) => (
                  <div key={identity.character_asset_id} style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 11, color: '#dbad57', marginBottom: 6 }}>
                      {identity.character_name} · {identity.character_asset_id}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
                      {LOOK_FIELDS.map(([field, label]) => (
                        <Input
                          key={field}
                          size="small"
                          value={lookDraft[identity.character_asset_id]?.[field] || ''}
                          onChange={(event) => updateLookField(identity.character_asset_id, field, event.target.value)}
                          placeholder={`${label}（可留空）`}
                        />
                      ))}
                    </div>
                  </div>
                ))}
                {!renderIdentities.length ? (
                  <div style={{ color: 'var(--vf-text-muted)', fontSize: 11, marginTop: 10 }}>
                    请先完成角色定妆选择并关联到当前分镜。
                  </div>
                ) : null}
              </div>

              <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

              {/* 关联资产 */}
              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🎭 关联资产 / Linked Assets
                </Text>
                <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                  <div style={{ flex: 1 }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>角色</Text>
                    <Select
                      size="small"
                      value={currentFrameData.character || undefined}
                      onChange={(v) => updateCurrentField('character', v)}
                      style={{ width: '100%', marginTop: '2px' }}
                    >
                      {linkCharacters.map((n) => (
                        <Option key={n} value={n}>{n}</Option>
                      ))}
                    </Select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>场景</Text>
                    <Select
                      size="small"
                      value={currentFrameData.scene || undefined}
                      onChange={(v) => updateCurrentField('scene', v)}
                      style={{ width: '100%', marginTop: '2px' }}
                    >
                      {linkScenes.map((n) => (
                        <Option key={n} value={n}>{n}</Option>
                      ))}
                    </Select>
                  </div>
                </div>
              </div>

              <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

              {/* 镜头参数 */}
              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🎥 镜头参数 / Camera Settings
                </Text>
                <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                  <div style={{ flex: 1 }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>镜头类型</Text>
                    <Select
                      size="small"
                      value={currentFrameData.shotType}
                      onChange={(v) => updateCurrentField('shotType', v)}
                      style={{ width: '100%', marginTop: '2px' }}
                    >
                      {shotTypes.map((t) => (
                        <Option key={t} value={t}>{t}</Option>
                      ))}
                    </Select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>机位角度</Text>
                    <Select
                      size="small"
                      value={currentFrameData.angle}
                      onChange={(v) => updateCurrentField('angle', v)}
                      style={{ width: '100%', marginTop: '2px' }}
                    >
                      {angles.map((a) => (
                        <Option key={a} value={a}>{a}</Option>
                      ))}
                    </Select>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                  <div style={{ flex: 1 }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>运动方式</Text>
                    <Select
                      size="small"
                      value={currentFrameData.movement}
                      onChange={(v) => updateCurrentField('movement', v)}
                      style={{ width: '100%', marginTop: '2px' }}
                    >
                      {movements.map((m) => (
                        <Option key={m} value={m}>{m}</Option>
                      ))}
                    </Select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>时长（秒）</Text>
                    <Input
                      size="small"
                      value={currentFrameData.duration}
                      onChange={(e) => {
                        const n = Number(e.target.value)
                        updateCurrentField('duration', Number.isFinite(n) ? n : currentFrameData.duration)
                      }}
                      style={{ marginTop: '2px' }}
                    />
                  </div>
                </div>
              </div>

              <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

              {/* 生成提示词 */}
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
                    ✨ 生成提示词 / Generation Prompt
                  </Text>
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={polishing}
                    disabled={previewBusy}
                    onClick={handlePolish}
                  >
                    润色
                  </Button>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)', marginBottom: '6px' }}>
                  LLM 自动生成，可手动微调；润色后预览再「应用」
                </div>
                <TextArea
                  value={currentFrameData.promptCn}
                  onChange={(e) => updateCurrentField('promptCn', e.target.value)}
                  autoSize={{ minRows: 3, maxRows: 5 }}
                  style={{
                    background: 'var(--vf-surface-muted)',
                    borderColor: 'var(--vf-border)',
                    color: 'var(--vf-text)',
                    borderRadius: '4px 4px 0 0',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                  }}
                />
                <div className="prompt-translation">
                  🔄 {currentFrameData.promptEn}
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
                  <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>EN · </Text>
                    {polishPreview.prompt_en}
                  </div>
                  {polishPreview.motion_prompt_en ? (
                    <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)', marginBottom: '6px' }}>
                      <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>Motion · </Text>
                      {polishPreview.motion_prompt_en}
                    </div>
                  ) : null}
                  <div style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>
                    <Text style={{ color: 'var(--vf-text-muted)', fontSize: '11px' }}>Avoid · </Text>
                    {polishPreview.avoid}
                  </div>
                </div>
              )}

              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🖼 静图提示词 / Still Prompt
                </Text>
                <TextArea
                  value={currentFrameData.promptEn}
                  onChange={(e) => updateCurrentField('promptEn', e.target.value)}
                  placeholder="ComfyUI 将使用英文提示词出图（含身份锁）"
                  autoSize={{ minRows: 3, maxRows: 5 }}
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
                  🎞 运动提示词 / I2V Motion
                </Text>
                <TextArea
                  value={currentFrameData.motionPromptEn || ''}
                  onChange={(e) => updateCurrentField('motionPromptEn', e.target.value)}
                  placeholder="只写动作、一个运镜、约 5 秒。不要重写脸和衣服。生成镜头视频时使用。"
                  autoSize={{ minRows: 2, maxRows: 5 }}
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

              <div
                style={{
                  marginBottom: 16,
                  padding: 12,
                  border: '1px solid var(--vf-border)',
                  borderRadius: 6,
                  background: 'rgba(114, 46, 209, 0.06)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <Text style={{ color: 'var(--vf-text)', fontSize: 13, fontWeight: 600 }}>
                    H3 I2VA 最终提示词
                  </Text>
                  <Space size={4} wrap>
                    <Tag color="purple">MiniMax-H3 官方格式</Tag>
                    {h3Artifact?.mode ? <Tag>{String(h3Artifact.mode).toUpperCase()}</Tag> : null}
                    <Tag>{H3_DURATION_SEC.toFixed(2)} 秒</Tag>
                    {h3Artifact?.stale ? (
                      <Tag color="orange">输入已变更·需重编译</Tag>
                    ) : h3Artifact?.validation_json?.valid ? (
                      <Tag color="green">结构有效</Tag>
                    ) : h3Artifact ? (
                      <Tag color="red">校验失败</Tag>
                    ) : (
                      <Tag>尚未编译</Tag>
                    )}
                    {h3Artifact?.status === 'locked' ? <Tag color="blue">已锁定</Tag> : null}
                    {h3Artifact?.is_user_edited ? <Tag color="cyan">人工编辑</Tag> : null}
                  </Space>
                </div>
                <div style={{ fontSize: 11, color: 'var(--vf-text-muted)', margin: '6px 0 8px' }}>
                  由项目视觉圣经、已选定角色、当前分镜和对白编译。可手改；任何上游输入变化都会标记过期。
                  {h3Artifact?.guide_version ? ` 指南：${h3Artifact.guide_version}。` : ''}
                  {h3Artifact?.provider ? ` 编译模型：${h3Artifact.provider}。` : ''}
                </div>
                <TextArea
                  value={h3Content}
                  onChange={(e) => {
                    setH3Content(e.target.value)
                    setH3Edited(true)
                  }}
                  placeholder="点击“编译 H3”生成 integrated_multimodal_description / overall_soundscape / non_diegetic_music"
                  autoSize={{ minRows: 7, maxRows: 16 }}
                  style={{
                    background: 'var(--vf-surface-muted)',
                    borderColor: 'var(--vf-border)',
                    color: 'var(--vf-text)',
                    fontFamily: 'monospace',
                    fontSize: 11,
                  }}
                />
                {h3Artifact && !h3Artifact.validation_json?.valid ? (
                  <div style={{ marginTop: 8 }}>
                    {(h3Artifact.validation_json?.issues || []).map((issue, index) => (
                      <div key={`${issue.code || 'issue'}-${index}`} style={{ color: '#ff7875', fontSize: 11 }}>
                        {issue.code ? `${issue.code}: ` : ''}{issue.message || JSON.stringify(issue)}
                      </div>
                    ))}
                  </div>
                ) : null}
                <Space style={{ marginTop: 10 }} wrap>
                  <Button size="small" loading={h3Compiling} onClick={compileH3}>
                    {h3Artifact?.stale ? '重新编译 H3' : '编译 H3'}
                  </Button>
                  <Button size="small" disabled={!h3Artifact || h3Artifact.stale} loading={h3Saving} onClick={() => saveH3('draft')}>
                    保存修改
                  </Button>
                  <Button
                    size="small"
                    icon={<CheckOutlined />}
                    disabled={!h3Artifact?.validation_json?.valid || h3Artifact?.stale || h3Edited}
                    loading={h3Saving}
                    onClick={() => saveH3('locked')}
                  >
                    锁定版本
                  </Button>
                </Space>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                  🚫 负面提示词 / Negative Prompt
                </Text>
                <TextArea
                  value={currentFrameData.negativePrompt || ''}
                  onChange={(e) => updateCurrentField('negativePrompt', e.target.value)}
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

              {/* 操作按钮 */}
              <Space direction="vertical" style={{ width: '100%' }}>
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  onClick={handleGenerateFrame}
                  loading={renderBusy || ['queued', 'running'].includes(newestAttempt?.status)}
                  disabled={polishing}
                  block
                  style={{ background: '#e94560', borderColor: '#e94560' }}
                >
                  用 Kontext 生成身份一致候选
                </Button>
                <Button
                  icon={<ThunderboltOutlined />}
                  onClick={handleGenerateVideo}
                  loading={currentFrameData?.videoStatus === 'generating'}
                  disabled={!canGenerateVideo || polishing || previewBusy}
                  block
                >
                  {canGenerateVideo ? '生成镜头视频' : '请先通过一张候选'}
                </Button>
                {currentFrameData?.videoError ? (
                  <Text type="danger" style={{ fontSize: 12 }}>{currentFrameData.videoError}</Text>
                ) : null}
                <div style={{ display: 'flex', gap: '8px' }}>
                  <Button icon={<CopyOutlined />} style={{ flex: 1 }} onClick={handleDuplicateFrame}>
                    复制
                  </Button>
                  <Button icon={<CheckOutlined />} style={{ flex: 1 }} onClick={handleConfirmFrame}>
                    确认
                  </Button>
                </div>
              </Space>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--vf-text-muted)' }}>
              请从时间轴选择一个分镜
            </div>
          )}
        </Card>
      </div>

      {/* 一致性检测栏（元数据启发式；无问题时不展示假告警） */}
      {consistencyIssues.length > 0 && (
        <div
          className="smart-suggestion"
          style={{
            marginTop: '16px',
            background: 'rgba(255, 170, 0, 0.1)',
            borderColor: 'rgba(255, 170, 0, 0.3)',
          }}
        >
          <div className="content" style={{ color: '#ffaa00', flex: 1 }}>
            <BulbOutlined style={{ marginRight: '8px' }} />
            {consistencyIssues.slice(0, 3).map((item, idx) => (
              <div key={`${item.frame_id}-${idx}`} style={{ marginBottom: idx < Math.min(consistencyIssues.length, 3) - 1 ? 4 : 0 }}>
                一致性检测：{item.issue}
                {item.suggestion ? ` — ${item.suggestion}` : ''}
              </div>
            ))}
            {consistencyIssues.length > 3 && (
              <div style={{ opacity: 0.8 }}>另有 {consistencyIssues.length - 3} 条提示</div>
            )}
          </div>
          <Space>
            <Button
              size="small"
              onClick={async () => {
                try {
                  const issues = await storyboardApi.consistencyCheck(projectId)
                  setConsistencyIssues(Array.isArray(issues) ? issues : [])
                  message.success('已重新检测')
                } catch (e) {
                  message.warning(e.message || '检测失败')
                }
              }}
            >
              重新检测
            </Button>
            <Button size="small" onClick={() => setConsistencyIssues([])}>
              忽略
            </Button>
          </Space>
        </div>
      )}

      {/* 批量操作栏 */}
      <div
        style={{
          marginTop: '16px',
          padding: '12px 16px',
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Checkbox checked={selectedFrameIds.length > 0 && selectedFrameIds.length === frames.length} indeterminate={selectedFrameIds.length > 0 && selectedFrameIds.length < frames.length} onChange={toggleSelectAll}>
            全选
          </Checkbox>
          <span style={{ color: 'var(--vf-text-secondary)', fontSize: '13px' }}>
            已选 {selectedFrameIds.length} / {frames.length} 帧
          </span>
        </div>
        <Space>
          <Button size="small" icon={<ExportOutlined />} onClick={handleExportPrompts}>导出提示词</Button>
          <Button size="small" icon={<DeleteOutlined />} onClick={handleDeleteSelected}>删除选中</Button>
        </Space>
      </div>

      {/* 底部操作栏 */}
      <div className="bottom-bar">
        <Button icon={<LeftOutlined />} onClick={handlePrev}>
          上一步
        </Button>
        <div style={{ color: 'var(--vf-text-muted)', fontSize: '13px' }}>
          当前步骤完成度：{Math.round((frames.filter((f) => f.status === 'completed').length / Math.max(frames.length, 1)) * 100)}%（{frames.filter((f) => f.status === 'completed').length}/{frames.length} 帧）
        </div>
        <Button
          type="primary"
          icon={<RightOutlined />}
          onClick={handleNext}
          style={{ background: '#e94560', borderColor: '#e94560' }}
        >
          下一步：成片合成
        </Button>
      </div>
    </div>
  )
}

export default Storyboard
