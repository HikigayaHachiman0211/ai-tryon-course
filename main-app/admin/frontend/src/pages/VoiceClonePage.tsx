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
import { useTranslation } from 'react-i18next'
import { detectInitialLocale } from '../i18n/locale'
import { resolveAdminApiBaseUrl } from '../utils/adminApi'

const { Title, Text } = Typography
const { TextArea } = Input

const API = resolveAdminApiBaseUrl({
  VITE_ADMIN_API_BASE_URL: import.meta.env.VITE_ADMIN_API_BASE_URL,
  VITE_ADMIN_API_URL: import.meta.env.VITE_ADMIN_API_URL,
})

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('admin_token')
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), 'Accept-Language': detectInitialLocale() }
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
  const { t } = useTranslation('common')
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
      if (!res.ok) throw new Error(t('errors.network'))
      setData(await res.json())
    } catch {
      message.error(t('errors.network'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleCreate = async () => {
    if (!newName.trim()) { message.warning(t('auth.requiredUsername')); return }
    setCreating(true)
    try {
      const form = new FormData()
      form.append('name', newName.trim())
      form.append('description', newDesc.trim())
      form.append('gender', newGender)
      form.append('language', newLanguage)
      form.append('locale', detectInitialLocale())

      const res = await fetch(`${API}/api/voice-clones`, {
        method: 'POST', headers: authHeaders(), body: form,
      })
      if (!res.ok) throw new Error(t('errors.unknown'))
      message.success(t('voice.referenceAudio'))
      setCreateOpen(false)
      setNewName(''); setNewDesc('')
      fetchData()
    } catch {
      message.error(t('errors.unknown'))
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
        throw new Error(t('images.uploadFailed'))
      }
      message.success(t('voice.uploadAudio'))
      fetchData()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('images.uploadFailed'))
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
        const errMsg = result.code ? t(`errors.${result.code}`, { defaultValue: t('errors.unknown') }) : t('errors.unknown')
        message.error(errMsg, 5)
        fetchData()
        return
      }
      message.success(t('voice.clone'))
      fetchData()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('errors.unknown'))
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
        throw new Error(t('errors.unknown'))
      }
      message.success(publish ? t('voice.publish') : t('voice.unpublish'))
      fetchData()
    } catch (e: unknown) {
      message.error(e instanceof Error ? e.message : t('errors.unknown'))
    }
  }

  const handleDelete = async (id: number) => {
    try {
      const res = await fetch(`${API}/api/voice-clones/${id}`, {
        method: 'DELETE', headers: authHeaders(),
      })
      if (!res.ok) throw new Error(t('errors.unknown'))
      message.success(t('voice.disable'))
      fetchData()
    } catch {
      message.error(t('errors.unknown'))
    }
  }

  const statusColors: Record<string, string> = {
    draft: 'default', cloning: 'processing', ready: 'success', failed: 'error',
  }

  const columns: ColumnsType<CloneProfile> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: t('voice.name'), dataIndex: 'name', width: 120 },
    { title: t('voice.gender'), dataIndex: 'gender', width: 60, render: (v) => v === 'female' ? t('voice.genderFemale') : t('voice.genderMale') },
    { title: t('voice.language'), dataIndex: 'language', width: 60 },
    {
      title: t('voice.status'), dataIndex: 'status', width: 80,
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
      title: t('voice.published'), dataIndex: 'is_published', width: 70,
      render: (v) => v ? <Tag color="green">{t('status.yes')}</Tag> : <Tag>{t('status.no')}</Tag>,
    },
    {
      title: t('actions.submit'), width: 300,
      render: (_, record) => (
        <Space size="small">
          {record.status === 'draft' && (
            <Upload
              accept=".wav,.mp3"
              showUploadList={false}
              beforeUpload={(file) => handleUpload(record.id, file as File)}
            >
              <Button size="small" icon={<UploadOutlined />}>{t('voice.uploadAudio')}</Button>
            </Upload>
          )}
          {record.status === 'draft' && (
            <Button
              size="small"
              type="primary"
              onClick={() => handleClone(record.id)}
              loading={cloneLoading === record.id}
            >
              {t('voice.clone')}
            </Button>
          )}
          {record.status === 'failed' && record.error_message?.includes('尚未接入') && (
            <Tooltip title={t('voice.notIntegrated')}>
              <Button size="small" disabled>{t('voice.cloneUnavailable')}</Button>
            </Tooltip>
          )}
          {record.status === 'ready' && !record.is_published && (
            <Button
              size="small" type="primary" ghost
              icon={<CheckCircleOutlined />}
              onClick={() => handlePublish(record.id, true)}
            >
              {t('voice.publish')}
            </Button>
          )}
          {record.is_published && (
            <Button
              size="small" danger ghost
              icon={<CloseCircleOutlined />}
              onClick={() => handlePublish(record.id, false)}
            >
              {t('voice.unpublish')}
            </Button>
          )}
          <Popconfirm title={t('voice.confirmDisable')} onConfirm={() => handleDelete(record.id)}>
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
          {t('voice.title')}
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          {t('voice.create')}
        </Button>
      </div>

      <Alert
        message={t('voice.apiStatus')}
        description={
          <>
            <Text>
              {t('voice.notIntegrated')}
            </Text>
            <ul style={{ margin: '8px 0 0 0', paddingLeft: 20 }}>
              <li>{t('voice.referenceAudio')}</li>
              <li>{t('voice.manageDrafts')}</li>
              <li>{t('voice.clone')} — {t('voice.notIntegrated')}</li>
              <li><Text strong>{t('voice.notPublished')}</Text></li>
            </ul>
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              {t('voice.adminReview')}
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
        title={t('voice.createTitle')}
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={creating}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text>{t('voice.name')} *</Text>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={t('voice.namePlaceholder')}
            />
          </div>
          <div>
            <Text>{t('voice.description')}</Text>
            <TextArea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder={t('voice.descriptionPlaceholder')}
              rows={2}
            />
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <Text>{t('voice.gender')}</Text>
              <Select
                value={newGender}
                onChange={setNewGender}
                style={{ width: '100%' }}
                options={[
                  { value: 'female', label: t('voice.genderFemale') },
                  { value: 'male', label: t('voice.genderMale') },
                ]}
              />
            </div>
            <div style={{ flex: 1 }}>
              <Text>{t('voice.language')}</Text>
              <Select
                value={newLanguage}
                onChange={setNewLanguage}
                style={{ width: '100%' }}
                options={[
                  { value: 'zh', label: t('voice.zh') },
                  { value: 'en', label: t('voice.en') },
                  { value: 'ja', label: t('voice.ja') },
                ]}
              />
            </div>
          </div>
        </Space>
      </Modal>
    </div>
  )
}
