import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Button, Input, Radio, Space, Typography, message } from 'antd'
import {
  ArrowLeftOutlined,
  VideoCameraOutlined,
  BulbOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import useProjectStore from '../../store/projectStore.js'

const { Title, Text } = Typography

// 项目创建页
// 选择项目类型（短剧/漫剧/视频），输入项目名称，创建后进入剧本工坊
function ProjectCreate() {
  const navigate = useNavigate()
  const { createProject } = useProjectStore()

  // 选中的项目类型
  const [selectedType, setSelectedType] = useState('short_drama')
  // 项目名称
  const [projectName, setProjectName] = useState('')

  // 项目类型配置
  const typeOptions = [
    {
      value: 'short_drama',
      icon: <VideoCameraOutlined style={{ fontSize: '36px' }} />,
      title: '短剧',
      subtitle: 'Short Drama',
      desc: '多集连续叙事内容，每集3-5分钟',
      color: '#e94560',
    },
    {
      value: 'comic_drama',
      icon: <BulbOutlined style={{ fontSize: '36px' }} />,
      title: '漫剧',
      subtitle: 'Comic Drama',
      desc: '动态漫画+配音，静态图+运镜',
      color: '#0891b2',
    },
    {
      value: 'video',
      icon: <PlayCircleOutlined style={{ fontSize: '36px' }} />,
      title: '视频',
      subtitle: 'Video',
      desc: '单集短视频，广告/宣传/MV',
      color: '#10b981',
    },
  ]

  // 创建项目并进入
  const [creating, setCreating] = useState(false)
  const handleCreate = async () => {
    const name = projectName.trim() || '未命名项目'
    setCreating(true)
    try {
      const project = await createProject(name, selectedType)
      navigate(`/workbench/${project.id}/script`)
    } catch (e) {
      message.error(`创建失败: ${e.message}`)
    } finally {
      setCreating(false)
    }
  }

  // 返回上一页
  const handleBack = () => {
    navigate('/workbench')
  }

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto' }}>
      {/* 返回按钮 */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={handleBack}
        style={{ marginBottom: '20px', color: 'var(--vf-text-secondary)' }}
      >
        返回项目列表
      </Button>

      <div className="page-heading" style={{ marginBottom: 28 }}>
        <div className="page-heading__icon">
          <PlayCircleOutlined />
        </div>
        <div className="page-heading__text">
          <h1 className="page-heading__title">创建新项目</h1>
          <span className="page-heading__subtitle">Create New Project</span>
        </div>
      </div>

      {/* 类型选择卡片 */}
      <Title level={5} style={{ color: 'var(--vf-text-secondary)', marginBottom: '16px' }}>
        选择项目类型 / Select Project Type
      </Title>

      <Space size="large" style={{ marginBottom: '32px', width: '100%' }}>
        {typeOptions.map((option) => (
          <Card
            key={option.value}
            hoverable
            onClick={() => setSelectedType(option.value)}
            style={{
              flex: 1,
              minWidth: '250px',
              background: 'var(--vf-surface)',
              border:
                selectedType === option.value
                  ? `2px solid ${option.color}`
                  : '1px solid var(--vf-border)',
              borderRadius: '12px',
              transition: 'all 0.3s ease',
              boxShadow:
                selectedType === option.value
                  ? `0 0 30px ${option.color}33`
                  : 'none',
            }}
            bodyStyle={{ padding: '32px 24px', textAlign: 'center' }}
          >
            {/* 图标 */}
            <div
              style={{
                width: '72px',
                height: '72px',
                borderRadius: '50%',
                background: `${option.color}22`,
                color: option.color,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 16px',
              }}
            >
              {option.icon}
            </div>

            {/* 标题 */}
            <div className="bilingual-title" style={{ marginBottom: '12px' }}>
              <span
                className="cn"
                style={{ fontSize: '20px', fontWeight: 700, color: 'var(--vf-text)' }}
              >
                {option.title}
              </span>
              <span className="en">{option.subtitle}</span>
            </div>

            {/* 描述 */}
            <Text style={{ color: 'var(--vf-text-secondary)', fontSize: '13px' }}>
              {option.desc}
            </Text>

            {/* 选中标记 */}
            {selectedType === option.value && (
              <div
                style={{
                  marginTop: '16px',
                  color: option.color,
                  fontSize: '13px',
                  fontWeight: 600,
                }}
              >
                ✓ 已选择
              </div>
            )}
          </Card>
        ))}
      </Space>

      {/* 项目名称输入 */}
      <Card
        style={{
          background: 'var(--vf-surface)',
          border: '1px solid var(--vf-border)',
          borderRadius: '8px',
          marginBottom: '32px',
        }}
        bodyStyle={{ padding: '24px' }}
      >
        <Title level={5} style={{ color: 'var(--vf-text)', marginBottom: '16px' }}>
          项目名称 / Project Name
        </Title>
        <Input
          size="large"
          placeholder="请输入项目名称，如：仙途第一季"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          style={{ maxWidth: '400px' }}
          onPressEnter={handleCreate}
        />
        <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--vf-text-muted)' }}>
          留空则使用默认名称「未命名项目」
        </div>
      </Card>

      {/* 底部按钮 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
        <Button size="large" onClick={handleBack}>
          取消
        </Button>
        <Button
          type="primary"
          size="large"
          onClick={handleCreate}
          loading={creating}
          style={{
            background: '#e94560',
            borderColor: '#e94560',
            padding: '0 32px',
          }}
        >
          创建并进入
        </Button>
      </div>
    </div>
  )
}

export default ProjectCreate
