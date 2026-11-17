import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Space, Spin, Tag, Upload, message } from 'antd'
import {
  CheckOutlined,
  CloudUploadOutlined,
  RobotOutlined,
  ScanOutlined,
} from '@ant-design/icons'
import { assetsApi, jobsApi } from '../services/api.js'
import './identity-reference.css'

const SOURCE_LABELS = {
  auto_crop: '自动裁脸',
  manual_crop: '手动裁剪',
  upload: '本地上传',
  generated: '标准身份照',
  legacy_full_reference: '整张定妆图',
}

export function clampSquareCrop({ x, y, size }) {
  const safeSize = Math.min(1, Math.max(0.1, Number(size) || 0.1))
  return {
    x: Math.min(1 - safeSize, Math.max(0, Number(x) || 0)),
    y: Math.min(1 - safeSize, Math.max(0, Number(y) || 0)),
    width: safeSize,
    height: safeSize,
  }
}

function errorText(error) {
  const code = error?.code || ''
  if (code === 'face_model_unavailable') return '本地人脸模型尚未就绪；仍可手动裁剪或上传。'
  if (code === 'identity_face_missing') return '没有识别到清晰人脸，请拖框手裁或上传正面身份照。'
  if (code === 'identity_crop_invalid') return '裁剪范围过小或越界，请重新拖选。'
  return error?.message || '身份引用操作失败'
}

export default function IdentityReferencePanel({ projectId, asset, mediaUrl, onChanged }) {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [crop, setCrop] = useState({ x: 0.25, y: 0.08, size: 0.5 })
  const [generatedJob, setGeneratedJob] = useState(null)
  const dragRef = useRef(null)

  const load = useCallback(async () => {
    if (!projectId || !asset?.id) return
    try {
      setError('')
      setState(await assetsApi.identityReference(projectId, asset.id))
    } catch (nextError) {
      setError(errorText(nextError))
    }
  }, [projectId, asset?.id])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!generatedJob?.id || !['queued', 'running'].includes(generatedJob.status)) return () => {}
    const timer = setInterval(async () => {
      try {
        const job = await jobsApi.get(generatedJob.id)
        setGeneratedJob(job)
        if (job.status === 'completed') {
          clearInterval(timer)
          await load()
          onChanged?.()
          message.success('标准身份照已生成，请检查后手动确认')
        } else if (job.status === 'failed') {
          clearInterval(timer)
          setError(`标准身份照生成失败：${job.error || '未知错误'}`)
        }
      } catch {
        // 保持任务状态，下一轮继续读取。
      }
    }, 1500)
    return () => clearInterval(timer)
  }, [generatedJob?.id, generatedJob?.status, load, onChanged])

  const run = async (key, action) => {
    setBusy(key)
    setError('')
    try {
      await action()
      await load()
    } catch (nextError) {
      setError(errorText(nextError))
    } finally {
      setBusy('')
    }
  }

  const pointerPosition = (event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    return {
      x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    }
  }

  const beginCrop = (event) => {
    const start = pointerPosition(event)
    dragRef.current = start
    event.currentTarget.setPointerCapture(event.pointerId)
    setCrop({ x: start.x, y: start.y, size: 0.1 })
  }

  const moveCrop = (event) => {
    if (!dragRef.current) return
    const point = pointerPosition(event)
    const dx = point.x - dragRef.current.x
    const dy = point.y - dragRef.current.y
    const size = Math.max(0.1, Math.abs(dx), Math.abs(dy))
    setCrop({
      x: dx < 0 ? dragRef.current.x - size : dragRef.current.x,
      y: dy < 0 ? dragRef.current.y - size : dragRef.current.y,
      size,
    })
  }

  const endCrop = () => { dragRef.current = null }
  const normalizedCrop = clampSquareCrop(crop)
  const reference = state?.reference
  const candidates = state?.candidates || []
  const faceReady = state?.face_model?.ready

  return (
    <section className="identity-desk" aria-label={`${asset.name} 身份引用工作台`}>
      <header className="identity-desk__header">
        <div>
          <div className="identity-desk__kicker">Face continuity control</div>
          <div className="identity-desk__title">{asset.name} · 身份底片工作台</div>
          <div className="identity-desk__subtitle">
            原定妆图负责选角，身份底片只保留脸、年龄感与稳定发型。候选必须人工确认后，分镜才会引用。
          </div>
        </div>
        <Space wrap>
          {reference ? <Tag color="success">身份版本 v{reference.version}</Tag> : <Tag color="warning">尚未净化</Tag>}
          <Tag color={faceReady ? 'cyan' : 'default'}>{faceReady ? '人脸模型就绪' : '人脸模型未就绪'}</Tag>
        </Space>
      </header>

      {error ? <Alert type="warning" showIcon message={error} style={{ margin: '14px 22px 0' }} /> : null}
      {!state ? <div style={{ padding: 50, textAlign: 'center' }}><Spin /></div> : (
        <div className="identity-desk__body">
          <div className="identity-desk__proofs">
            <div className="identity-section-title"><span>01 · 来源与当前底片</span><span>{candidates.length} pending</span></div>
            <div className="identity-proof-grid">
              <div className="identity-proof">
                <img src={mediaUrl(state.source_image_url)} alt={`${asset.name} 原定妆图`} />
                <span className="identity-proof__label">Casting source</span>
              </div>
              <div className="identity-proof">
                {reference?.image_url ? (
                  <img src={mediaUrl(reference.image_url)} alt={`${asset.name} 当前身份底片`} />
                ) : (
                  <div className="identity-proof__empty">整张定妆图仍是临时身份源<br />请从右侧制作净化底片</div>
                )}
                <span className="identity-proof__label">Identity master {reference ? `v${reference.version}` : '—'}</span>
              </div>
            </div>

            {candidates.length ? (
              <div className="identity-candidates">
                {candidates.map((candidate) => (
                  <article className="identity-candidate" key={candidate.id}>
                    <img src={mediaUrl(candidate.image_url)} alt="身份底片候选" />
                    <div className="identity-candidate__meta">
                      <div className="identity-candidate__source">{SOURCE_LABELS[candidate.source_type] || candidate.source_type}</div>
                      <div className="identity-candidate__quality">
                        {candidate.quality === 'good' ? '单脸清晰' : candidate.quality === 'review' ? '需要人工复核' : '尚未评分'}
                      </div>
                      <Button
                        size="small"
                        type="primary"
                        icon={<CheckOutlined />}
                        loading={busy === candidate.id}
                        onClick={() => run(candidate.id, async () => {
                          await assetsApi.confirmIdentityReference(projectId, asset.id, candidate.id)
                          onChanged?.()
                          message.success('身份底片已确认；新分镜将使用该版本')
                        })}
                        style={{ width: '100%', marginTop: 8, background: '#d94a3d' }}
                      >
                        确认为身份底片
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </div>

          <aside className="identity-desk__tools">
            <div className="identity-section-title"><span>02 · 制作净化底片</span><span>drag square</span></div>
            <div className="identity-toolbox">
              <div
                className="identity-crop-stage"
                onPointerDown={beginCrop}
                onPointerMove={moveCrop}
                onPointerUp={endCrop}
                onPointerCancel={endCrop}
              >
                <img src={mediaUrl(state.source_image_url)} alt="拖动裁剪身份区域" draggable="false" />
                <div
                  className="identity-crop-box"
                  style={{
                    left: `${normalizedCrop.x * 100}%`,
                    top: `${normalizedCrop.y * 100}%`,
                    width: `${normalizedCrop.width * 100}%`,
                    height: `${normalizedCrop.height * 100}%`,
                  }}
                />
              </div>
              <div className="identity-coordinates">
                {Object.entries(normalizedCrop).map(([key, value]) => (
                  <div className="identity-coordinate" key={key}>{key}<strong>{value.toFixed(3)}</strong></div>
                ))}
              </div>
              <div style={{ color: '#746d64', fontSize: 11, lineHeight: 1.55, marginTop: 8 }}>
                在原图上拖出正方形。保留完整发际线、双耳与下巴，尽量排除服装和背景。
              </div>
              <div className="identity-actions">
                <Button
                  icon={<ScanOutlined />}
                  disabled={!faceReady}
                  loading={busy === 'auto'}
                  onClick={() => run('auto', () => assetsApi.autoIdentityReference(projectId, asset.id))}
                >自动找脸</Button>
                <Button
                  type="primary"
                  icon={<CheckOutlined />}
                  loading={busy === 'crop'}
                  onClick={() => run('crop', () => assetsApi.cropIdentityReference(projectId, asset.id, normalizedCrop))}
                  style={{ background: '#1d2026' }}
                >生成手裁候选</Button>
                <Upload
                  accept="image/png,image/jpeg,image/webp"
                  showUploadList={false}
                  beforeUpload={(file) => {
                    run('upload', () => assetsApi.uploadIdentityReference(projectId, asset.id, file))
                    return false
                  }}
                >
                  <Button icon={<CloudUploadOutlined />} loading={busy === 'upload'} block>上传正面身份照</Button>
                </Upload>
                <Button
                  icon={<RobotOutlined />}
                  loading={busy === 'generate' || ['queued', 'running'].includes(generatedJob?.status)}
                  onClick={() => run('generate', async () => {
                    const job = await assetsApi.generateIdentityReference(projectId, asset.id)
                    setGeneratedJob(job)
                    message.info('标准身份照已进入后台队列')
                  })}
                >AI 标准身份照</Button>
              </div>
              {generatedJob ? (
                <div style={{ marginTop: 9, color: '#615b53', fontSize: 11 }}>
                  任务 {generatedJob.id} · {generatedJob.status === 'completed' ? '已完成' : generatedJob.status === 'failed' ? '失败' : '生成中'}
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      )}
    </section>
  )
}
