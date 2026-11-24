import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Input, Select, Space, Popconfirm, message, Tag, Image, Upload, Modal,
  Typography,
} from 'antd'
import { PlusOutlined, DeleteOutlined, SearchOutlined, UploadOutlined, LinkOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { listProducts, deleteProduct, batchDelete, importProducts, validateLinks } from '../api/products'
import { useTranslation } from 'react-i18next'
import { formatCurrency } from '../i18n/formatters'
import type { AppLocale } from '../i18n/locale'

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
  const { t, i18n } = useTranslation('common')
  const locale = (i18n.language === 'en' || i18n.language === 'ja' ? i18n.language : 'zh-CN') as AppLocale
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

  useEffect(() => { fetchData(1); setPage(1) }, [search, styleFilter, i18n.resolvedLanguage])

  const handleDelete = async (id: number) => {
    await deleteProduct(id)
    message.success(t('products.deleted'))
    fetchData()
  }

  const handleBatchDelete = async () => {
    await batchDelete(selectedIds)
    message.success(t('messages.deletedCount', { count: selectedIds.length }))
    setSelectedIds([])
    fetchData()
  }

  const handleImport = async () => {
    try {
      const jsonData = JSON.parse(importText)
      await importProducts(Array.isArray(jsonData) ? jsonData : [jsonData])
      message.success(t('products.imported'))
      setImportModalOpen(false)
      setImportText('')
      fetchData()
    } catch {
      message.error(t('products.invalidJson'))
    }
  }

  const handleValidateLinks = async () => {
    const ids = selectedIds.length > 0 ? selectedIds : data.map((d) => d.id)
    const res = await validateLinks(ids)
    message.info(t('products.validationComplete', { valid: res.data.valid, invalid: res.data.invalid }))
    fetchData()
  }

  const columns: ColumnsType<Product> = [
    {
      title: t('products.image'),
      dataIndex: 'image_url',
      width: 80,
      render: (url: string | null) => url ? <Image src={url} width={48} height={48} style={{ objectFit: 'cover', borderRadius: 4 }} /> : '-',
    },
    {
      title: t('products.name'),
      dataIndex: 'title',
      ellipsis: true,
      render: (text: string, record: Product) => (
        <a onClick={() => navigate(`/products/${record.id}`)}>{text}</a>
      ),
    },
    { title: t('products.price'), dataIndex: 'price', width: 100, render: (v: number) => formatCurrency(v, locale) },
    { title: t('products.style'), dataIndex: 'style_type', width: 100 },
    {
      title: t('products.color'),
      dataIndex: 'color_family',
      width: 100,
      render: (v: string) => v ? <Tag>{v}</Tag> : '-',
    },
    {
      title: t('products.reviewStatus'),
      dataIndex: 'annotation_status',
      width: 100,
      render: (v: string | null) => {
        const map: Record<string, string> = { verified: 'green', partial: 'orange', unreviewed: 'default' }
        return <Tag color={map[v || 'unreviewed'] || 'default'}>{v ? t(`status.${v}`, { defaultValue: v }) : t('status.unreviewed')}</Tag>
      },
    },
    {
      title: t('products.confidence'),
      dataIndex: 'annotation_confidence',
      width: 80,
      render: (v: number | null) => v != null ? `${(v * 100).toFixed(0)}%` : '-',
    },
    {
      title: t('products.link'),
      dataIndex: 'product_url',
      width: 60,
      render: (url: string | null) => url ? <a href={url} target="_blank" rel="noreferrer"><LinkOutlined /></a> : '-',
    },
    {
      title: t('actions.submit'),
      width: 120,
      render: (_: unknown, record: Product) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/products/${record.id}`)}>{t('actions.edit')}</Button>
          <Popconfirm title={t('products.confirmDelete')} onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('products.title')}</Title>
      <Card>
        <Space wrap style={{ marginBottom: 16, width: '100%' }}>
          <Input
            className="admin-toolbar-input"
            placeholder={t('products.searchPlaceholder')}
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 250 }}
            allowClear
          />
          <Select
            className="admin-toolbar-input"
            placeholder={t('products.styleFilter')}
            value={styleFilter || undefined}
            onChange={(v) => setStyleFilter(v || '')}
            allowClear
            style={{ width: 150 }}
          >
            {[
              ['户外运动', 'options.styles.outdoor'], ['商务通勤', 'options.styles.business'], ['日常休闲', 'options.styles.casual'],
              ['时尚潮流', 'options.styles.fashion'], ['轻薄便携', 'options.styles.light'], ['极寒防护', 'options.styles.cold'], ['亲子家庭', 'options.styles.family'],
            ].map(([value, key]) => (
              <Option key={value} value={value}>{t(key)}</Option>
            ))}
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/products/new')}>
            {t('products.add')}
          </Button>
          <Button icon={<UploadOutlined />} onClick={() => setImportModalOpen(true)}>
            {t('products.importJson')}
          </Button>
          <Button onClick={handleValidateLinks}>{t('products.validateLinks')}</Button>
          {selectedIds.length > 0 && (
            <Popconfirm title={t('products.confirmDeleteCount', { count: selectedIds.length })} onConfirm={handleBatchDelete}>
              <Button danger>{t('products.batchDelete', { count: selectedIds.length })}</Button>
            </Popconfirm>
          )}
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
            current: page,
            pageSize: 20,
            total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (count) => t('pagination.total', { count }),
          }}
          size="middle"
        />
      </Card>

      <Modal
        title={t('products.importTitle')}
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        onOk={handleImport}
        width={600}
      >
        <Input.TextArea
          rows={12}
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder={t('products.jsonPlaceholder')}
        />
      </Modal>
    </div>
  )
}
