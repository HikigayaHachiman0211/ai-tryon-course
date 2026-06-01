import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Input, Select, Space, Popconfirm, message, Tag, Image, Upload, Modal,
  Typography,
} from 'antd'
import { PlusOutlined, DeleteOutlined, SearchOutlined, UploadOutlined, LinkOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { listProducts, deleteProduct, batchDelete, importProducts, validateLinks } from '../api/products'

const { Title } = Typography
const { Option } = Select

interface Product {
  id: number
  title: string
  price: number
  image_url: string | null
  style_type: string
  color_family: string
  product_url: string | null
  annotation_status: string | null
  annotation_confidence: number | null
}

export default function ProductsPage() {
  const [data, setData] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [styleFilter, setStyleFilter] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const navigate = useNavigate()

  const fetchData = (p = page) => {
    setLoading(true)
    listProducts({ page: p, size: 20, keyword: search, style_type: styleFilter })
      .then((res) => {
        setData(res.data.items)
        setTotal(res.data.total)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData(1); setPage(1) }, [search, styleFilter])

  const handleDelete = async (id: number) => {
    await deleteProduct(id)
    message.success('已删除')
    fetchData()
  }

  const handleBatchDelete = async () => {
    await batchDelete(selectedIds)
    message.success(`已删除 ${selectedIds.length} 条`)
    setSelectedIds([])
    fetchData()
  }

  const handleImport = async () => {
    try {
      const jsonData = JSON.parse(importText)
      await importProducts(Array.isArray(jsonData) ? jsonData : [jsonData])
      message.success('导入成功')
      setImportModalOpen(false)
      setImportText('')
      fetchData()
    } catch {
      message.error('JSON 格式错误')
    }
  }

  const handleValidateLinks = async () => {
    const ids = selectedIds.length > 0 ? selectedIds : data.map((d) => d.id)
    const res = await validateLinks(ids)
    message.info(`验证完成: ${res.data.valid} 有效, ${res.data.invalid} 失效`)
    fetchData()
  }

  const columns: ColumnsType<Product> = [
    {
      title: '图片',
      dataIndex: 'image_url',
      width: 80,
      render: (url: string | null) => url ? <Image src={url} width={48} height={48} style={{ objectFit: 'cover', borderRadius: 4 }} /> : '-',
    },
    {
      title: '商品名称',
      dataIndex: 'title',
      ellipsis: true,
      render: (text: string, record: Product) => (
        <a onClick={() => navigate(`/products/${record.id}`)}>{text}</a>
      ),
    },
    { title: '价格', dataIndex: 'price', width: 100, render: (v: number) => `¥${v}` },
    { title: '款式', dataIndex: 'style_type', width: 100 },
    {
      title: '颜色',
      dataIndex: 'color_family',
      width: 100,
      render: (v: string) => v ? <Tag>{v}</Tag> : '-',
    },
    {
      title: '标注状态',
      dataIndex: 'annotation_status',
      width: 100,
      render: (v: string | null) => {
        const map: Record<string, string> = { verified: 'green', partial: 'orange', unreviewed: 'default' }
        return <Tag color={map[v || 'unreviewed'] || 'default'}>{v || '未审核'}</Tag>
      },
    },
    {
      title: '置信度',
      dataIndex: 'annotation_confidence',
      width: 80,
      render: (v: number | null) => v != null ? `${(v * 100).toFixed(0)}%` : '-',
    },
    {
      title: '链接',
      dataIndex: 'product_url',
      width: 60,
      render: (url: string | null) => url ? <a href={url} target="_blank" rel="noreferrer"><LinkOutlined /></a> : '-',
    },
    {
      title: '操作',
      width: 120,
      render: (_: unknown, record: Product) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/products/${record.id}`)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>商品管理</Title>
      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            placeholder="搜索商品名称..."
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 250 }}
            allowClear
          />
          <Select
            placeholder="款式筛选"
            value={styleFilter || undefined}
            onChange={(v) => setStyleFilter(v || '')}
            allowClear
            style={{ width: 150 }}
          >
            {['户外运动', '商务通勤', '日常休闲', '时尚潮流', '轻薄便携', '极寒防护', '亲子家庭'].map((s) => (
              <Option key={s} value={s}>{s}</Option>
            ))}
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/products/new')}>
            新增商品
          </Button>
          <Button icon={<UploadOutlined />} onClick={() => setImportModalOpen(true)}>
            JSON 导入
          </Button>
          <Button onClick={handleValidateLinks}>验证链接</Button>
          {selectedIds.length > 0 && (
            <Popconfirm title={`确认删除 ${selectedIds.length} 条？`} onConfirm={handleBatchDelete}>
              <Button danger>批量删除 ({selectedIds.length})</Button>
            </Popconfirm>
          )}
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
            current: page,
            pageSize: 20,
            total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="middle"
        />
      </Card>

      <Modal
        title="JSON 导入商品"
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        onOk={handleImport}
        width={600}
      >
        <Input.TextArea
          rows={12}
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder={'[\n  {"商品标题": "...", "价格": 299, "图片路径": "..."}\n]'}
        />
      </Modal>
    </div>
  )
}
