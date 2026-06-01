import { useState, useEffect } from 'react'
import { Card, Table, Button, Tag, Space, Modal, Input, message, Typography, Descriptions } from 'antd'
import { EditOutlined, HistoryOutlined, PlayCircleOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import Editor from '@monaco-editor/react'
import { listPrompts, getPrompt, updatePrompt, testPrompt, getVersions, diffVersions } from '../api/prompts'

const { Title, Text } = Typography

interface PromptItem {
  id: number
  name: string
  description: string
  version: number
  is_active: boolean
  updated_at: string
}

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
  const [diffText, setDiffText] = useState('')

  const fetchData = () => {
    setLoading(true)
    listPrompts()
      .then((res) => setData(res.data.items || res.data || []))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData() }, [])

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
      await updatePrompt(current.id as number, {
        content,
        description: current.description,
      })
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
      setTestResult(res.data.result || JSON.stringify(res.data, null, 2))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setTestResult(`Error: ${err.response?.data?.detail || '测试失败'}`)
    }
  }

  const showVersions = async (id: number) => {
    const res = await getVersions(id)
    setVersions(res.data.versions || res.data || [])
    setCurrent({ id } as Record<string, unknown>)
    setVersionsOpen(true)
  }

  const showDiff = async (v1: number, v2: number) => {
    if (!current) return
    const res = await diffVersions(current.id as number, v1, v2)
    setDiffText(res.data.diff || '')
  }

  const columns: ColumnsType<PromptItem> = [
    { title: '名称', dataIndex: 'name', width: 200 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '版本', dataIndex: 'version', width: 80, render: (v: number) => `v${v}` },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 180 },
    {
      title: '操作',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record.id)}>编辑</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => showVersions(record.id)}>版本</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>Prompt 配置中心</Title>
      <Card>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={false}
          size="middle"
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
            <Button onClick={() => { setTestOpen(true); setTestResult('') }}>
              <PlayCircleOutlined /> 测试
            </Button>
            <Button onClick={() => setEditOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>保存</Button>
          </Space>
        }
      >
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
        onCancel={() => { setVersionsOpen(false); setDiffText('') }}
        footer={null}
        width={700}
      >
        <Table
          rowKey="version"
          dataSource={versions}
          columns={[
            { title: '版本', dataIndex: 'version', width: 80, render: (v: number) => `v${v}` },
            { title: '修改者', dataIndex: 'changed_by', width: 120 },
            { title: '时间', dataIndex: 'created_at', width: 180 },
            {
              title: '操作',
              render: (_, record, index) => (
                index < versions.length - 1 ? (
                  <Button
                    size="small"
                    onClick={() => showDiff(
                      (versions[index + 1] as Record<string, unknown>).version as number,
                      record.version as number,
                    )}
                  >
                    对比
                  </Button>
                ) : null
              ),
            },
          ]}
          pagination={false}
          size="small"
        />
        {diffText && (
          <Card size="small" style={{ marginTop: 12 }}>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 300, overflow: 'auto' }}>
              {diffText}
            </pre>
          </Card>
        )}
      </Modal>
    </div>
  )
}
