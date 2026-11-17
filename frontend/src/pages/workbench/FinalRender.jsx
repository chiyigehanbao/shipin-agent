import React, { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Card,
  Button,
  Input,
  Select,
  List,
  Tag,
  Space,
  Typography,
  Divider,
  Switch,
  message,
  Progress,
} from 'antd'
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  DownloadOutlined,
  ExportOutlined,
  LeftOutlined,
  RightOutlined,
  SoundOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import StepProgress from '../../components/StepProgress.jsx'
import useProjectStore from '../../store/projectStore.js'
import { mediaUrl, renderApi, projectsApi, monitorApi } from '../../services/api.js'

const { Option } = Select
const { Title, Text } = Typography

// 第四步：成片合成
// 三栏布局：集数列表 + 视频预览 + 合成参数
function FinalRender() {
  const navigate = useNavigate()
  const { projectId } = useParams()
  const { setCurrentStep } = useProjectStore()

  const [currentEpisode, setCurrentEpisode] = useState('__all__')
  const [isPlaying, setIsPlaying] = useState(false)
  const [isRendering, setIsRendering] = useState(false)
  const [renderProgress, setRenderProgress] = useState(0)
  const [videoUrl, setVideoUrl] = useState(null)
  const [engine, setEngine] = useState('edge')

  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [bgmEnabled, setBgmEnabled] = useState(false)
  const [bgmCaption, setBgmCaption] = useState('')
  const [aceStepOnline, setAceStepOnline] = useState(null)

  const [subtitleEnabled, setSubtitleEnabled] = useState(false)

  const [episodes, setEpisodes] = useState([])
  const videoRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!projectId) return
      try {
        const list = await renderApi.episodes(projectId)
        if (cancelled) return
        setEpisodes(Array.isArray(list) ? list : [])
        const full = (list || []).find((e) => e.id === '__all__')
        if (full?.video_url) setVideoUrl(full.video_url)
        if (list?.length) setCurrentEpisode(list[0].id)
      } catch (e) {
        message.warning(`加载成片列表失败：${e.message}`)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    monitorApi
      .acestep()
      .then((s) => {
        if (!cancelled) setAceStepOnline(Boolean(s?.online))
      })
      .catch(() => {
        if (!cancelled) setAceStepOnline(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const currentEp = episodes.find((e) => e.id === currentEpisode)

  // 选中集时加载该集成片预览（每集可独立合成）
  useEffect(() => {
    setVideoUrl(currentEp?.video_url || null)
  }, [currentEpisode, episodes])

  const getStatusTag = (status) => {
    switch (status) {
      case 'completed':
        return <Tag color="success">已合成</Tag>
      case 'rendering':
      case 'queued':
      case 'running':
        return <Tag color="processing">合成中</Tag>
      case 'pending':
        return <Tag>待合成</Tag>
      default:
        return <Tag>{status || '未知'}</Tag>
    }
  }

  const pollJob = async (jobId) => {
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      const st = await renderApi.status(projectId, jobId)
      setRenderProgress(st.progress || 0)
      if (st.status === 'completed') {
        setVideoUrl(st.output_url || null)
        const list = await renderApi.episodes(projectId)
        setEpisodes(Array.isArray(list) ? list : [])
        return 'ok'
      }
      if (st.status === 'failed' || st.status === 'cancelled') {
        throw new Error(st.error || '合成失败')
      }
    }
    throw new Error('合成超时')
  }

  const renderOne = async (episodeId) => {
    const res = await renderApi.start(projectId, {
      episode_id: episodeId,
      voice_enabled: voiceEnabled,
      subtitle_enabled: subtitleEnabled,
      engine,
      bgm_enabled: bgmEnabled,
      bgm_caption: bgmCaption,
      resolution: '1080p',
      fps: 24,
    })
    const jobId = res.job_id || res.task_id
    await pollJob(jobId)
  }

  const handleRenderCurrent = async () => {
    if (!projectId) return
    setIsRendering(true)
    setRenderProgress(5)
    try {
      await renderOne(currentEpisode || '__all__')
      message.success('合成完成！')
    } catch (e) {
      message.error(`合成失败：${e.message}`)
    } finally {
      setIsRendering(false)
    }
  }

  const handleRenderAll = async () => {
    if (!projectId) return
    const sceneEps = episodes.filter(
      (e) => e.id !== '__all__' && (e.frame_count ?? e.frames ?? 0) > 0,
    )
    const targets = [...sceneEps.map((e) => e.id), '__all__']
    if (!targets.length) return
    setIsRendering(true)
    setRenderProgress(5)
    let done = 0
    const failed = []
    try {
      for (let i = 0; i < targets.length; i++) {
        const id = targets[i]
        try {
          await renderOne(id)
          done += 1
          setCurrentEpisode(id)
          message.loading(`成片合成中 ${done}/${targets.length}...`, 0.8)
        } catch (e) {
          const title =
            id === '__all__'
              ? '整片'
              : episodes.find((x) => x.id === id)?.title || id
          failed.push(`${title}：${e.message}`)
        }
      }
      setCurrentEpisode('__all__')
      if (failed.length) {
        message.warning(`合成结束：成功 ${done}/${targets.length}，失败 ${failed.length}（${failed.join('；')}）`)
      } else {
        message.success(`全部合成完成（${targets.length} 项）`)
      }
    } finally {
      setIsRendering(false)
    }
  }

  const togglePlay = () => {
    const v = videoRef.current
    if (v) {
      if (v.paused) {
        v.play()
        setIsPlaying(true)
      } else {
        v.pause()
        setIsPlaying(false)
      }
      return
    }
    setIsPlaying((p) => !p)
  }

  const handleDownload = () => {
    if (!videoUrl) {
      message.warning('暂无成片可下载，请先合成')
      return
    }
    const a = document.createElement('a')
    a.href = mediaUrl(videoUrl)
    a.download = `visionforge-${projectId}.mp4`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const handleExportPackage = async () => {
    if (!projectId) return
    try {
      const list = await renderApi.episodes(projectId)
      const blob = new Blob([JSON.stringify(list, null, 2)], {
        type: 'application/json;charset=utf-8',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `visionforge-${projectId}-project.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success('工程数据已导出')
    } catch (e) {
      message.error(`导出失败：${e.message}`)
    }
  }

  const handleComplete = async () => {
    try {
      const res = await projectsApi.complete(projectId)
      const ing = res?.ingested
      message.success(
        ing
          ? `项目已完成，已沉淀 ${ing.total ?? 0} 条经验到知识库 🎉`
          : '项目已完成 🎉',
      )
    } catch (e) {
      message.warning(`项目已标记完成（经验沉淀未执行：${e.message}）`)
    }
    navigate('/workbench')
  }

  // 上一步
  const handlePrev = () => {
    setCurrentStep(3)
    navigate(`/workbench/${projectId}/storyboard`)
  }

  // 步骤点击
  const handleStepChange = (step) => {
    if (step === 0) {
      setCurrentStep(1)
      navigate(`/workbench/${projectId}/script`)
    } else if (step === 1) {
      setCurrentStep(2)
      navigate(`/workbench/${projectId}/assets`)
    } else if (step === 2) {
      setCurrentStep(3)
      navigate(`/workbench/${projectId}/storyboard`)
    }
  }

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
      <StepProgress current={4} onChange={handleStepChange} />

      {/* 页面标题 */}
      <div className="bilingual-title" style={{ marginBottom: '16px' }}>
        <span className="cn" style={{ fontSize: '18px', fontWeight: 600 }}>
          成片合成
        </span>
        <span className="en">Final Render</span>
      </div>

      {/* 三栏布局 */}
      <div style={{ display: 'flex', gap: '16px', minHeight: '550px' }}>
        {/* ===== 左栏：集数列表 (20%) ===== */}
        <Card
          style={{
            flex: '0 0 200px',
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
            剧集列表
          </div>
          <List
            dataSource={episodes}
            renderItem={(ep) => (
              <List.Item
                key={ep.id}
                onClick={() => setCurrentEpisode(ep.id)}
                style={{
                  padding: '10px 12px',
                  marginBottom: '4px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  background:
                    currentEpisode === ep.id
                      ? 'rgba(233, 69, 96, 0.15)'
                      : 'transparent',
                  border:
                    currentEpisode === ep.id
                      ? '1px solid #e94560'
                      : '1px solid transparent',
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ width: '100%' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '4px',
                    }}
                  >
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--vf-text)' }}>
                      第{ep.number}集 {ep.title}
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)', marginBottom: '6px' }}>
                    {ep.title_en || ep.titleEn || ''}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    {getStatusTag(ep.status)}
                    <span style={{ fontSize: '11px', color: 'var(--vf-text-muted)' }}>
                      {ep.frame_count ?? ep.frames ?? 0} 帧
                    </span>
                  </div>
                </div>
              </List.Item>
            )}
          />

          <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

          {/* 批量操作 */}
          <Space direction="vertical" style={{ width: '100%' }}>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={handleRenderCurrent}
              loading={isRendering}
              block
              size="small"
              style={{ background: '#e94560', borderColor: '#e94560' }}
            >
              合成当前集
            </Button>
            <Button icon={<PlayCircleOutlined />} block size="small" onClick={handleRenderAll}>
              全部合成
            </Button>
            <Button icon={<DownloadOutlined />} block size="small" onClick={handleDownload}>
              全部导出
            </Button>
          </Space>
        </Card>

        {/* ===== 中栏：视频预览 (55%) ===== */}
        <Card
          style={{
            flex: 1,
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '16px', height: '100%', display: 'flex', flexDirection: 'column' }}
        >
          {/* 视频播放器 */}
          <div style={{ flex: 1, position: 'relative' }}>
            <div
              style={{
                width: '100%',
                aspectRatio: '16/9',
                background: '#000000',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              {mediaUrl(videoUrl) ? (
                <video
                  ref={videoRef}
                  src={mediaUrl(videoUrl)}
                  controls
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }}
                />
              ) : (
              <div
                style={{
                  width: '100%',
                  height: '100%',
                  background: 'linear-gradient(135deg, #f8fafc 0%, #eef2f7 50%, #f8fafc 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  position: 'relative',
                }}
              >
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '64px', marginBottom: '12px' }}>🎬</div>
                  <div style={{ color: 'var(--vf-text-secondary)', fontSize: '14px' }}>
                    {currentEp?.number === 0 ? '整片' : `第${currentEp?.number}集`}{currentEp?.title}
                  </div>
                  <div style={{ color: 'var(--vf-text-muted)', fontSize: '12px', marginTop: '4px' }}>
                    {currentEp?.title_en || currentEp?.titleEn || '合成后在此预览'}
                  </div>
                </div>
              </div>
              )}

              {/* 中央播放按钮 */}
              <Button
                type="text"
                icon={isPlaying ? <PauseCircleOutlined style={{ fontSize: '48px' }} /> : <PlayCircleOutlined style={{ fontSize: '48px' }} />}
                onClick={togglePlay}
                style={{
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  color: 'rgba(255,255,255,0.8)',
                  fontSize: '48px',
                  height: 'auto',
                  background: 'transparent',
                }}
              />
            </div>

            {/* 播放控制条 */}
            <div
              style={{
                marginTop: '12px',
                padding: '12px',
                background: 'var(--vf-surface-muted)',
                borderRadius: '6px',
              }}
            >
              {/* 进度条 */}
              <div style={{ marginBottom: '8px' }}>
                <Progress
                  percent={isRendering ? renderProgress : (videoUrl ? 100 : 0)}
                  showInfo={false}
                  strokeColor="#e94560"
                  trailColor="var(--vf-border)"
                  size="small"
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--vf-text-muted)' }}>
                    {currentEp?.duration || '00:00'}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--vf-text-muted)' }}>
                    {currentEp?.duration || '合成后显示时长'}
                  </span>
                </div>
              </div>

              {/* 控制按钮 */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Space>
                  <Button type="text" icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />} onClick={togglePlay} style={{ color: '#fff' }} />
                  <span style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>
                    {currentEp?.frame_count ?? currentEp?.frames ?? 0} 个分镜 · {currentEp?.title || '整片'} {currentEp?.status === 'completed' ? '· 已合成' : ''}
                  </span>
                </Space>
                <Space>
                  <SoundOutlined style={{ color: 'var(--vf-text-secondary)' }} />
                  <span style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>音量</span>
                </Space>
              </div>
            </div>
          </div>

          {/* 合成进度 */}
          {isRendering && (
            <div style={{ marginTop: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>合成进度</span>
                <span style={{ fontSize: '12px', color: '#e94560' }}>{renderProgress}%</span>
              </div>
              <Progress
                percent={renderProgress}
                status="active"
                strokeColor="#e94560"
                trailColor="var(--vf-border)"
                showInfo={false}
              />
            </div>
          )}
        </Card>

        {/* ===== 右栏：合成参数 (25%) ===== */}
        <Card
          style={{
            flex: '0 0 280px',
            background: 'var(--vf-surface)',
            border: '1px solid var(--vf-border)',
            borderRadius: '8px',
          }}
          bodyStyle={{ padding: '16px', height: '100%', overflowY: 'auto' }}
        >
          {/* 基础信息 */}
          <div style={{ marginBottom: '16px' }}>
            <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
              📋 基础信息 / Info
            </Text>
            <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--vf-text-secondary)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                <span>分辨率</span>
                <span style={{ color: 'var(--vf-text)' }}>1080p</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                <span>帧率</span>
                <span style={{ color: 'var(--vf-text)' }}>24fps</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                <span>总时长</span>
                <span style={{ color: 'var(--vf-text)' }}>{currentEp?.duration}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                <span>分镜数</span>
                <span style={{ color: 'var(--vf-text)' }}>{currentEp?.frames} 帧</span>
              </div>
            </div>
          </div>

          <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

          {/* 音轨设置 */}
          <div style={{ marginBottom: '16px' }}>
            <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
              🔊 音轨设置 / Audio
            </Text>

            <div style={{ marginTop: '8px', marginBottom: '8px' }}>
              <Text style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>TTS 引擎</Text>
              <Select value={engine} onChange={setEngine} style={{ width: '100%', marginTop: 4 }} size="small">
                <Option value="edge">Edge TTS</Option>
                <Option value="voxcpm">VoxCPM</Option>
              </Select>
            </div>

            <div style={{ marginTop: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>配音</span>
                <Switch size="small" checked={voiceEnabled} onChange={setVoiceEnabled} />
              </div>
              <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)', marginTop: '2px' }}>
                开启后为每个分镜生成 TTS 配音
              </div>
            </div>

            <div style={{ marginTop: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '12px', color: 'var(--vf-text-secondary)' }}>
                  BGM（本地 ACE-Step 生成）
                </span>
                <Switch size="small" checked={bgmEnabled} onChange={setBgmEnabled} />
              </div>
              {bgmEnabled && (
                <>
                  <Input
                    size="small"
                    value={bgmCaption}
                    onChange={(e) => setBgmCaption(e.target.value)}
                    placeholder="描述配乐风格，如：cinematic ambient, emotional underscore, soft pads, instrumental"
                  />
                  <div
                    style={{ fontSize: '11px', marginTop: '4px', color: aceStepOnline ? '#52c41a' : '#e94560' }}
                  >
                    {aceStepOnline ? '● 本地 ACE-Step 在线，可生成配乐' : '● 本地 ACE-Step 未启动，配乐将被跳过（需在 beat 项目启动 acestep-api :8001）'}
                  </div>
                </>
              )}
            </div>
          </div>

          <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

          {/* 字幕设置 */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <Text style={{ color: 'var(--vf-text)', fontSize: '13px', fontWeight: 600 }}>
                📝 字幕设置 / Subtitles
              </Text>
              <Switch size="small" checked={subtitleEnabled} onChange={setSubtitleEnabled} />
            </div>

            {subtitleEnabled && (
              <div style={{ fontSize: '11px', color: 'var(--vf-text-muted)', marginTop: '4px' }}>
                开启后把每个分镜的对白烧录为字幕（默认样式）
              </div>
            )}
          </div>

          <Divider style={{ borderColor: 'var(--vf-border)', margin: '12px 0' }} />

          {/* 操作按钮 */}
          <Space direction="vertical" style={{ width: '100%' }}>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={handleRenderCurrent}
              loading={isRendering}
              block
              style={{ background: '#e94560', borderColor: '#e94560' }}
            >
              重新合成
            </Button>
            <Button icon={<DownloadOutlined />} block onClick={handleDownload}>
              下载 MP4
            </Button>
            <Button icon={<ExportOutlined />} block onClick={handleExportPackage}>
              导出工程包
            </Button>
          </Space>
        </Card>
      </div>

      {/* 底部操作栏 */}
      <div className="bottom-bar">
        <Button icon={<LeftOutlined />} onClick={handlePrev}>
          上一步
        </Button>
        <div style={{ color: 'var(--vf-text-muted)', fontSize: '13px' }}>
          项目完成度：{episodes.filter(e => e.status === 'completed').length}/{episodes.length} 集
        </div>
        <Button
          type="primary"
          icon={<FileTextOutlined />}
          onClick={handleComplete}
          style={{ background: '#10b981', borderColor: '#10b981', color: '#ffffff' }}
        >
          完成项目
        </Button>
      </div>
    </div>
  )
}

export default FinalRender
