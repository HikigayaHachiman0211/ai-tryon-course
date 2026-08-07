import { useState, useEffect } from 'react'
import { Card, Table, Button, Tag, Space, Modal, Input, message, Typography, Select, Descriptions } from 'antd'
import { EditOutlined, HistoryOutlined, PlayCircleOutlined, UndoOutlined, EyeOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import Editor from '@monaco-editor/react'
import { listPrompts, getPrompt, updatePrompt, testPrompt, previewPrompt, getVersions, restoreDefault } from '../api/prompts'

const { Title, Text } = Typography

interface PromptItem {
  id: number
  name: string
  display_name: string
  description: string
  category: string
  prompt_type: string
  version: number
  is_active: boolean
  updated_at: string
  updated_by: string
}

const CATEGORY_OPTIONS = [
  { value: '', label: '全部分类' },
  { value: 'image_analysis', label: '图像分析' },
  { value: 'text_analysis', label: '文本分析' },
  { value: 'recommendation', label: '推荐' },
  { value: 'assistant', label: 'AI 导购/客服' },
  { value: 'tryon', label: '虚拟试穿' },
  { value: 'voice', label: '语音' },
  { value: 'voice_call', label: '电话导购' },
  { value: 'voice_clone', label: '声音克隆' },
]

const TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'system', label: 'System' },
  { value: 'user', label: 'User' },
]

export default function PromptsPage() {
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

  useEffect(() => { fetchData() }, [filterCategory, filterType])

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
      message.success('保存成功')
      setEditOpen(false)
      fetchData()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '保存失败')
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
      setTestResult(`Error: ${err.response?.data?.detail || '测试失败'}`)
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
      setPreviewResult(`Error: ${err.response?.data?.detail || '预览失败'}`)
    }
  }

  const handleRestoreDefault = async (id: number) => {
    try {
      await restoreDefault(id)
      message.success('已恢复默认内容')
      fetchData()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '恢复失败')
    }
  }

  const showVersions = async (id: number) => {
    const res = await getVersions(id)
    setVersions(res.data || [])
    setCurrent({ id } as Record<string, unknown>)
    setVersionsOpen(true)
  }

  const columns: ColumnsType<PromptItem> = [
    { title: '名称', dataIndex: 'name', width: 200, ellipsis: true },
    { title: '显示名', dataIndex: 'display_name', width: 160, ellipsis: true },
    {
      title: '分类',
      dataIndex: 'category',
      width: 100,
      render: (v: string) => {
        const labels: Record<string, string> = {
          image_analysis: '图像分析', text_analysis: '文本分析', recommendation: '推荐',
          assistant: 'AI 导购', tryon: '试穿', voice: '语音',
          voice_call: '电话导购', voice_clone: '声音克隆',
        }
        return labels[v] || v || '-'
      },
    },
    {
      title: '类型',
      dataIndex: 'prompt_type',
      width: 80,
      render: (v: string) => v || '-',
    },
    { title: '版本', dataIndex: 'version', width: 70, render: (v: number) => `v${v}` },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 70,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    { title: '更新者', dataIndex: 'updated_by', width: 100, ellipsis: true },
    { title: '更新时间', dataIndex: 'updated_at', width: 160 },
    {
      title: '操作',
      width: 280,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record.id)}>编辑</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => showVersions(record.id)}>版本</Button>
          <Button size="small" icon={<UndoOutlined />} onClick={() => handleRestoreDefault(record.id)}>恢复默认</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>Prompt 配置中心</Title>

      {/* Filters */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            value={filterCategory}
            onChange={setFilterCategory}
            style={{ width: 150 }}
            options={CATEGORY_OPTIONS}
          />
          <Select
            value={filterType}
            onChange={setFilterType}
            style={{ width: 130 }}
            options={TYPE_OPTIONS}
          />
          <Input.Search
            placeholder="搜索名称/描述"
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
        title={`编辑 Prompt — ${(current as Record<string, unknown>)?.name || ''}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        width={900}
        footer={
          <Space>
            <Button onClick={() => { setPreviewOpen(true); setPreviewResult(''); setPreviewVars('') }}>
              <EyeOutlined /> 预览
            </Button>
            <Button onClick={() => { setTestOpen(true); setTestResult('') }}>
              <PlayCircleOutlined /> 测试
            </Button>
            <Button onClick={() => setEditOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
          </Space>
        }
      >
        {current && (
          <div style={{ marginBottom: 12 }}>
            <Descriptions size="small" column={3}>
              <Descriptions.Item label="分类">{(current as Record<string, unknown>).category as string || '-'}</Descriptions.Item>
              <Descriptions.Item label="类型">{(current as Record<string, unknown>).prompt_type as string || '-'}</Descriptions.Item>
              <Descriptions.Item label="描述">{(current as Record<string, unknown>).description as string || '-'}</Descriptions.Item>
            </Descriptions>
          </div>
        )}
        <div style={{ border: '1px solid #d9d9d9', borderRadius: 8, overflow: 'hidden' }}>
          <Editor
            height="400px"
            language="markdown"
            value={content}
            onChange={(v) => setContent(v || '')}
            options={{ minimap: { enabled: false }, wordWrap: 'on', fontSize: 14 }}
          />
        </div>
      </Modal>

      {/* Preview Modal */}
      <Modal
        title="预览 Prompt"
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        onOk={handlePreview}
        okText="渲染预览"
        width={700}
      >
        <Text type="secondary">变量 JSON（用于替换 {'{variable}'} 占位符）：</Text>
        <Input.TextArea
          rows={3}
          value={previewVars}
          onChange={(e) => setPreviewVars(e.target.value)}
          placeholder='{"color_preference": "黑色", "gender": "male"}'
          style={{ marginBottom: 12 }}
        />
        {previewResult && (
          <Card size="small" title="渲染结果">
            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto', fontSize: 13 }}>
              {previewResult}
            </pre>
          </Card>
        )}
      </Modal>

      {/* Test Modal */}
      <Modal
        title="测试 Prompt"
        open={testOpen}
        onCancel={() => setTestOpen(false)}
        onOk={handleTest}
        okText="运行测试"
        width={600}
      >
        <Text type="secondary">变量 JSON（可选）：</Text>
        <Input.TextArea
          rows={3}
          value={testVars}
          onChange={(e) => setTestVars(e.target.value)}
          placeholder='{"user_gender": "男", "user_height": "175"}'
          style={{ marginBottom: 12 }}
        />
        {testResult && (
          <Card size="small" title="结果">
            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto', fontSize: 13 }}>
              {testResult}
            </pre>
          </Card>
        )}
      </Modal>

      {/* Versions Modal */}
      <Modal
        title="版本历史"
        open={versionsOpen}
        onCancel={() => setVersionsOpen(false)}
        footer={null}
        width={700}
      >
        <Table
          rowKey="version"
          dataSource={versions}
          columns={[
            { title: '版本', dataIndex: 'version', width: 80, render: (v: number) => `v${v}` },
            { title: '修改者', dataIndex: 'updated_by', width: 120 },
            { title: '时间', dataIndex: 'updated_at', width: 180 },
          ]}
          pagination={false}
          size="small"
        />
      </Modal>
    </div>
  )
}
