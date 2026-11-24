import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Image, Tag, Upload, Modal, Form, Input, Select, InputNumber,
  Popconfirm, message, Typography, Switch, Row, Col,
} from 'antd'
import { PlusOutlined, UploadOutlined, DeleteOutlined, SortAscendingOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  listSampleModels, uploadSampleModel, updateSampleModel, deleteSampleModel,
  batchDeleteModels, batchStatus,
} from '../api/sampleModels'
import { useTranslation } from 'react-i18next'

const { Title } = Typography
const { Option } = Select

interface SampleModel {
  id: number
  name: string
  gender: string
  gcs_url: string
  display_order: number
  is_active: boolean
  uploaded_by: string
  created_at: string
  file_size: number
  image_width: number | null
  image_height: number | null
}

export default function SampleModelsPage() {
  const { t } = useTranslation('common')
  const [data, setData] = useState<SampleModel[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [genderFilter, setGenderFilter] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [uploadOpen, setUploadOpen] = useState(false)
  const [form] = Form.useForm()
  const [uploading, setUploading] = useState(false)
  const [fileList, setFileList] = useState<File[]>([])

  const fetchData = (p = page) => {
    setLoading(true)
    listSampleModels({ page: p, size: 50, gender: genderFilter })
      .then((res) => { setData(res.data.items || []); setTotal(res.data.total || 0) })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData(1); setPage(1) }, [genderFilter])

  const handleUpload = async () => {
    if (fileList.length === 0) { message.warning(t('samples.selectImage')); return }
    const values = form.getFieldsValue()
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('image', fileList[0])
      fd.append('name', values.name)
      fd.append('gender', values.gender)
      fd.append('display_order', String(values.display_order || 0))
      await uploadSampleModel(fd)
      message.success(t('images.uploadSuccess'))
      setUploadOpen(false)
      form.resetFields()
      setFileList([])
      fetchData()
    } catch {
      message.error(t('images.uploadFailed'))
    } finally {
      setUploading(false)
    }
  }

  const handleToggleActive = async (id: number, active: boolean) => {
    await updateSampleModel(id, { is_active: active })
    fetchData()
  }

  const handleDelete = async (id: number) => {
    await deleteSampleModel(id)
    message.success(t('products.deleted'))
    fetchData()
  }

  const handleBatchDelete = async () => {
    await batchDeleteModels(selectedIds)
    message.success(t('messages.deletedCount', { count: selectedIds.length }))
    setSelectedIds([])
    fetchData()
  }

  const handleBatchActivate = async (active: boolean) => {
    await batchStatus(selectedIds, active)
    message.success(t('status.enabled'))
    setSelectedIds([])
    fetchData()
  }

  const columns: ColumnsType<SampleModel> = [
    {
      title: t('samples.image'), dataIndex: 'gcs_url', width: 80,
      render: (url: string) => <Image src={url} width={48} height={64} style={{ objectFit: 'cover', borderRadius: 4 }} />,
    },
    { title: t('samples.name'), dataIndex: 'name', width: 150 },
    {
      title: t('samples.gender'), dataIndex: 'gender', width: 80,
      render: (v: string) => <Tag color={v === '男' ? 'blue' : 'pink'}>{v === '男' ? t('samples.male') : t('samples.female')}</Tag>,
    },
    { title: t('samples.order'), dataIndex: 'display_order', width: 80 },
    {
      title: t('samples.active'), dataIndex: 'is_active', width: 80,
      render: (v: boolean, record) => (
        <Switch checked={v} size="small" onChange={(c) => handleToggleActive(record.id, c)} />
      ),
    },
    {
      title: t('samples.size'), width: 120,
      render: (_, r) => r.image_width ? `${r.image_width}×${r.image_height}` : '-',
    },
    {
      title: t('samples.fileSize'), dataIndex: 'file_size', width: 80,
      render: (v: number) => v ? `${(v / 1024).toFixed(0)} KB` : '-',
    },
    { title: t('samples.uploadedBy'), dataIndex: 'uploaded_by', width: 100 },
    { title: t('samples.createdAt'), dataIndex: 'created_at', width: 180 },
    {
      title: t('actions.submit'), width: 80,
      render: (_, record) => (
        <Popconfirm title={t('products.confirmDelete')} onConfirm={() => handleDelete(record.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('samples.title')}</Title>
      <Card>
        <Space wrap style={{ marginBottom: 16, width: '100%' }}>
          <Select
            className="admin-toolbar-input"
            placeholder={t('samples.filterGender')}
            value={genderFilter || undefined}
            onChange={(v) => setGenderFilter(v || '')}
            allowClear
            style={{ width: 120 }}
          >
            <Option value="男">{t('samples.male')}</Option>
            <Option value="女">{t('samples.female')}</Option>
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
            {t('samples.upload')}
          </Button>
          {selectedIds.length > 0 && (
            <>
              <Button onClick={() => handleBatchActivate(true)}>{t('samples.batchEnable')}</Button>
              <Button onClick={() => handleBatchActivate(false)}>{t('samples.batchDisable')}</Button>
              <Popconfirm title={t('samples.confirmDelete', { count: selectedIds.length })} onConfirm={handleBatchDelete}>
                <Button danger>{t('samples.batchDelete')}</Button>
              </Popconfirm>
            </>
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
            current: page, pageSize: 50, total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (count) => t('pagination.items', { count }),
          }}
          size="middle"
        />
      </Card>

      <Modal
        title={t('samples.uploadTitle')}
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={handleUpload}
        confirmLoading={uploading}
        okText={t('actions.upload')}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={t('samples.modelName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="gender" label={t('samples.gender')} rules={[{ required: true }]}>
            <Select>
              <Option value="男">{t('samples.male')}</Option>
              <Option value="女">{t('samples.female')}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="display_order" label={t('samples.order')}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label={t('samples.file')}>
            <Upload
              beforeUpload={(file) => { setFileList([file]); return false }}
              fileList={fileList.map((f) => ({ uid: f.name, name: f.name, status: 'done' as const }))}
              onRemove={() => setFileList([])}
              accept="image/*"
              maxCount={1}
            >
              <Button icon={<UploadOutlined />}>{t('samples.chooseFile')}</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
