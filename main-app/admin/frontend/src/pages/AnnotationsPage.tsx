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
import { useTranslation } from 'react-i18next'

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

export function annotationFormValues(product: Record<string, unknown>): Record<string, unknown> {
  const canonical = product.canonical && typeof product.canonical === 'object'
    ? product.canonical as Record<string, unknown>
    : product
  return { color_family: canonical.color_family, style_type: canonical.style_type, body_fit: canonical.body_fit }
}

export default function AnnotationsPage() {
  const { t, i18n } = useTranslation('common')
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

  useEffect(() => { fetchData(1); setPage(1); fetchStats() }, [statusFilter, i18n.resolvedLanguage])

  const openEdit = async (productId: number) => {
    const res = await getAnnotation(productId)
    setDetail(res.data)
    const p = res.data.product
    form.setFieldsValue(annotationFormValues(p))
    setEditOpen(true)
  }

  const handleSave = async () => {
    if (!detail) return
    const values = form.getFieldsValue()
    const product = detail.product as Record<string, unknown>
    await updateAnnotation(product.id as number, values)
    message.success(t('annotations.saved'))
    setEditOpen(false)
    fetchData()
  }

  const handleApprove = async (id: number) => {
    await approveAnnotation(id)
    message.success(t('annotations.confirmed'))
    fetchData()
    fetchStats()
  }

  const handleReject = async (id: number) => {
    await rejectAnnotation(id, '')
    message.success(t('annotations.rejected'))
    fetchData()
  }

  const handleBatchApprove = async () => {
    await batchApprove(selectedIds)
    message.success(t('annotations.bulkConfirm', { count: selectedIds.length }))
    setSelectedIds([])
    fetchData()
    fetchStats()
  }

  const handleRecompute = async () => {
    const res = await recomputeConfidence()
    message.success(t('annotations.recomputed', { count: res.data.recomputed }))
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
    message.success(t('annotations.synced', { count: res.data.total }))
  }

  const confDist = (stats?.confidence_distribution as { range: string; count: number }[]) || []

  const columns: ColumnsType<AnnotationItem> = [
    { title: t('annotations.product'), dataIndex: 'title', ellipsis: true },
    { title: t('annotations.style'), dataIndex: 'style_type', width: 100 },
    { title: t('annotations.color'), dataIndex: 'color_family', width: 100, render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
    {
      title: t('annotations.state'),
      dataIndex: 'annotation_status',
      width: 100,
      render: (v: string | null) => {
        const m: Record<string, string> = { verified: 'green', partial: 'orange', unreviewed: 'default' }
        return <Tag color={m[v || ''] || 'default'}>{v ? t(`status.${v}`, { defaultValue: v }) : t('status.unreviewed')}</Tag>
      },
    },
    {
      title: t('annotations.confidence'),
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
      title: t('annotations.priority'),
      width: 80,
      render: (_, record) => {
        const p = record.task?.priority
        if (p === 2) return <Tag color="red">{t('priority.high', { defaultValue: 'High' })}</Tag>
        if (p === 1) return <Tag color="orange">{t('priority.medium', { defaultValue: 'Medium' })}</Tag>
        return <Tag>{t('priority.low', { defaultValue: 'Low' })}</Tag>
      },
    },
    { title: t('annotations.lastAnnotated'), dataIndex: 'last_annotated_by', width: 100 },
    {
      title: t('actions.submit'),
      width: 180,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record.id)}>{t('actions.edit')}</Button>
          <Button size="small" type="primary" ghost icon={<CheckOutlined />} onClick={() => handleApprove(record.id)}>
            {t('actions.confirm')}
          </Button>
          <Popconfirm title={t('actions.confirm')} onConfirm={() => handleReject(record.id)}>
            <Button size="small" danger icon={<CloseOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('annotations.title')}</Title>

      {stats && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title={t('annotations.total')} value={(stats.total as number) || 0} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title={t('annotations.verified')} value={(stats.verified as number) || 0} valueStyle={{ color: '#52c41a' }} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title={t('annotations.partial')} value={(stats.partial as number) || 0} valueStyle={{ color: '#faad14' }} />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card className="stat-card">
              <Statistic title={t('annotations.unreviewed')} value={(stats.unreviewed as number) || 0} />
            </Card>
          </Col>
        </Row>
      )}

      {confDist.length > 0 && (
        <Card title={t('annotations.confidenceDistribution')} style={{ marginBottom: 16 }}>
          <ReactECharts
            option={{
              tooltip: { trigger: 'axis' as const, confine: true },
              xAxis: { type: 'category' as const, data: confDist.map((d) => d.range) },
              yAxis: { type: 'value' as const },
              series: [{
                type: 'bar',
                data: confDist.map((d) => d.count),
                itemStyle: { color: '#0071e3', borderRadius: [4, 4, 0, 0] },
              }],
              grid: { top: 16, right: 16, bottom: 20, left: 16, containLabel: true },
            }}
            style={{ height: 200 }}
          />
        </Card>
      )}

      <Card>
        <Space wrap style={{ marginBottom: 16, width: '100%' }}>
          <Select
            className="admin-toolbar-input"
            placeholder={t('annotations.statusFilter')}
            value={statusFilter || undefined}
            onChange={(v) => setStatusFilter(v || '')}
            allowClear
            style={{ width: 150 }}
          >
            <Option value="unreviewed">{t('status.unreviewed')}</Option>
            <Option value="partial">{t('status.partial')}</Option>
            <Option value="verified">{t('status.verified')}</Option>
          </Select>
          {selectedIds.length > 0 && (
            <Button type="primary" onClick={handleBatchApprove}>
              {t('annotations.bulkConfirm', { count: selectedIds.length })}
            </Button>
          )}
          <Button icon={<SyncOutlined />} onClick={handleRecompute}>{t('annotations.recompute')}</Button>
          <Button icon={<ExportOutlined />} onClick={handleExport}>{t('annotations.export')}</Button>
          <Button icon={<DatabaseOutlined />} onClick={handleSync}>{t('annotations.sync')}</Button>
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 'max-content' }}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys as number[]),
          }}
          pagination={{
            current: page, pageSize: 20, total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (count) => t('pagination.total', { count }),
          }}
          size="middle"
        />
      </Card>

      {/* Edit Annotation Modal */}
      <Modal
        title={t('annotations.editTitle')}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        okText={t('actions.save')}
        width={600}
      >
        {detail && (
          <>
            <Descriptions size="small" column={{ xs: 1, sm: 2 }} style={{ marginBottom: 16 }}>
              <Descriptions.Item label={t('annotations.productName')}>{(detail.product as Record<string, unknown>)?.title as string}</Descriptions.Item>
              <Descriptions.Item label={t('annotations.price')}>¥{String((detail.product as Record<string, unknown>)?.price)}</Descriptions.Item>
            </Descriptions>
            <Form form={form} layout="vertical">
              <Form.Item name="color_family" label={t('products.color')}>
                <Input />
              </Form.Item>
              <Form.Item name="style_type" label={t('annotations.styleType')}>
                <Select allowClear>
                  {[
                    ['户外运动', 'options.styles.outdoor'], ['商务通勤', 'options.styles.business'], ['日常休闲', 'options.styles.casual'],
                    ['时尚潮流', 'options.styles.fashion'], ['轻薄便携', 'options.styles.light'], ['极寒防护', 'options.styles.cold'], ['亲子家庭', 'options.styles.family'],
                  ].map(([value, key]) => (
                    <Option key={value} value={value}>{t(key)}</Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item name="body_fit" label={t('annotations.bodyFit')}>
                <Input />
              </Form.Item>
              <Form.Item name="notes" label={t('annotations.notes')}>
                <Input.TextArea rows={2} />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  )
}
