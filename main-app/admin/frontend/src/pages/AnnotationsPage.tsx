import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Tag, Row, Col, Statistic, Select, Modal,
  Form, Input, Popconfirm, message, Typography, Progress, Descriptions,
} from 'antd'
import {
  CheckOutlined, CloseOutlined, EditOutlined, SyncOutlined, ExportOutlined,
  DatabaseOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { ColumnsType } from 'antd/es/table'
import {
  listAnnotations, getAnnotationStats, getAnnotation, updateAnnotation,
  approveAnnotation, rejectAnnotation, batchApprove, recomputeConfidence,
  exportAnnotations, syncDatabaseJson, getQualityReport,
} from '../api/annotations'

const { Title, Text } = Typography
const { Option } = Select

interface AnnotationItem {
  id: number
  title: string
  image_url: string | null
  style_type: string
  color_family: string
  annotation_status: string | null
  annotation_confidence: number | null
  last_annotated_by: string | null
  task?: { status: string; priority: number; assigned_to: string | null } | null
}

export default function AnnotationsPage() {
  const [data, setData] = useState<AnnotationItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [stats, setStats] = useState<Record<string, unknown> | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [form] = Form.useForm()

  const fetchData = (p = page) => {
    setLoading(true)
    listAnnotations({ page: p, size: 20, status: statusFilter })
      .then((res) => { setData(res.data.items || []); setTotal(res.data.total || 0) })
      .finally(() => setLoading(false))
  }

  const fetchStats = () => {
    getAnnotationStats().then((res) => setStats(res.data))
  }

  useEffect(() => { fetchData(1); setPage(1); fetchStats() }, [statusFilter])

  const openEdit = async (productId: number) => {
    const res = await getAnnotation(productId)
    setDetail(res.data)
    const p = res.data.product
    form.setFieldsValue({
      color_family: p.color_family,
      style_type: p.style_type,
      body_fit: p.body_fit,
    })
    setEditOpen(true)
  }

  const handleSave = async () => {
    if (!detail) return
    const values = form.getFieldsValue()
    const product = detail.product as Record<string, unknown>
    await updateAnnotation(product.id as number, values)
    message.success('标注已保存')
    setEditOpen(false)
    fetchData()
  }

  const handleApprove = async (id: number) => {
    await approveAnnotation(id)
    message.success('已确认')
    fetchData()
    fetchStats()
  }

  const handleReject = async (id: number) => {
    await rejectAnnotation(id, '')
    message.success('已驳回')
    fetchData()
  }

  const handleBatchApprove = async () => {
    await batchApprove(selectedIds)
    message.success(`已批量确认 ${selectedIds.length} 条`)
    setSelectedIds([])
    fetchData()
    fetchStats()
  }

  const handleRecompute = async () => {
    const res = await recomputeConfidence()
    message.success(`已重新计算 ${res.data.recomputed} 条`)
    fetchData()
    fetchStats()
  }

  const handleExport = async () => {
    const res = await exportAnnotations()
    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'annotations.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleSync = async () => {
    const res = await syncDatabaseJson()
    message.success(`已同步 ${res.data.total} 条已验证数据`)
  }

  const confDist = (stats?.confidence_distribution as { range: string; count: number }[]) || []

  const columns: ColumnsType<AnnotationItem> = [
    { title: '商品名称', dataIndex: 'title', ellipsis: true },
    { title: '款式', dataIndex: 'style_type', width: 100 },
    { title: '颜色', dataIndex: 'color_family', width: 100, render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
    {
      title: '状态',
      dataIndex: 'annotation_status',
      width: 100,
      render: (v: string | null) => {
        const m: Record<string, string> = { verified: 'green', partial: 'orange', unreviewed: 'default' }
        return <Tag color={m[v || ''] || 'default'}>{v || '未审核'}</Tag>
      },
    },
    {
      title: '置信度',
      dataIndex: 'annotation_confidence',
      width: 100,
      render: (v: number | null) => v != null ? (
        <Progress
          percent={Math.round(v * 100)}
          size="small"
          status={v >= 0.8 ? 'success' : v >= 0.5 ? 'normal' : 'exception'}
        />
      ) : '-',
    },
    {
      title: '优先级',
      width: 80,
      render: (_, record) => {
        const p = record.task?.priority
        if (p === 2) return <Tag color="red">高</Tag>
        if (p === 1) return <Tag color="orange">中</Tag>
        return <Tag>低</Tag>
      },
    },
    { title: '最后标注', dataIndex: 'last_annotated_by', width: 100 },
    {
      title: '操作',
      width: 180,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record.id)}>标注</Button>
          <Button size="small" type="primary" ghost icon={<CheckOutlined />} onClick={() => handleApprove(record.id)}>
            确认
          </Button>
          <Popconfirm title="确认驳回？" onConfirm={() => handleReject(record.id)}>
            <Button size="small" danger icon={<CloseOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>标注中心</Title>

      {stats && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="总商品" value={(stats.total as number) || 0} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="已验证" value={(stats.verified as number) || 0} valueStyle={{ color: '#52c41a' }} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="部分标注" value={(stats.partial as number) || 0} valueStyle={{ color: '#faad14' }} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title="未审核" value={(stats.unreviewed as number) || 0} />
            </Card>
          </Col>
        </Row>
      )}

      {confDist.length > 0 && (
        <Card title="置信度分布" style={{ marginBottom: 16 }}>
          <ReactECharts
            option={{
              tooltip: { trigger: 'axis' as const },
              xAxis: { type: 'category' as const, data: confDist.map((d) => d.range) },
              yAxis: { type: 'value' as const },
              series: [{
                type: 'bar',
                data: confDist.map((d) => d.count),
                itemStyle: { color: '#0071e3', borderRadius: [4, 4, 0, 0] },
              }],
              grid: { top: 10, right: 20, bottom: 30, left: 50 },
            }}
            style={{ height: 200 }}
          />
        </Card>
      )}

      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            placeholder="状态筛选"
            value={statusFilter || undefined}
            onChange={(v) => setStatusFilter(v || '')}
            allowClear
            style={{ width: 150 }}
          >
            <Option value="unreviewed">未审核</Option>
            <Option value="partial">部分标注</Option>
            <Option value="verified">已验证</Option>
          </Select>
          {selectedIds.length > 0 && (
            <Button type="primary" onClick={handleBatchApprove}>
              批量确认 ({selectedIds.length})
            </Button>
          )}
          <Button icon={<SyncOutlined />} onClick={handleRecompute}>重算置信度</Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>导出标注</Button>
          <Button icon={<DatabaseOutlined />} onClick={handleSync}>同步 database.json</Button>
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys as number[]),
          }}
          pagination={{
            current: page, pageSize: 20, total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="middle"
        />
      </Card>

      {/* Edit Annotation Modal */}
      <Modal
        title="编辑标注"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        okText="保存"
        width={600}
      >
        {detail && (
          <>
            <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="商品名">{(detail.product as Record<string, unknown>)?.title as string}</Descriptions.Item>
              <Descriptions.Item label="价格">¥{String((detail.product as Record<string, unknown>)?.price)}</Descriptions.Item>
            </Descriptions>
            <Form form={form} layout="vertical">
              <Form.Item name="color_family" label="颜色色系">
                <Input />
              </Form.Item>
              <Form.Item name="style_type" label="款式类型">
                <Select allowClear>
                  {['户外运动', '商务通勤', '日常休闲', '时尚潮流', '轻薄便携', '极寒防护', '亲子家庭'].map((s) => (
                    <Option key={s} value={s}>{s}</Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item name="body_fit" label="版型适配">
                <Input />
              </Form.Item>
              <Form.Item name="notes" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  )
}
