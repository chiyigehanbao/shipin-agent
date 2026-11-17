import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Row,
  Col,
  Card,
  Button,
  Input,
  Select,
  Tag,
  Progress,
  Space,
  Dropdown,
  Empty,
  Spin,
  message,
  Modal,
} from 'antd'
import {
  PlusOutlined,
  SearchOutlined,
  MoreOutlined,
  VideoCameraOutlined,
  BulbOutlined,
  PlayCircleOutlined,
  EditOutlined,
  CopyOutlined,
  InboxOutlined,
  DeleteOutlined,
  AppstoreOutlined,
} from '@ant-design/icons'
import useProjectStore from '../../store/projectStore.js'
import { projectsApi } from '../../services/api.js'

const { Option } = Select

function ProjectList() {
  const navigate = useNavigate()
  const { projects, projectsLoading, fetchProjects } = useProjectStore()

  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [searchText, setSearchText] = useState('')

  useEffect(() => {
    fetchProjects().catch((e) => message.error(`加载项目失败: ${e.message}`))
  }, [fetchProjects])

  const typeConfig = {
    short_drama: { icon: <VideoCameraOutlined />, color: '#e94560', label: '短剧' },
    comic_drama: { icon: <BulbOutlined />, color: '#0891b2', label: '漫剧' },
    video: { icon: <PlayCircleOutlined />, color: '#10b981', label: '视频' },
    drama: { icon: <VideoCameraOutlined />, color: '#e94560', label: '短剧' },
    comic: { icon: <BulbOutlined />, color: '#0891b2', label: '漫剧' },
  }

  const statusConfig = {
    draft: { color: 'default', text: '草稿' },
    in_progress: { color: 'processing', text: '进行中' },
    completed: { color: 'success', text: '已完成' },
    archived: { color: 'default', text: '已归档' },
  }

  const filteredProjects = projects.filter((p) => {
    const matchType = typeFilter === 'all' || p.type === typeFilter
    const matchStatus = statusFilter === 'all' || p.status === statusFilter
    const matchSearch = String(p.name || '').toLowerCase().includes(searchText.toLowerCase())
    return matchType && matchStatus && matchSearch
  })

  const handleProjectClick = (project) => {
    navigate(`/workbench/${project.id}/script`)
  }

  const handleDeleteProject = (project) => {
    Modal.confirm({
      title: '删除项目',
      content: (
        <div>
          确定要删除项目 <b>{project.name}</b> 吗？
          <div style={{ fontSize: 12, color: 'var(--vf-text-muted)', marginTop: 6 }}>
            将同时删除其剧本、资产、分镜与所有生成文件，此操作不可恢复。
          </div>
        </div>
      ),
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await projectsApi.delete(project.id)
          message.success('项目已删除')
          fetchProjects().catch((e) => message.error(`刷新项目列表失败：${e.message}`))
        } catch (e) {
          message.error(`删除失败：${e.message}`)
        }
      },
    })
  }

  const handleArchiveProject = async (project) => {
    try {
      const updated = await projectsApi.update(project.id, {
        name: project.name,
        type: project.type,
        description: project.description || '',
        style: project.style || '',
        status: project.status === 'archived' ? 'draft' : 'archived',
      })
      if (updated) {
        message.success(project.status === 'archived' ? '已取消归档' : '项目已归档')
        fetchProjects().catch((e) => message.error(`刷新项目列表失败：${e.message}`))
      }
    } catch (e) {
      message.error(`归档失败：${e.message}`)
    }
  }

  const handleCreateProject = () => {
    navigate('/workbench/create')
  }

  const getMenuItems = (project) => [
    {
      key: 'edit',
      icon: <EditOutlined />,
      label: '编辑项目',
      onClick: () => handleProjectClick(project),
    },
    {
      key: 'copy',
      icon: <CopyOutlined />,
      label: '复制项目',
    },
    {
      key: 'archive',
      icon: <InboxOutlined />,
      label: project.status === 'archived' ? '取消归档' : '归档项目',
      onClick: () => handleArchiveProject(project),
    },
    { type: 'divider' },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      label: '删除项目',
      danger: true,
      onClick: () => handleDeleteProject(project),
    },
  ]

  return (
    <div className="wb-page">
      <div
        className="vf-reveal"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 26,
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div className="page-heading">
          <div className="page-heading__icon">
            <AppstoreOutlined />
          </div>
          <div className="page-heading__text">
            <h1 className="page-heading__title">工作台</h1>
            <span className="page-heading__subtitle">Workbench · Project List</span>
          </div>
        </div>

        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          onClick={handleCreateProject}
          style={{
            height: 44,
            padding: '0 22px',
            borderRadius: 12,
            fontWeight: 600,
          }}
        >
          新建项目
        </Button>
      </div>

      <div className="wb-toolbar vf-reveal" style={{ animationDelay: '60ms' }}>
        <Space size="middle" wrap style={{ width: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="wb-toolbar__label">类型</span>
            <Select value={typeFilter} onChange={setTypeFilter} style={{ width: 140 }}>
              <Option value="all">全部类型</Option>
              <Option value="short_drama">短剧</Option>
              <Option value="comic_drama">漫剧</Option>
              <Option value="video">视频</Option>
            </Select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="wb-toolbar__label">状态</span>
            <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 140 }}>
              <Option value="all">全部状态</Option>
              <Option value="draft">草稿</Option>
              <Option value="in_progress">进行中</Option>
              <Option value="completed">已完成</Option>
              <Option value="archived">已归档</Option>
            </Select>
          </div>

          <Input
            placeholder="搜索项目名称..."
            prefix={<SearchOutlined style={{ color: 'var(--vf-text-muted)' }} />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 260, borderRadius: 10 }}
            allowClear
          />
        </Space>
      </div>

      <Spin spinning={projectsLoading}>
      {filteredProjects.length > 0 ? (
        <Row gutter={[20, 20]}>
          <Col xs={24} sm={12} md={8} lg={6} className="vf-reveal" style={{ animationDelay: '100ms' }}>
            <Card
              hoverable
              className="project-card project-card--create"
              onClick={handleCreateProject}
              styles={{
                body: {
                  height: 248,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: 20,
                },
              }}
            >
              <div className="create-orb">
                <PlusOutlined />
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--vf-text)' }}>
                新建项目
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: 'var(--vf-text-muted)',
                  marginTop: 6,
                  fontFamily: 'var(--vf-font-display)',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                }}
              >
                Create New
              </div>
            </Card>
          </Col>

          {filteredProjects.map((project, index) => {
            const typeInfo = typeConfig[project.type] || {
              icon: <VideoCameraOutlined />,
              color: '#64748b',
              label: project.typeLabel || '项目',
            }
            const statusInfo = statusConfig[project.status] || {
              color: 'default',
              text: project.status || '未知状态',
            }
            return (
              <Col
                xs={24}
                sm={12}
                md={8}
                lg={6}
                key={project.id}
                className="vf-reveal"
                style={{ animationDelay: `${140 + index * 50}ms` }}
              >
                <Card
                  hoverable
                  className="project-card"
                  onClick={() => handleProjectClick(project)}
                  styles={{ body: { padding: 0, height: '100%' } }}
                >
                  <div
                    className="project-card__cover"
                    style={{
                      background: `linear-gradient(145deg, ${typeInfo.color}22 0%, ${typeInfo.color}08 40%, #f8fafc 100%)`,
                      color: typeInfo.color,
                    }}
                  >
                    {typeInfo.icon}
                    <Dropdown
                      menu={{ items: getMenuItems(project) }}
                      trigger={['click']}
                      placement="bottomRight"
                    >
                      <Button
                        type="text"
                        icon={<MoreOutlined />}
                        style={{
                          position: 'absolute',
                          top: 8,
                          right: 8,
                          color: 'var(--vf-text-secondary)',
                          background: 'rgba(255,255,255,0.75)',
                        }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Dropdown>
                    <Tag
                      color={typeInfo.color}
                      style={{
                        position: 'absolute',
                        top: 10,
                        left: 10,
                        borderRadius: 999,
                        margin: 0,
                      }}
                    >
                      {typeInfo.label}
                    </Tag>
                  </div>

                  <div className="project-card__meta">
                    <div className="project-card__name">{project.name}</div>
                    <div className="project-card__desc">
                      {project.style} · {project.episodes}集
                    </div>
                    <Progress
                      percent={project.progress}
                      size="small"
                      strokeColor="#e94560"
                      trailColor="var(--vf-border)"
                      format={(percent) => (
                        <span style={{ fontSize: 11, color: 'var(--vf-text-muted)' }}>
                          {percent}%
                        </span>
                      )}
                    />
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginTop: 8,
                      }}
                    >
                      <Tag color={statusInfo.color} style={{ fontSize: 11, margin: 0 }}>
                        {statusInfo.text}
                      </Tag>
                      <span style={{ fontSize: 11, color: 'var(--vf-text-muted)' }}>
                        {project.updatedAt}
                      </span>
                    </div>
                  </div>
                </Card>
              </Col>
            )
          })}
        </Row>
      ) : (
        <div style={{ textAlign: 'center', padding: '80px 0' }} className="vf-reveal">
          <Empty
            description={
              <div>
                <div style={{ color: 'var(--vf-text-secondary)', marginBottom: 8 }}>暂无项目</div>
                <div
                  style={{
                    fontSize: 12,
                    color: 'var(--vf-text-muted)',
                    fontFamily: 'var(--vf-font-display)',
                    letterSpacing: '0.06em',
                  }}
                >
                  No projects yet
                </div>
              </div>
            }
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateProject}>
              创建第一个项目
            </Button>
          </Empty>
        </div>
      )}
      </Spin>
    </div>
  )
}

export default ProjectList
