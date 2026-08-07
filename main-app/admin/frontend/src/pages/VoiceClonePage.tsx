import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Tag, Space, Modal, Input, message, Typography,
  Upload, Select, Descriptions, Popconfirm, Alert, Tooltip,
} from 'antd'
import {
  PlusOutlined, UploadOutlined, SoundOutlined,
  CheckCircleOutlined, CloseCircleOutlined, DeleteOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

const { Title, Text } = Typography
const { TextArea } = Input

const API = import.meta.env.VITE_ADMIN_API_URL || ''

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('admin_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

interface CloneProfile {
  id: number
  name: string
  description: string
  gender: string
  language: string
  provider_voice_id: string | null
  status: string
  enabled: boolean
  is_published: boolean
  error_message: string | null
  created_at: string
  updated_at: string
}

export default function VoiceClonePage() {
  const [data, setData] = useState<CloneProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newGender, setNewGender] = useState('female')
  const [newLanguage, setNewLanguage] = useState('zh')
  const [creating, setCreating] = useState(false)
  const [cloneLoading, setCloneLoading] = useState<number | null>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/voice-clones`, { headers: authHeaders() })
      if (!res.ok) throw new Error('Failed')
      setData(await res.json())
    } catch {
      message.error('加载声音克隆列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleCreate = async () => {
    if (!newName.trim()) { message.warning('请输入名称'); return }
    setCreating(true)
    try {
      const form = new FormData()
      form.append('name', newName.trim())
      form.append('description', newDesc.trim())
      form.append('gender', newGender)
      form.append('language', newLanguage)

      const res = await fetch(`${API}/api/voice-clones`, {
        method: 'POST', headers: authHeaders(), body: form,
      })
      if (!res.ok) throw new Error('Failed')
      message.success('创建成功，请上传参考音频')
      setCreateOpen(false)
      setNewName(''); setNewDesc('')
      fetchData()
    } catch {
      message.error('创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleUpload = async (id: number, file: File) => {
    const form = new FormData()
    form.append('audio', file)
    try {
      const res = await fetch(`${API}/api/voice-clones/${id}/upload`, {
        method: 'POST', headers: authHeaders(), body: form,
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Upload failed')
      }
      message.success('音频上传成功')
      fetchData()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '上传失败')
    }
    return false
  }

  const handleClone = async (id: number) => {
    setCloneLoading(id)
    try {
      const res = await fetch(`${API}/api/voice-clones/${id}/clone`, {
        method: 'POST', headers: authHeaders(),
      })
      const result = await res.json()
      if (!res.ok || !result.ok) {
        // Show the specific error from backend
        const errMsg = result.message || result.detail || '克隆失败'
        message.error(errMsg, 5)
        fetchData()
        return
      }
      message.success('克隆完成')
      fetchData()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '克隆失败')
    } finally {
      setCloneLoading(null)
    }
  }

  const handlePublish = async (id: number, publish: boolean) => {
    const endpoint = publish ? 'publish' : 'unpublish'
    try {
      const res = await fetch(`${API}/api/voice-clones/${id}/${endpoint}`, {
        method: 'POST', headers: authHeaders(),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed')
      }
      message.success(publish ? '已发布' : '已下架')
      fetchData()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : '操作失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      const res = await fetch(`${API}/api/voice-clones/${id}`, {
        method: 'DELETE', headers: authHeaders(),
      })
      if (!res.ok) throw new Error('Failed')
      message.success('已禁用')
      fetchData()
    } catch {
      message.error('操作失败')
    }
  }

  const statusColors: Record<string, string> = {
    draft: 'default', cloning: 'processing', ready: 'success', failed: 'error',
  }

  const columns: ColumnsType<CloneProfile> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', width: 120 },
    { title: '性别', dataIndex: 'gender', width: 60, render: (v) => v === 'female' ? '女' : '男' },
    { title: '语言', dataIndex: 'language', width: 60 },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v, record) => (
        <Tooltip title={record.error_message || undefined}>
          <Tag color={statusColors[v] || 'default'}>
            {v}
            {record.error_message && <WarningOutlined style={{ marginLeft: 4 }} />}
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: '已发布', dataIndex: 'is_published', width: 70,
      render: (v) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag>,
    },
    {
      title: '操作', width: 300,
      render: (_, record) => (
        <Space size="small">
          {record.status === 'draft' && (
            <Upload
              accept=".wav,.mp3"
              showUploadList={false}
              beforeUpload={(file) => handleUpload(record.id, file as File)}
            >
              <Button size="small" icon={<UploadOutlined />}>上传音频</Button>
            </Upload>
          )}
          {record.status === 'draft' && (
            <Button
              size="small"
              type="primary"
              onClick={() => handleClone(record.id)}
              loading={cloneLoading === record.id}
            >
              克隆
            </Button>
          )}
          {record.status === 'failed' && record.error_message?.includes('尚未接入') && (
            <Tooltip title="MiMo VoiceClone API 尚未接入，无法执行克隆">
              <Button size="small" disabled>克隆（未接入）</Button>
            </Tooltip>
          )}
          {record.status === 'ready' && !record.is_published && (
            <Button
              size="small" type="primary" ghost
              icon={<CheckCircleOutlined />}
              onClick={() => handlePublish(record.id, true)}
            >
              发布
            </Button>
          )}
          {record.is_published && (
            <Button
              size="small" danger ghost
              icon={<CloseCircleOutlined />}
              onClick={() => handlePublish(record.id, false)}
            >
              下架
            </Button>
          )}
          <Popconfirm title="确认禁用？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <SoundOutlined style={{ marginRight: 8 }} />
          声音克隆管理
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          新建克隆音色
        </Button>
      </div>

      <Alert
        message="声音克隆接口状态"
        description={
          <>
            <Text>
              MiMo VoiceClone API 尚未正式接入。当前功能支持：
            </Text>
            <ul style={{ margin: '8px 0 0 0', paddingLeft: 20 }}>
              <li>上传参考音频（WAV/MP3，校验真实文件头）</li>
              <li>创建和管理音色草稿</li>
              <li>点击"克隆"将尝试调用 API，若未接入会返回明确错误</li>
              <li><Text strong>未成功克隆的音色无法发布到主站</Text></li>
            </ul>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              普通主站用户不可上传声音样本。所有克隆音色必须经后台审核发布后才可在主站使用。
            </Text>
          </>
        }
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Card>
        <Table
          dataSource={data}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={data.length > 20 ? { pageSize: 20 } : false}
          scroll={{ x: 800 }}
        />
      </Card>

      <Modal
        title="新建克隆音色"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={creating}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text>名称 *</Text>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="例如：温柔女声-小雪"
            />
          </div>
          <div>
            <Text>描述</Text>
            <TextArea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="音色描述"
              rows={2}
            />
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <Text>性别</Text>
              <Select
                value={newGender}
                onChange={setNewGender}
                style={{ width: '100%' }}
                options={[
                  { value: 'female', label: '女' },
                  { value: 'male', label: '男' },
                ]}
              />
            </div>
            <div style={{ flex: 1 }}>
              <Text>语言</Text>
              <Select
                value={newLanguage}
                onChange={setNewLanguage}
                style={{ width: '100%' }}
                options={[
                  { value: 'zh', label: '中文' },
                  { value: 'en', label: 'English' },
                ]}
              />
            </div>
          </div>
        </Space>
      </Modal>
    </div>
  )
}
