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
    if (fileList.length === 0) { message.warning('请选择图片'); return }
    const values = form.getFieldsValue()
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('image', fileList[0])
      fd.append('name', values.name)
      fd.append('gender', values.gender)
      fd.append('display_order', String(values.display_order || 0))
      await uploadSampleModel(fd)
      message.success('上传成功')
      setUploadOpen(false)
      form.resetFields()
      setFileList([])
      fetchData()
    } catch {
      message.error('上传失败')
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
    message.success('已删除')
    fetchData()
  }

  const handleBatchDelete = async () => {
    await batchDeleteModels(selectedIds)
    message.success(`已删除 ${selectedIds.length} 个`)
    setSelectedIds([])
    fetchData()
  }

  const handleBatchActivate = async (active: boolean) => {
    await batchStatus(selectedIds, active)
    message.success('状态已更新')
    setSelectedIds([])
    fetchData()
  }

  const columns: ColumnsType<SampleModel> = [
    {
      title: '图片', dataIndex: 'gcs_url', width: 80,
      render: (url: string) => <Image src={url} width={48} height={64} style={{ objectFit: 'cover', borderRadius: 4 }} />,
    },
    { title: '名称', dataIndex: 'name', width: 150 },
    {
      title: '性别', dataIndex: 'gender', width: 80,
      render: (v: string) => <Tag color={v === '男' ? 'blue' : 'pink'}>{v}</Tag>,
    },
    { title: '排序', dataIndex: 'display_order', width: 80 },
    {
      title: '启用', dataIndex: 'is_active', width: 80,
      render: (v: boolean, record) => (
        <Switch checked={v} size="small" onChange={(c) => handleToggleActive(record.id, c)} />
      ),
    },
    {
      title: '尺寸', width: 120,
      render: (_, r) => r.image_width ? `${r.image_width}×${r.image_height}` : '-',
    },
    {
      title: '大小', dataIndex: 'file_size', width: 80,
      render: (v: number) => v ? `${(v / 1024).toFixed(0)} KB` : '-',
    },
    { title: '上传者', dataIndex: 'uploaded_by', width: 100 },
    { title: '创建时间', dataIndex: 'created_at', width: 180 },
    {
      title: '操作', width: 80,
      render: (_, record) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>示例模特管理</Title>
      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadOpen(true)}>
            上传模特
          </Button>
          {selectedIds.length > 0 && (
            <>
              <Button onClick={() => handleBatchActivate(true)}>批量启用</Button>
              <Button onClick={() => handleBatchActivate(false)}>批量停用</Button>
              <Popconfirm title={`确认删除 ${selectedIds.length} 个？`} onConfirm={handleBatchDelete}>
                <Button danger>批量删除</Button>
              </Popconfirm>
            </>
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
            current: page, pageSize: 50, total,
            onChange: (p) => { setPage(p); fetchData(p) },
            showTotal: (t) => `共 ${t} 个`,
          }}
          size="middle"
        />
      </Card>

      <Modal
        title="上传示例模特"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={handleUpload}
        confirmLoading={uploading}
        okText="上传"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="模特名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="gender" label="性别" rules={[{ required: true }]}>
            <Select>
              <Option value="男">男</Option>
              <Option value="女">女</Option>
            </Select>
          </Form.Item>
          <Form.Item name="display_order" label="排序">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="图片">
            <Upload
              beforeUpload={(file) => { setFileList([file]); return false }}
              fileList={fileList.map((f) => ({ uid: f.name, name: f.name, status: 'done' as const }))}
              onRemove={() => setFileList([])}
              accept="image/*"
              maxCount={1}
            >
              <Button icon={<UploadOutlined />}>选择文件</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
