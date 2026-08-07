import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Modal, Typography, Descriptions, Spin, message, Popconfirm, Image, Tag, Tooltip } from 'antd'
import { EyeOutlined, DeleteOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { listHistory, getHistory, deleteHistory } from '../api/history'

const { Title, Text } = Typography

const AUTO_REFRESH_MS = 15000
const LATENCY_HINT = '数据为主站/试穿台异步上报，可能有数秒延迟；本页每 15 秒自动刷新'

interface HistoryItem {
  id: string
  summary?: string
  created_at: string
  user_photo_url?: string
  result_count?: number
}

interface DetailFilters {
  price_min?: number
  price_max?: number
  catalog_total?: number
  matched_after_price_filter?: number
  matched_after_gender_filter?: number
  user_gender?: string
  brand_preference?: string
}

interface DetailInference {
  resolved_size?: string
  resolved_style?: string
  body_shape?: string
  size_source?: string
  style_source?: string
  reasoning?: string
  gemini_model?: string
  gemini_used?: boolean
  mimo_model?: string
  mimo_used?: boolean
  ai_provider?: string
  rule_fallback_used?: boolean
}

interface DetailItem {
  id: number
  title: string
  price: number
  image_url?: string
  brand?: string
  style_type?: string
  color_family?: string
  total_score: number
  reason?: string
}

interface HistoryDetail {
  filters?: DetailFilters
  inference?: DetailInference
  items?: DetailItem[]
  user_photo_url?: string
  _total_items?: number
  [key: string]: unknown
}

export default function HistoryPage() {
  const [data, setData] = useState<HistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<HistoryDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)

  const fetchData = (p = page) => {
    setLoading(true)
    listHistory({ page: p, size: 20 })
      .then((res) => { setData(res.data.items || []); setTotal(res.data.total || 0) })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData() }, [])

  useEffect(() => {
    const timer = setInterval(() => fetchData(page), AUTO_REFRESH_MS)
    return () => clearInterval(timer)
  }, [page])

  const showDetail = async (id: string) => {
    setDetailLoading(true)
    setDetailOpen(true)
    try {
      const res = await getHistory(id)
      setDetail(res.data)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    await deleteHistory(id)
    message.success('已删除')
    fetchData()
  }

  const columns: ColumnsType<HistoryItem> = [
    {
      title: 'ID', dataIndex: 'id', width: 220, ellipsis: true,
      render: (v: string) => <Tooltip title={v}><span>{v}</span></Tooltip>,
    },
    { title: '摘要', dataIndex: 'summary', ellipsis: true },
    { title: '时间', dataIndex: 'created_at', width: 180 },
    { title: '结果数', dataIndex: 'result_count', width: 80 },
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => showDetail(record.id)}>详情</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const itemColumns: ColumnsType<DetailItem> = [
    { title: '商品', dataIndex: 'title', ellipsis: true, width: 200 },
    { title: '价格', dataIndex: 'price', width: 80, render: (v: number) => `¥${v}` },
    { title: '评分', dataIndex: 'total_score', width: 70, render: (v: number) => <Tag color="blue">{v?.toFixed(1)}</Tag> },
    { title: '颜色', dataIndex: 'color_family', width: 80 },
    { title: '款式', dataIndex: 'style_type', width: 100 },
    { title: '品牌', dataIndex: 'brand', width: 80 },
  ]

  const inf = detail?.inference
  const filters = detail?.filters

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>推荐历史</Title>
          <Tooltip title={LATENCY_HINT}><Text type="secondary" style={{ fontSize: 12 }}>数据可能有数秒延迟 ⓘ</Text></Tooltip>
        </Space>
        <Button icon={<ReloadOutlined />} onClick={() => fetchData(page)} loading={loading}>刷新</Button>
      </Space>
      <Card>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={{
            current: page, pageSize: 20, total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="middle"
        />
      </Card>
      <Modal
        title="推荐详情"
        open={detailOpen}
        onCancel={() => { setDetailOpen(false); setDetail(null) }}
        footer={null}
        width={780}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : detail && (
          <>
            {detail.user_photo_url && (
              <Card size="small" title="用户上传图片" style={{ marginBottom: 12 }}>
                <Space align="start">
                  <Image src={detail.user_photo_url} width={120} style={{ borderRadius: 4 }} />
                  <div>
                    <Text type="secondary">Cloud Storage 链接：</Text>
                    <br />
                    <a href={detail.user_photo_url} target="_blank" rel="noopener noreferrer">
                      <LinkOutlined /> {detail.user_photo_url}
                    </a>
                  </div>
                </Space>
              </Card>
            )}

            {inf && (
              <Descriptions title="AI 推断" column={2} bordered size="small" style={{ marginBottom: 12 }}>
                <Descriptions.Item label="推荐尺码">{inf.resolved_size ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="推荐款式">{inf.resolved_style ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="体型判断">{inf.body_shape ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="AI 模型">
                  {inf.ai_provider === 'mimo'
                    ? (inf.mimo_model ?? '-')
                    : inf.ai_provider === 'gemini'
                      ? (inf.gemini_model ?? '-')
                      : (inf.gemini_model ?? inf.mimo_model ?? inf.ai_provider ?? '-')}
                </Descriptions.Item>
                <Descriptions.Item label="尺码来源">{inf.size_source ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="款式来源">{inf.style_source ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="AI 使用">
                  {(inf.rule_fallback_used === false || inf.gemini_used || inf.mimo_used)
                    ? <Tag color="green">是</Tag>
                    : <Tag color="orange">否 (Fallback)</Tag>}
                </Descriptions.Item>
                {inf.reasoning && (
                  <Descriptions.Item label="推理说明" span={2}>{inf.reasoning}</Descriptions.Item>
                )}
              </Descriptions>
            )}

            {filters && (
              <Descriptions title="筛选条件" column={2} bordered size="small" style={{ marginBottom: 12 }}>
                <Descriptions.Item label="价格区间">
                  {filters.price_min ?? '无'} ~ {filters.price_max ?? '无'}
                </Descriptions.Item>
                <Descriptions.Item label="用户性别">{filters.user_gender ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="品牌偏好">{filters.brand_preference ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="商品总数">{filters.catalog_total ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="价格筛选后">{filters.matched_after_price_filter ?? '-'}</Descriptions.Item>
                <Descriptions.Item label="性别筛选后">{filters.matched_after_gender_filter ?? '-'}</Descriptions.Item>
              </Descriptions>
            )}

            {detail.items && detail.items.length > 0 && (
              <Card
                size="small"
                title={
                  <span>
                    推荐商品 (前 5 项)
                    {detail._total_items && detail._total_items > 5 && (
                      <Text type="secondary" style={{ marginLeft: 8, fontWeight: 'normal' }}>
                        共 {detail._total_items} 项
                      </Text>
                    )}
                  </span>
                }
              >
                <Table
                  rowKey="id"
                  dataSource={detail.items}
                  columns={itemColumns}
                  size="small"
                  pagination={false}
                />
              </Card>
            )}
          </>
        )}
      </Modal>
    </div>
  )
}
