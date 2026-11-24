import { useState, useEffect } from 'react'
import { Card, Table, Button, Tag, Space, Modal, Input, message, Typography, Select, Descriptions, Grid } from 'antd'
import { EditOutlined, HistoryOutlined, PlayCircleOutlined, UndoOutlined, EyeOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import Editor from '@monaco-editor/react'
import { listPrompts, getPrompt, updatePrompt, testPrompt, previewPrompt, getVersions, restoreDefault } from '../api/prompts'
import { useTranslation } from 'react-i18next'

const { Title, Text } = Typography

interface PromptItem {
  id: number
  name: string
  display_name: string
  description: string
  category: string
  prompt_type: string
  locale: string
  version: number
  is_active: boolean
  updated_at: string
  updated_by: string
}

const CATEGORY_OPTIONS = ['', 'image_analysis', 'text_analysis', 'recommendation', 'assistant', 'tryon', 'voice', 'voice_call', 'voice_clone']
const TYPE_OPTIONS = [
  '',
  { value: 'system', label: 'System' },
  { value: 'user', label: 'User' },
]

export default function PromptsPage() {
  const { t, i18n } = useTranslation('common')
  const screens = Grid.useBreakpoint()
  const isMobile = screens.md === false
  const [data, setData] = useState<PromptItem[]>([])
  const [loading, setLoading] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [current, setCurrent] = useState<Record<string, unknown> | null>(null)
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [testOpen, setTestOpen] = useState(false)
  const [testVars, setTestVars] = useState('')
  const [testResult, setTestResult] = useState('')
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewVars, setPreviewVars] = useState('')
  const [previewResult, setPreviewResult] = useState('')

  // Filters
  const [filterCategory, setFilterCategory] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterKeyword, setFilterKeyword] = useState('')

  const fetchData = () => {
    setLoading(true)
    const params: Record<string, unknown> = {}
    if (filterCategory) params.category = filterCategory
    if (filterType) params.prompt_type = filterType
    if (filterKeyword) params.keyword = filterKeyword
    listPrompts(params as { category?: string; prompt_type?: string; is_active?: boolean; keyword?: string })
      .then((res) => setData(res.data || []))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData() }, [filterCategory, filterType, i18n.language])

  const openEdit = async (id: number) => {
    const res = await getPrompt(id)
    setCurrent(res.data)
    setContent(res.data.content || '')
    setEditOpen(true)
  }

  const handleSave = async () => {
    if (!current) return
    setSaving(true)
    try {
      await updatePrompt(current.id as number, { content })
      message.success(t('prompts.saved'))
      setEditOpen(false)
      fetchData()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('prompts.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    if (!current) return
    try {
      const vars = testVars ? JSON.parse(testVars) : {}
      const res = await testPrompt(current.id as number, vars)
      setTestResult(res.data.output || JSON.stringify(res.data, null, 2))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setTestResult(`Error: ${err.response?.data?.detail || t('prompts.testFailed')}`)
    }
  }

  const handlePreview = async () => {
    if (!current) return
    try {
      const vars = previewVars ? JSON.parse(previewVars) : {}
      const res = await previewPrompt(content || (current.content as string) || '', vars)
      setPreviewResult(res.data.preview || '')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setPreviewResult(`Error: ${err.response?.data?.detail || t('prompts.previewFailed')}`)
    }
  }

  const handleRestoreDefault = async (id: number) => {
    try {
      await restoreDefault(id)
      message.success(t('prompts.restore'))
      fetchData()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.unknown'))
    }
  }

  const showVersions = async (id: number) => {
    const res = await getVersions(id)
    setVersions(res.data?.items || res.data || [])
    setCurrent({ id } as Record<string, unknown>)
    setVersionsOpen(true)
  }

  const columns: ColumnsType<PromptItem> = [
    { title: t('prompts.name'), dataIndex: 'name', width: 200, ellipsis: true },
    { title: t('prompts.displayName'), dataIndex: 'display_name', width: 160, ellipsis: true },
    { title: t('prompts.locale'), dataIndex: 'locale', width: 100 },
    {
      title: t('prompts.category'),
      dataIndex: 'category',
      width: 100,
      render: (v: string) => {
        const labels: Record<string, string> = {
          image_analysis: t('prompts.imageAnalysis'), text_analysis: t('prompts.textAnalysis'), recommendation: t('prompts.recommendation'),
          assistant: t('prompts.assistant'), tryon: t('prompts.tryon'), voice: t('prompts.voice'),
          voice_call: t('prompts.voiceCall'), voice_clone: t('prompts.voiceClone'),
        }
        return labels[v] || v || '-'
      },
    },
    {
      title: t('prompts.type'),
      dataIndex: 'prompt_type',
      width: 80,
      render: (v: string) => v || '-',
    },
    { title: t('prompts.version'), dataIndex: 'version', width: 70, render: (v: number) => `v${v}` },
    {
      title: t('prompts.state'),
      dataIndex: 'is_active',
      width: 70,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? t('status.enabled') : t('status.disabled')}</Tag>,
    },
    { title: t('prompts.updatedBy'), dataIndex: 'updated_by', width: 100, ellipsis: true },
    { title: t('prompts.updatedAt'), dataIndex: 'updated_at', width: 160 },
    {
      title: t('actions.submit'),
      width: 280,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record.id)}>{t('actions.edit')}</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => showVersions(record.id)}>{t('prompts.history')}</Button>
          <Button size="small" icon={<UndoOutlined />} onClick={() => handleRestoreDefault(record.id)}>{t('prompts.restore')}</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('prompts.title')}</Title>

      {/* Filters */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap style={{ width: '100%' }}>
          <Select
            className="admin-toolbar-input"
            value={filterCategory}
            onChange={setFilterCategory}
            style={{ width: 150 }}
            options={CATEGORY_OPTIONS.map((value) => ({ value, label: value ? t(`prompts.${value === 'image_analysis' ? 'imageAnalysis' : value === 'text_analysis' ? 'textAnalysis' : value === 'recommendation' ? 'recommendation' : value === 'assistant' ? 'assistant' : value === 'tryon' ? 'tryon' : value === 'voice' ? 'voice' : value === 'voice_call' ? 'voiceCall' : 'voiceClone'}`) : t('prompts.allCategories') }))}
          />
          <Select
            className="admin-toolbar-input"
            value={filterType}
            onChange={setFilterType}
            style={{ width: 130 }}
            options={TYPE_OPTIONS.map((item) => typeof item === 'string' ? { value: item, label: t('prompts.allTypes') } : item)}
          />
          <Input.Search
            className="admin-toolbar-input"
            placeholder={t('prompts.searchPlaceholder')}
            value={filterKeyword}
            onChange={(e) => setFilterKeyword(e.target.value)}
            onSearch={fetchData}
            style={{ width: 220 }}
            allowClear
          />
        </Space>
      </Card>

      <Card>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={false}
          size="middle"
          scroll={{ x: 1200 }}
        />
      </Card>

      {/* Edit Modal */}
      <Modal
        title={t('prompts.editTitle', { name: (current as Record<string, unknown>)?.name || '' })}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        width={900}
        footer={
          <Space wrap>
            <Button onClick={() => { setPreviewOpen(true); setPreviewResult(''); setPreviewVars('') }}>
              <EyeOutlined /> {t('actions.preview')}
            </Button>
            <Button onClick={() => { setTestOpen(true); setTestResult('') }}>
              <PlayCircleOutlined /> {t('actions.test')}
            </Button>
            <Button onClick={() => setEditOpen(false)}>{t('actions.cancel')}</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>{t('actions.save')}</Button>
          </Space>
        }
      >
        {current && (
          <div style={{ marginBottom: 12 }}>
            <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }}>
              <Descriptions.Item label={t('prompts.category')}>{(current as Record<string, unknown>).category as string || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('prompts.type')}>{(current as Record<string, unknown>).prompt_type as string || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('prompts.description')}>{(current as Record<string, unknown>).description as string || '-'}</Descriptions.Item>
            </Descriptions>
          </div>
        )}
        <div style={{ border: '1px solid #d9d9d9', borderRadius: 8, overflow: 'hidden' }}>
          {isMobile ? (
            <Input.TextArea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              autoSize={{ minRows: 12, maxRows: 24 }}
              style={{ border: 0, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 16 }}
            />
          ) : (
            <Editor
              height="400px"
              language="markdown"
              value={content}
              onChange={(v) => setContent(v || '')}
              options={{ minimap: { enabled: false }, wordWrap: 'on', fontSize: 14 }}
            />
          )}
        </div>
      </Modal>

      {/* Preview Modal */}
      <Modal
        title={t('prompts.previewTitle')}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        onOk={handlePreview}
        okText={t('prompts.render')}
        width={700}
      >
        <Text type="secondary">{t('prompts.variables')}</Text>
        <Input.TextArea
          rows={3}
          value={previewVars}
          onChange={(e) => setPreviewVars(e.target.value)}
          placeholder={t('promptPlaceholders.preview')}
          style={{ marginBottom: 12 }}
        />
        {previewResult && (
          <Card size="small" title={t('prompts.rendered')}>
            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto', fontSize: 13 }}>
              {previewResult}
            </pre>
          </Card>
        )}
      </Modal>

      {/* Test Modal */}
      <Modal
        title={t('prompts.testTitle')}
        open={testOpen}
        onCancel={() => setTestOpen(false)}
        onOk={handleTest}
        okText={t('prompts.runTest')}
        width={600}
      >
        <Text type="secondary">{t('prompts.variables')}</Text>
        <Input.TextArea
          rows={3}
          value={testVars}
          onChange={(e) => setTestVars(e.target.value)}
          placeholder={t('promptPlaceholders.test')}
          style={{ marginBottom: 12 }}
        />
        {testResult && (
          <Card size="small" title={t('prompts.result')}>
            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto', fontSize: 13 }}>
              {testResult}
            </pre>
          </Card>
        )}
      </Modal>

      {/* Versions Modal */}
      <Modal
        title={t('prompts.history')}
        open={versionsOpen}
        onCancel={() => setVersionsOpen(false)}
        footer={null}
        width={700}
      >
        <Table
          rowKey="version"
          dataSource={versions}
          scroll={{ x: 'max-content' }}
          columns={[
            { title: t('prompts.version'), dataIndex: 'version', width: 80, render: (v: number) => `v${v}` },
            { title: t('prompts.updated'), dataIndex: 'updated_by', width: 120 },
            { title: t('history.time'), dataIndex: 'updated_at', width: 180 },
          ]}
          pagination={false}
          size="small"
        />
      </Modal>
    </div>
  )
}
