import { useState, useEffect } from 'react'
import { Card, Table, Tag, Row, Col, Statistic, Select, Space, Typography, Modal, Descriptions, Tooltip } from 'antd'
import { UserOutlined, ManOutlined, WomanOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { ColumnsType } from 'antd/es/table'
import { listProfiles, getProfile, getProfileStats, getProfileTryonResults } from '../api/profiles'

const { Title } = Typography
const { Option } = Select

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

  useEffect(() => {
    fetchData(1); setPage(1)
    getProfileStats().then((res) => setStats(res.data))
  }, [genderFilter])

  const showDetail = async (id: number) => {
    const [pRes, tRes] = await Promise.all([getProfile(id), getProfileTryonResults(id)])
    setDetail(pRes.data)
    setTryonResults(tRes.data || [])
    setDetailOpen(true)
  }

  const bodyDist = (stats?.body_shape_distribution as { shape: string; count: number }[]) || []
  const sizeDist = (stats?.size_distribution as { size: string; count: number }[]) || []

  const columns: ColumnsType<ProfileItem> = [
    { title: '会话', dataIndex: 'session_id', width: 120, ellipsis: true },
    {
      title: '性别', dataIndex: 'gender', width: 80,
      render: (v: string) => v === '男' ? <Tag icon={<ManOutlined />} color="blue">{v}</Tag> : <Tag icon={<WomanOutlined />} color="pink">{v}</Tag>,
    },
    { title: 'MBTI', dataIndex: 'mbti', width: 80 },
    { title: 'AI 体型', dataIndex: 'ai_body_shape', width: 120 },
    { title: '推荐尺码', dataIndex: 'ai_recommended_size', width: 100 },
    {
      title: (
        <Tooltip title="Fallback 表示 AI (Gemini) 体型分析失败或不可用，系统自动回退到基于规则的启发式推断（如通过身高推尺码、关键词推款式）">
          Fallback <QuestionCircleOutlined style={{ color: '#999', fontSize: 12 }} />
        </Tooltip>
      ),
      dataIndex: 'used_fallback',
      width: 100,
      render: (v: boolean) => v ? <Tag color="orange">是</Tag> : <Tag color="green">否</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 180 },
    {
      title: '操作', width: 80,
      render: (_, record) => <a onClick={() => showDetail(record.id)}>详情</a>,
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>用户画像</Title>

      {stats && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="总画像数" value={(stats.total as number) || 0} prefix={<UserOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic
                title={
                  <Tooltip title="Fallback 率 = 使用规则回退的画像数 / 总画像数 × 100%。反映 AI 分析的可用性和成功率，比率越低表示 AI 服务越稳定">
                    <span>Fallback 率 <QuestionCircleOutlined style={{ color: '#999', fontSize: 12 }} /></span>
                  </Tooltip>
                }
                value={(stats.fallback_rate as number) || 0}
                suffix="%"
                valueStyle={{ color: (stats.fallback_rate as number) > 20 ? '#ff4d4f' : '#52c41a' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12}>
            <Card title="体型分布">
              <ReactECharts
                option={{
                  tooltip: { trigger: 'item' as const },
                  series: [{
                    type: 'pie', radius: ['30%', '65%'],
                    data: bodyDist.map((b) => ({ value: b.count, name: b.shape })),
                    itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
                  }],
                }}
                style={{ height: 200 }}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select
            placeholder="性别筛选"
            value={genderFilter || undefined}
            onChange={(v) => setGenderFilter(v || '')}
            allowClear
            style={{ width: 120 }}
          >
            <Option value="男">男</Option>
            <Option value="女">女</Option>
          </Select>
        </Space>
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

      <Modal title="用户画像详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={700}>
        {detail && (
          <>
            <Descriptions column={2} bordered size="small">
              {Object.entries(detail).map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>{String(v ?? '-')}</Descriptions.Item>
              ))}
            </Descriptions>
            {tryonResults.length > 0 && (
              <Card title="试穿记录" size="small" style={{ marginTop: 12 }}>
                <Table
                  rowKey="id"
                  dataSource={tryonResults}
                  columns={[
                    { title: '商品 ID', dataIndex: 'product_id' },
                    { title: '状态', dataIndex: 'status' },
                    { title: '时间', dataIndex: 'created_at' },
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
