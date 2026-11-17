import React, { useCallback, useEffect, useState } from 'react'
import {
  Card,
  Button,
  Input,
  Select,
  Tag,
  Space,
  Typography,
  Row,
  Col,
  Statistic,
  message,
  Modal,
  Empty,
} from 'antd'
import {
  SearchOutlined,
  DeleteOutlined,
  EyeOutlined,
  ThunderboltOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { ragApi } from '../../services/api.js'

const { TextArea } = Input
const { Option } = Select
const { Text } = Typography

function mapCase(c) {
  return {
    id: c.id,
    title: c.title,
    type: c.type,
    typeName: c.type_name || c.type,
    style: c.style || '',
    rating: c.rating ?? 0,
    usageCount: c.usage_count ?? 0,
    description: c.description || '',
    tags: c.tags || [],
    createdAt: c.created_at || '',
    promptEn: c.prompt_en || '',
  }
}

function RAGKnowledge() {
  const [searchText, setSearchText] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [queryInput, setQueryInput] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [cases, setCases] = useState([])
  const [stats, setStats] = useState({
    total: 0,
    imageType: 0,
    textType: 0,
    weeklyNew: 0,
  })
  const [loading, setLoading] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const [s, list] = await Promise.all([
        ragApi.stats(),
        ragApi.listCases({
          type: typeFilter === 'all' ? undefined : typeFilter,
          keyword: searchText || undefined,
          page_size: 100,
        }),
      ])
      setStats({
        total: s.total ?? 0,
        imageType: s.image_type ?? 0,
        textType: s.text_type ?? 0,
        weeklyNew: s.weekly_new ?? 0,
      })
      setCases((list || []).map(mapCase))
    } catch (e) {
      message.error(`加载知识库失败: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }, [typeFilter, searchText])

  useEffect(() => {
    reload()
  }, [reload])

  const handleSearch = async () => {
    if (!queryInput.trim()) {
      message.warning('请输入检索内容')
      return
    }
    const hide = message.loading('正在检索...', 0)
    try {
      const hits = await ragApi.search({ query: queryInput, top_k: 5 })
      setSearchResults(
        (hits || []).map((h) => ({
          ...mapCase(h.case),
          similarity: h.similarity,
        })),
      )
      message.success(`检索完成，找到 ${(hits || []).length} 个相关案例`)
    } catch (e) {
      message.error(`检索失败: ${e.message}`)
    } finally {
      hide()
    }
  }

  const handleViewDetail = (caseItem) => {
    Modal.info({
      title: caseItem.title,
      content: (
        <div>
          <p style={{ color: 'var(--vf-text-secondary)', marginBottom: 12 }}>
            {caseItem.description}
          </p>
          {caseItem.promptEn ? (
            <p style={{ fontSize: 12, color: 'var(--vf-text-muted)' }}>
              prompt_en: {caseItem.promptEn}
            </p>
          ) : null}
          <div style={{ marginBottom: 12 }}>
            <Text strong>标签：</Text>
            {(caseItem.tags || []).map((tag) => (
              <Tag key={tag} color="blue">
                {tag}
              </Tag>
            ))}
          </div>
        </div>
      ),
      width: 520,
    })
  }

  const handleDelete = (caseItem) => {
    Modal.confirm({
      title: '删除案例',
      content: `确定删除「${caseItem.title}」？`,
      okType: 'danger',
      onOk: async () => {
        await ragApi.deleteCase(caseItem.id)
        message.success('已删除')
        reload()
      },
    })
  }

  const handleManualAdd = () => {
    let title = ''
    let description = ''
    let type = 'scene'
    Modal.confirm({
      title: '手动添加案例',
      width: 480,
      content: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Input
            placeholder="标题"
            onChange={(e) => {
              title = e.target.value
            }}
          />
          <Select
            defaultValue="scene"
            style={{ width: '100%' }}
            onChange={(v) => {
              type = v
            }}
            options={[
              { value: 'character', label: '角色' },
              { value: 'scene', label: '场景' },
              { value: 'prop', label: '道具' },
              { value: 'storyboard', label: '分镜' },
              { value: 'technique', label: '技巧' },
            ]}
          />
          <TextArea
            placeholder="描述 / 提示词摘要"
            rows={3}
            onChange={(e) => {
              description = e.target.value
            }}
          />
        </div>
      ),
      onOk: async () => {
        if (!title.trim()) {
          message.warning('请填写标题')
          return Promise.reject()
        }
        await ragApi.createCase({
          title: title.trim(),
          type,
          description: description.trim(),
        })
        message.success('已添加')
        reload()
      },
    })
  }

  return (
    <div>
      <div className="bilingual-title" style={{ marginBottom: 20 }}>
        <span className="cn" style={{ fontSize: 20, fontWeight: 700 }}>
          RAG 知识库
        </span>
        <span className="en">RAG Knowledge Base</span>
      </div>

      <div
        style={{
          padding: '12px 16px',
          background: 'rgba(0, 217, 255, 0.1)',
          border: '1px solid rgba(0, 217, 255, 0.2)',
          borderRadius: 8,
          marginBottom: 20,
          fontSize: 13,
          color: '#0891b2',
        }}
      >
        知识库初始为空。完成创作后可在工作台「存入知识库」；需本机安装 bge-m3（
        {'{MODELHUB_ROOT}/embed/bge-m3'}
        ）后检索与入库才可用。
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 20,
        }}
      >
        <Space>
          <Button icon={<PlusOutlined />} onClick={handleManualAdd}>
            手动添加案例
          </Button>
          <Button icon={<ReloadOutlined />} onClick={reload} loading={loading}>
            刷新
          </Button>
        </Space>
        <div style={{ display: 'flex', gap: 12 }}>
          <Select value={typeFilter} onChange={setTypeFilter} style={{ width: 140 }}>
            <Option value="all">全部类型</Option>
            <Option value="character">角色</Option>
            <Option value="scene">场景</Option>
            <Option value="prop">道具</Option>
            <Option value="storyboard">分镜</Option>
            <Option value="technique">技巧</Option>
          </Select>
          <Input
            placeholder="搜索案例..."
            prefix={<SearchOutlined style={{ color: 'var(--vf-text-muted)' }} />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={reload}
            style={{ width: 200 }}
            allowClear
          />
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={12} sm={6}>
          <Card style={{ background: 'var(--vf-surface)', border: '1px solid var(--vf-border)' }}>
            <Statistic title="总案例数" value={stats.total} valueStyle={{ color: '#e94560' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ background: 'var(--vf-surface)', border: '1px solid var(--vf-border)' }}>
            <Statistic title="图像类" value={stats.imageType} valueStyle={{ color: '#0891b2' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ background: 'var(--vf-surface)', border: '1px solid var(--vf-border)' }}>
            <Statistic title="文本类" value={stats.textType} valueStyle={{ color: '#10b981' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ background: 'var(--vf-surface)', border: '1px solid var(--vf-border)' }}>
            <Statistic title="本周新增" value={stats.weeklyNew} valueStyle={{ color: '#ffaa00' }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {!cases.length && !loading ? (
          <Col span={24}>
            <Empty description="暂无案例，可手动添加或从工作台入库" />
          </Col>
        ) : null}
        {cases.map((caseItem) => (
          <Col xs={24} sm={12} lg={8} key={caseItem.id}>
            <Card
              hoverable
              style={{
                background: 'var(--vf-surface)',
                border: '1px solid var(--vf-border)',
                borderRadius: 8,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginBottom: 8,
                }}
              >
                <span style={{ fontSize: 15, fontWeight: 600 }}>{caseItem.title}</span>
                <Tag color="blue">{caseItem.typeName}</Tag>
              </div>
              <p
                style={{
                  fontSize: 12,
                  color: 'var(--vf-text-secondary)',
                  WebkitLineClamp: 2,
                  display: '-webkit-box',
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {caseItem.description || '（无描述）'}
              </p>
              <div style={{ marginBottom: 8 }}>
                {(caseItem.tags || []).map((tag) => (
                  <Tag key={tag} style={{ fontSize: 11 }}>
                    {tag}
                  </Tag>
                ))}
              </div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  borderTop: '1px solid var(--vf-border)',
                  paddingTop: 10,
                }}
              >
                <span style={{ fontSize: 11, color: 'var(--vf-text-muted)' }}>
                  使用 {caseItem.usageCount} 次 · {caseItem.createdAt}
                </span>
                <Space size="small">
                  <Button size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(caseItem)}>
                    查看
                  </Button>
                  <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => handleDelete(caseItem)}
                  />
                </Space>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        style={{ background: 'var(--vf-surface)', border: '1px solid var(--vf-border)' }}
        title="检索测试"
      >
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          <TextArea
            placeholder="输入要检索的内容，测试知识库匹配效果..."
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 3 }}
            style={{ flex: 1 }}
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={handleSearch}
            style={{ background: '#e94560', borderColor: '#e94560', height: 'auto' }}
          >
            开始检索
          </Button>
        </div>
        {searchResults && (
          <div style={{ padding: 16, background: 'var(--vf-surface-muted)', borderRadius: 6 }}>
            <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--vf-text-secondary)' }}>
              找到 {searchResults.length} 个相关案例：
            </div>
            {!searchResults.length ? <Empty description="无命中" /> : null}
            {searchResults.map((result, index) => (
              <div
                key={result.id}
                style={{
                  padding: '10px 12px',
                  background: 'var(--vf-surface)',
                  borderRadius: 4,
                  marginBottom: index < searchResults.length - 1 ? 8 : 0,
                  display: 'flex',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <span style={{ fontWeight: 500 }}>{result.title}</span>
                  <Tag color="blue" style={{ marginLeft: 8 }}>
                    {result.typeName}
                  </Tag>
                </div>
                <Tag>{(result.similarity * 100).toFixed(0)}%</Tag>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

export default RAGKnowledge
