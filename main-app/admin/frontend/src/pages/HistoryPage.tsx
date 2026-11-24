import { useState, useEffect } from 'react'
import { Card, Table, Button, Space, Modal, Typography, Descriptions, Spin, message, Popconfirm, Image, Tag, Tooltip } from 'antd'
import { EyeOutlined, DeleteOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { listHistory, getHistory, deleteHistory } from '../api/history'
import { useTranslation } from 'react-i18next'
import { formatCurrency } from '../i18n/formatters'
import type { AppLocale } from '../i18n/locale'

const { Title, Text } = Typography

const AUTO_REFRESH_MS = 15000
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
  const { t, i18n } = useTranslation('common')
  const locale = (i18n.language === 'en' || i18n.language === 'ja' ? i18n.language : 'zh-CN') as AppLocale
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
    message.success(t('products.deleted'))
    fetchData()
  }

  const columns: ColumnsType<HistoryItem> = [
    {
      title: 'ID', dataIndex: 'id', width: 220, ellipsis: true,
      render: (v: string) => <Tooltip title={v}><span>{v}</span></Tooltip>,
    },
    { title: t('history.summary'), dataIndex: 'summary', ellipsis: true },
    { title: t('history.time'), dataIndex: 'created_at', width: 180 },
    { title: t('history.resultCount'), dataIndex: 'result_count', width: 80 },
    {
      title: t('actions.submit'),
      width: 120,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => showDetail(record.id)}>{t('actions.detail')}</Button>
          <Popconfirm title={t('products.confirmDelete')} onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const itemColumns: ColumnsType<DetailItem> = [
    { title: t('history.product'), dataIndex: 'title', ellipsis: true, width: 200 },
    { title: t('products.price'), dataIndex: 'price', width: 80, render: (v: number) => formatCurrency(v, locale) },
    { title: t('history.score'), dataIndex: 'total_score', width: 70, render: (v: number) => <Tag color="blue">{v?.toFixed(1)}</Tag> },
    { title: t('products.color'), dataIndex: 'color_family', width: 80 },
    { title: t('products.style'), dataIndex: 'style_type', width: 100 },
    { title: t('history.brand'), dataIndex: 'brand', width: 80 },
  ]

  const inf = detail?.inference
  const filters = detail?.filters

  return (
    <div>
      <Space wrap style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space wrap>
          <Title level={4} style={{ margin: 0 }}>{t('history.title')}</Title>
          <Tooltip title={t('history.latencyHint')}><Text type="secondary" style={{ fontSize: 12 }}>{t('history.delayed')}</Text></Tooltip>
        </Space>
        <Button icon={<ReloadOutlined />} onClick={() => fetchData(page)} loading={loading}>{t('actions.refresh')}</Button>
      </Space>
      <Card>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 'max-content' }}
          pagination={{
            current: page, pageSize: 20, total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (count) => t('pagination.total', { count }),
          }}
          size="middle"
        />
      </Card>
      <Modal
        title={t('actions.detail')}
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
              <Card size="small" title={t('history.userImage')} style={{ marginBottom: 12 }}>
                <Space align="start" wrap>
                  <Image src={detail.user_photo_url} width={120} style={{ borderRadius: 4 }} />
                  <div>
                    <Text type="secondary">{t('history.cloudLink')}</Text>
                    <br />
                    <a href={detail.user_photo_url} target="_blank" rel="noopener noreferrer">
                      <LinkOutlined /> {detail.user_photo_url}
                    </a>
                  </div>
                </Space>
              </Card>
            )}

            {inf && (
              <Descriptions title={t('history.inference')} column={{ xs: 1, sm: 2 }} bordered size="small" style={{ marginBottom: 12 }}>
                <Descriptions.Item label={t('history.recommendedSize')}>{inf.resolved_size ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.recommendedStyle')}>{inf.resolved_style ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.bodyShape')}>{inf.body_shape ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.model')}>
                  {inf.ai_provider === 'mimo'
                    ? (inf.mimo_model ?? '-')
                    : inf.ai_provider === 'gemini'
                      ? (inf.gemini_model ?? '-')
                      : inf.ai_provider === 'deepseek'
                        ? 'deepseek-flash'
                        : inf.ai_provider === 'opencode_go'
                          ? 'OpenCode Go'
                          : (inf.gemini_model ?? inf.mimo_model ?? inf.ai_provider ?? '-')}
                </Descriptions.Item>
                <Descriptions.Item label={t('history.sizeSource')}>{inf.size_source ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.styleSource')}>{inf.style_source ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.aiUsed')}>
                  {(inf.rule_fallback_used === false || inf.gemini_used || inf.mimo_used)
                    ? <Tag color="green">{t('status.yes')}</Tag>
                    : <Tag color="orange">{t('history.fallback')}</Tag>}
                </Descriptions.Item>
                {inf.reasoning && (
                  <Descriptions.Item label={t('history.reasoning')} span={{ xs: 1, sm: 2 }}>{inf.reasoning}</Descriptions.Item>
                )}
              </Descriptions>
            )}

            {filters && (
              <Descriptions title={t('history.filters')} column={{ xs: 1, sm: 2 }} bordered size="small" style={{ marginBottom: 12 }}>
                <Descriptions.Item label={t('history.priceRange')}>
                  {filters.price_min ?? t('history.noValue')} ~ {filters.price_max ?? t('history.noValue')}
                </Descriptions.Item>
                <Descriptions.Item label={t('history.gender')}>{filters.user_gender ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.brandPreference')}>{filters.brand_preference ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.catalogTotal')}>{filters.catalog_total ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.matchedPrice')}>{filters.matched_after_price_filter ?? '-'}</Descriptions.Item>
                <Descriptions.Item label={t('history.matchedGender')}>{filters.matched_after_gender_filter ?? '-'}</Descriptions.Item>
              </Descriptions>
            )}

            {detail.items && detail.items.length > 0 && (
              <Card
                size="small"
                title={
                  <span>
                    {t('history.recommendations')}
                    {detail._total_items && detail._total_items > 5 && (
                      <Text type="secondary" style={{ marginLeft: 8, fontWeight: 'normal' }}>
                        {t('history.totalItems', { count: detail._total_items })}
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
                  scroll={{ x: 'max-content' }}
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
