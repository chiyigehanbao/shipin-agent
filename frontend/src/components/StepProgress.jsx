import React from 'react'
import { Steps } from 'antd'
import {
  FileTextOutlined,
  AppstoreOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  CheckOutlined,
} from '@ant-design/icons'

// 四步流程进度条组件
// 在剧本工坊、资产生成、分镜故事板、成片合成四个页面顶部显示
// 可以点击已完成的步骤回退
function StepProgress({ current = 1, onChange }) {
  // 步骤配置
  const steps = [
    {
      title: '剧本工坊',
      subtitle: 'Script Workshop',
      icon: <FileTextOutlined />,
    },
    {
      title: '资产生成',
      subtitle: 'Asset Generation',
      icon: <AppstoreOutlined />,
    },
    {
      title: '分镜故事板',
      subtitle: 'Storyboard',
      icon: <PictureOutlined />,
    },
    {
      title: '成片合成',
      subtitle: 'Final Render',
      icon: <PlayCircleOutlined />,
    },
  ]

  // 自定义步骤图标
  const customIcon = (step, index) => {
    const stepNum = index + 1
    if (stepNum < current) {
      // 已完成 - 显示对勾
      return <CheckOutlined style={{ color: '#10b981' }} />
    }
    return step.icon
  }

  return (
    <div
      style={{
        background: 'var(--vf-surface)',
        border: '1px solid var(--vf-border)',
        borderRadius: '8px',
        padding: '20px 40px',
        marginBottom: '20px',
      }}
    >
      <Steps
        current={current - 1} // antd 的 current 从 0 开始
        onChange={onChange}
        items={steps.map((step, index) => ({
          title: (
            <div className="bilingual-title">
              <span className="cn" style={{ fontSize: '14px' }}>
                {step.title}
              </span>
              <span className="en">{step.subtitle}</span>
            </div>
          ),
          icon: customIcon(step, index),
          status:
            index + 1 < current
              ? 'finish'
              : index + 1 === current
              ? 'process'
              : 'wait',
        }))}
      />
    </div>
  )
}

export default StepProgress
