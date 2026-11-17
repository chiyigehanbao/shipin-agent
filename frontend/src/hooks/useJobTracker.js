import React, { useEffect, useRef, useState } from 'react'
import { Button, notification } from 'antd'
import { useNavigate } from 'react-router-dom'
import { jobsApi } from '../services/api.js'

function describeError(err = '') {
  const s = String(err)
  if (!s) return '未知错误'
  if (s.includes('comfyui_unavailable')) return 'ComfyUI 未启动或不可用，请稍后重试'
  if (s.includes('characters_not_ready')) return '有角色未完成定妆，请先补齐定妆图'
  if (s.includes('poll timeout')) return '生成超时，可重试'
  if (s.includes('server_restarted')) return '服务重启导致中断，可重试'
  if (s.includes('ffmpeg failed')) return '视频合成失败（ffmpeg），请检查环境'
  if (s.includes('bge-m3') || s.includes('embed')) return '检索模型未安装'
  if (s.includes('model not ready')) return '模型权重未就绪'
  if (s.includes('MiniMax') || s.includes('minimax')) return '视频生成服务异常，请重试'
  return s
}

export function useJobTracker(pollMs = 3000) {
  const [activeJobs, setActiveJobs] = useState([])
  const known = useRef(new Map())
  const navigate = useNavigate()

  useEffect(() => {
    let dead = false

    const tick = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const list = await jobsApi.list({ status: 'active', limit: 50 })
        if (dead) return
        const ids = new Set(list.map((j) => j.id))
        for (const [id, prev] of known.current.entries()) {
          if (!ids.has(id) && (prev === 'queued' || prev === 'running')) {
            try {
              const j = await jobsApi.get(id)
              if (j.status === 'completed') {
                notification.success({
                  message: `${j.title || '任务'}已完成`,
                  description: j.link_path ? '点击前往查看' : undefined,
                  onClick: () => {
                    if (j.link_path) navigate(j.link_path)
                  },
                })
                window.dispatchEvent(
                  new CustomEvent('vf-job-completed', { detail: j }),
                )
              } else if (j.status === 'failed') {
                const errMsg = describeError(j.error || '')
                notification.error({
                  message: `${j.title || '任务'}失败`,
                  description: errMsg,
                  duration: 10,
                  btn: React.createElement(
                    Button,
                    {
                      size: 'small',
                      onClick: async () => {
                        try {
                          await jobsApi.retry(id)
                          notification.success({ message: '已重新提交任务，稍后在看板查看' })
                          known.current.delete(id)
                          await tick()
                        } catch (e) {
                          notification.error({ message: '重试失败', description: e.message })
                        }
                      },
                    },
                    '重试',
                  ),
                })
              }
            } catch {
              /* ignore */
            }
          }
        }
        const next = new Map()
        for (const j of list) next.set(j.id, j.status)
        known.current = next
        setActiveJobs(list)
      } catch {
        /* keep last */
      }
    }

    tick()
    const t = setInterval(tick, pollMs)
    const onVis = () => {
      if (document.visibilityState === 'visible') tick()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      dead = true
      clearInterval(t)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [pollMs, navigate])

  return { activeJobs }
}
