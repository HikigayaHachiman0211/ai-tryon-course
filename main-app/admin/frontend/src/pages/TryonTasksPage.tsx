import { useState, useEffect } from 'react'
import { Card, Table, Tag, Row, Col, Statistic, Space, Button, Select, Typography, Modal, Descriptions, Tooltip } from 'antd'
import { ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { ColumnsType } from 'antd/es/table'
import { listTasks, getTaskStats, getTask, retryTask } from '../api/tryon'
import { message } from 'antd'

const { Title, Text } = Typography
const { Option } = Select

const AUTO_REFRESH_MS = 15000
const LATENCY_HINT = '数据为试穿台异步上报，可能有数秒延迟；本页每 15 秒自动刷新'

interface TryonTask {
  id: string
  status: string
  product_id: number
  user_photo_url: string
  result_image_url: string | null
  created_at: string
  updated_at: string | null
  duration_ms: number | null
  error_type: string | null
  error_detail: string | null
  model_used: string
}

export default function TryonTasksPage() {
  const [data, setData] = useState<TryonTask[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [stats, setStats] = useState<Record<string, unknown> | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const fetchData = (p = page) => {
    setLoading(true)
    listTasks({ page: p, size: 20, status: statusFilter })
      .then((res) => { setData(res.data.items || []); setTotal(res.data.total || 0) })
      .finally(() => setLoading(false))
  }

  const refresh = () => {
    fetchData(page)
    getTaskStats().then((res) => setStats(res.data))
  }

  useEffect(() => {
    fetchData(1); setPage(1)
    getTaskStats().then((res) => setStats(res.data))
  }, [statusFilter])

  useEffect(() => {
    const timer = setInterval(refresh, AUTO_REFRESH_MS)
    return () => clearInterval(timer)
  }, [page, statusFilter])

  const handleRetry = async (id: string) => {
    await retryTask(id)
    message.success('已重试')
    fetchData()
  }

  const showDetail = async (id: string) => {
    const res = await getTask(id)
    setDetail(res.data)
    setDetailOpen(true)
  }

  const columns: ColumnsType<TryonTask> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => {
        const colorMap: Record<string, string> = {
          completed: 'green', failed: 'red', queued: 'blue', processing: 'orange', pending: 'default',
        }
        return <Tag color={colorMap[s] || 'default'}>{s}</Tag>
      },
    },
    { title: '商品 ID', dataIndex: 'product_id', width: 80 },
    { title: '创建时间', dataIndex: 'created_at', width: 180 },
    { title: '耗时', dataIndex: 'duration_ms', width: 80, render: (v: number | null) => v ? `${(v / 1000).toFixed(1)}s` : '-' },
    { title: '错误', dataIndex: 'error_detail', ellipsis: true },
    {
      title: '操作',
      width: 130,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => showDetail(record.id)}>详情</Button>
          {record.status === 'failed' && (
            <Button size="small" icon={<ReloadOutlined />} onClick={() => handleRetry(record.id)}>重试</Button>
          )}
        </Space>
      ),
    },
  ]

  const successTrend = (stats?.success_trend as { date: string; rate: number; total: number }[]) || []
  const errorDist = (stats?.error_distribution as { type: string; count: number }[]) || []
  const hasTrendData = successTrend.some((t) => t.total > 0)

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>AI 试穿任务</Title>
          <Tooltip title={LATENCY_HINT}><Text type="secondary" style={{ fontSize: 12 }}>数据可能有数秒延迟 ⓘ</Text></Tooltip>
        </Space>
        <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>刷新</Button>
      </Space>

      {stats && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="总任务" value={(stats.total as number) || 0} prefix={<ThunderboltOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="已完成" value={(stats.completed as number) || 0} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="失败" value={(stats.failed as number) || 0} valueStyle={{ color: '#ff4d4f' }} prefix={<CloseCircleOutlined />} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Tooltip title="已完成任务平均耗时">
                <Statistic title="平均耗时" value={stats.avg_duration_ms ? ((stats.avg_duration_ms as number) / 1000).toFixed(1) : '0'} suffix="s" prefix={<ClockCircleOutlined />} />
              </Tooltip>
            </Card>
          </Col>
        </Row>
      )}

      {stats && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} lg={16}>
            <Card title="成功率趋势">
              {hasTrendData ? (
                <ReactECharts
                  option={{
                    tooltip: { trigger: 'axis' as const },
                    xAxis: { type: 'category' as const, data: successTrend.map((t) => t.date) },
                    yAxis: { type: 'value' as const, max: 100 },
                    series: [{
                      type: 'line', smooth: true,
                      data: successTrend.map((t) => t.rate),
                      itemStyle: { color: '#52c41a' },
                      areaStyle: { color: 'rgba(82,196,26,0.1)' },
                    }],
                    grid: { top: 10, right: 20, bottom: 30, left: 50 },
                  }}
                  style={{ height: 200 }}
                />
              ) : (
                <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>暂无趋势数据</div>
              )}
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="错误分布">
              {errorDist.length > 0 ? (
                <ReactECharts
                  option={{
                    tooltip: { trigger: 'item' as const },
                    series: [{
                      type: 'pie', radius: ['35%', '65%'],
                      data: errorDist.map((e) => ({ value: e.count, name: e.type })),
                    }],
                  }}
                  style={{ height: 200 }}
                />
              ) : (
                <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>暂无错误</div>
              )}
            </Card>
          </Col>
        </Row>
      )}

      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select
            placeholder="状态筛选"
            value={statusFilter || undefined}
            onChange={(v) => setStatusFilter(v || '')}
            allowClear
            style={{ width: 150 }}
          >
            {['pending', 'queued', 'processing', 'completed', 'failed'].map((s) => (
              <Option key={s} value={s}>{s}</Option>
            ))}
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

      <Modal title="任务详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={600}>
        {detail && (
          <Descriptions column={1} bordered size="small">
            {Object.entries(detail).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? '-')}
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
