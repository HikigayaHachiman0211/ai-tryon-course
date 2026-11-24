import { useState, useEffect } from 'react'
import { Card, Table, Tag, Row, Col, Statistic, Select, Space, Typography, Modal, Descriptions, Tooltip, Popconfirm, message, Button } from 'antd'
import { UserOutlined, ManOutlined, WomanOutlined, QuestionCircleOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { ColumnsType } from 'antd/es/table'
import { listProfiles, getProfile, getProfileStats, getProfileTryonResults, deleteProfile } from '../api/profiles'
import { useTranslation } from 'react-i18next'

const { Title, Text } = Typography
const { Option } = Select

const AUTO_REFRESH_MS = 15000
interface ProfileItem {
  id: number
  session_id: string
  gender: string
  mbti: string | null
  ai_body_shape: string | null
  ai_recommended_size: string | null
  used_fallback: boolean
  created_at: string
}

export default function ProfilesPage() {
  const { t } = useTranslation('common')
  const [data, setData] = useState<ProfileItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [genderFilter, setGenderFilter] = useState('')
  const [stats, setStats] = useState<Record<string, unknown> | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [tryonResults, setTryonResults] = useState<Record<string, unknown>[]>([])

  const fetchData = (p = page) => {
    setLoading(true)
    listProfiles({ page: p, size: 20, gender: genderFilter })
      .then((res) => { setData(res.data.items || []); setTotal(res.data.total || 0) })
      .finally(() => setLoading(false))
  }

  const refresh = () => {
    fetchData(page)
    getProfileStats().then((res) => setStats(res.data))
  }

  useEffect(() => {
    fetchData(1); setPage(1)
    getProfileStats().then((res) => setStats(res.data))
  }, [genderFilter])

  useEffect(() => {
    const timer = setInterval(refresh, AUTO_REFRESH_MS)
    return () => clearInterval(timer)
  }, [page, genderFilter])

  const handleDelete = async (id: number) => {
    await deleteProfile(id)
    message.success(t('products.deleted'))
    fetchData(1); setPage(1)
    getProfileStats().then((res) => setStats(res.data))
  }

  const showDetail = async (id: number) => {
    const [pRes, tRes] = await Promise.all([getProfile(id), getProfileTryonResults(id)])
    setDetail(pRes.data)
    setTryonResults(tRes.data || [])
    setDetailOpen(true)
  }

  const bodyDist = (stats?.body_shape_distribution as { shape: string; count: number }[]) || []
  const sizeDist = (stats?.size_distribution as { size: string; count: number }[]) || []

  const columns: ColumnsType<ProfileItem> = [
    { title: t('profiles.session'), dataIndex: 'session_id', width: 120, ellipsis: true },
    {
      title: t('profiles.gender'), dataIndex: 'gender', width: 80,
      render: (v: string) => {
        const isMale = v === '男' || v?.toLowerCase() === 'male'
        return isMale ? <Tag icon={<ManOutlined />} color="blue">{t('samples.male')}</Tag> : <Tag icon={<WomanOutlined />} color="pink">{t('samples.female')}</Tag>
      },
    },
    { title: 'MBTI', dataIndex: 'mbti', width: 80 },
    { title: t('profiles.bodyShape'), dataIndex: 'ai_body_shape', width: 120 },
    { title: t('profiles.size'), dataIndex: 'ai_recommended_size', width: 100 },
    {
      title: (
        <Tooltip title={t('profiles.fallbackHint')}>
          {t('profiles.fallbackRate')} <QuestionCircleOutlined style={{ color: '#999', fontSize: 12 }} />
        </Tooltip>
      ),
      dataIndex: 'used_fallback',
      width: 100,
      render: (v: boolean) => v ? <Tag color="orange">{t('status.yes')}</Tag> : <Tag color="green">{t('status.no')}</Tag>,
    },
    { title: t('profiles.createdAt'), dataIndex: 'created_at', width: 180 },
    {
      title: t('actions.submit'), width: 120,
      render: (_, record) => (
        <Space>
          <a onClick={() => showDetail(record.id)}>{t('actions.detail')}</a>
          <Popconfirm title={t('profiles.confirmDelete')} onConfirm={() => handleDelete(record.id)}>
            <a style={{ color: '#ff4d4f' }}><DeleteOutlined /></a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>{t('profiles.title')}</Title>
          <Tooltip title={t('profiles.latencyHint')}><Text type="secondary" style={{ fontSize: 12 }}>{t('profiles.latencyHint')}</Text></Tooltip>
        </Space>
        <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>{t('actions.refresh')}</Button>
      </Space>

      {stats && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title={t('profiles.total')} value={(stats.total as number) || 0} prefix={<UserOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic
                title={
                  <Tooltip title={t('profiles.fallbackHint')}>
                    <span>{t('profiles.fallbackRate')} <QuestionCircleOutlined style={{ color: '#999', fontSize: 12 }} /></span>
                  </Tooltip>
                }
                value={(stats.fallback_rate as number) || 0}
                suffix="%"
                valueStyle={{ color: (stats.fallback_rate as number) > 20 ? '#ff4d4f' : '#52c41a' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12}>
            <Card title={t('profiles.distribution')}>
              <ReactECharts
                option={{
                  tooltip: { trigger: 'item' as const, confine: true },
                  series: [{
                    type: 'pie', radius: ['32%', '62%'],
                    data: bodyDist.map((b) => ({ value: b.count, name: b.shape })),
                    itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
                    label: { overflow: 'truncate' as const },
                  }],
                }}
                style={{ height: 200 }}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card>
        <Space wrap style={{ marginBottom: 16, width: '100%' }}>
          <Select
            className="admin-toolbar-input"
            placeholder={t('profiles.genderFilter')}
            value={genderFilter || undefined}
            onChange={(v) => setGenderFilter(v || '')}
            allowClear
            style={{ width: 120 }}
          >
            <Option value="male">{t('samples.male')}</Option>
            <Option value="female">{t('samples.female')}</Option>
          </Select>
        </Space>
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

      <Modal title={t('actions.detail')} open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={700}>
        {detail && (
          <>
            <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
              {Object.entries(detail).map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>{String(v ?? '-')}</Descriptions.Item>
              ))}
            </Descriptions>
            {tryonResults.length > 0 && (
              <Card title={t('profiles.tryonRecords')} size="small" style={{ marginTop: 12 }}>
                <Table
                  rowKey="id"
                  dataSource={tryonResults}
                  scroll={{ x: 'max-content' }}
                  columns={[
                    { title: 'product_id', dataIndex: 'product_id' },
                    { title: t('profiles.status'), dataIndex: 'status' },
                    { title: t('profiles.time'), dataIndex: 'created_at' },
                  ]}
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
