import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Button, Tag, Space, Modal, Form, Input, Select, Switch,
  InputNumber, message, Typography, Tabs, Descriptions, Alert, Tooltip, Popconfirm,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined,
  ThunderboltOutlined, ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getProviders, createProvider, updateProvider, deleteProvider, testProvider,
  getFeatures, updateFeature,
  getTryonAIConfig, updateTryonAIConfig, testTryonAIConfig,
  type AIAPIProvider, type AIFeatureConfig,
  type TryonAIConfig, type TryonAIConfigTestResult,
} from '../api/aiConfig'

const { Title, Text } = Typography
const { TextArea } = Input

const CATEGORY_OPTIONS = [
  { value: 'llm', label: 'LLM 文本' },
  { value: 'vision', label: '视觉分析' },
  { value: 'multi', label: '多模态 (LLM+Vision)' },
  { value: 'asr', label: '语音识别 ASR' },
  { value: 'tts', label: '语音合成 TTS' },
  { value: 'voice_clone', label: '声音克隆' },
  { value: 'tryon', label: '虚拟试穿' },
  { value: 'custom', label: '自定义' },
]

const AUTH_TYPE_OPTIONS = [
  { value: 'api_key_header', label: 'API Key Header' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'query_key', label: 'Query ?key=' },
  { value: 'none', label: '无需认证' },
  { value: 'custom', label: '自定义' },
]

const FEATURE_LABELS: Record<string, string> = {
  recommendation: '智能推荐',
  vision_analysis: '图像分析',
  assistant_chat: 'AI 导购',
  tryon: '虚拟试穿',
  asr: '语音识别',
  tts: '语音合成',
  voice_clone: '声音克隆',
}

// ---------------------------------------------------------------------------
// Tab 1: Overview
// ---------------------------------------------------------------------------
function OverviewTab() {
  const [providers, setProviders] = useState<AIAPIProvider[]>([])
  const [features, setFeatures] = useState<AIFeatureConfig[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [pRes, fRes] = await Promise.all([getProviders(), getFeatures()])
      setProviders(pRes.data)
      setFeatures(fRes.data)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const getProviderName = (key: string) =>
    providers.find(p => p.provider_key === key)?.display_name || key

  const missingKeys = providers.filter(p => p.enabled && !p.has_api_key)

  return (
    <div>
      {missingKeys.length > 0 && (
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          message="以下已启用的 Provider 缺少 API Key"
          description={missingKeys.map(p => p.display_name).join(', ')}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card title="功能路由总览" loading={loading}>
        <Table
          rowKey="feature_key"
          dataSource={features}
          pagination={false}
          size="small"
          columns={[
            { title: '功能', dataIndex: 'feature_key', render: (k: string) => FEATURE_LABELS[k] || k },
            {
              title: '状态', dataIndex: 'enabled', width: 80,
              render: (v: boolean) => v
                ? <Tag color="green" icon={<CheckCircleOutlined />}>启用</Tag>
                : <Tag color="default" icon={<CloseCircleOutlined />}>停用</Tag>,
            },
            { title: '默认 Provider', dataIndex: 'default_provider', render: (k: string) => getProviderName(k) },
            { title: '默认模型', dataIndex: 'default_model' },
            {
              title: 'Fallback 顺序', dataIndex: 'fallback_order',
              render: (arr: string[] | null) => arr?.map(getProviderName).join(' → ') || '-',
            },
          ]}
        />
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 2: Provider Management
// ---------------------------------------------------------------------------
function ProvidersTab() {
  const [data, setData] = useState<AIAPIProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<AIAPIProvider | null>(null)
  const [form] = Form.useForm()
  const [testing, setTesting] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getProviders()
      setData(res.data)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({
      enabled: true, is_default: false, auth_type: 'api_key_header',
      timeout_seconds: 30, retry_count: 1,
    })
    setEditOpen(true)
  }

  const openEdit = (record: AIAPIProvider) => {
    setEditing(record)
    form.setFieldsValue({
      ...record,
      api_key: '',  // don't prefill
      model_options: record.model_options?.join(', ') || '',
    })
    setEditOpen(true)
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    const payload = {
      ...values,
      model_options: values.model_options
        ? String(values.model_options).split(',').map((s: string) => s.trim()).filter(Boolean)
        : undefined,
    }

    try {
      if (editing) {
        // Don't send api_key if empty (preserve existing)
        if (!payload.api_key) delete payload.api_key
        await updateProvider(editing.id, payload)
        message.success('更新成功')
      } else {
        await createProvider(payload)
        message.success('创建成功')
      }
      setEditOpen(false)
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '操作失败')
    }
  }

  const handleTest = async (id: number) => {
    setTesting(id)
    try {
      const res = await testProvider(id)
      if (res.data.success) {
        message.success(`测试通过 (${res.data.latency_ms}ms)`)
      } else {
        message.warning(`测试失败: ${res.data.message}`)
      }
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '测试请求失败')
    }
    setTesting(null)
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteProvider(id)
      message.success('已处理')
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '删除失败')
    }
  }

  const columns: ColumnsType<AIAPIProvider> = [
    { title: '名称', dataIndex: 'display_name', width: 160 },
    { title: 'Key', dataIndex: 'provider_key', width: 120 },
    {
      title: '分类', dataIndex: 'category', width: 100,
      render: (v: string) => CATEGORY_OPTIONS.find(c => c.value === v)?.label || v,
    },
    { title: 'Base URL', dataIndex: 'base_url', ellipsis: true },
    { title: '默认模型', dataIndex: 'default_model', width: 160 },
    {
      title: 'API Key', dataIndex: 'api_key_masked', width: 120,
      render: (v: string, r) => r.has_api_key ? <Text code>{v}</Text> : <Text type="secondary">未配置</Text>,
    },
    {
      title: '启用', dataIndex: 'enabled', width: 70,
      render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '默认', dataIndex: 'is_default', width: 60,
      render: (v: boolean) => v ? <Tag color="blue">默认</Tag> : '-',
    },
    {
      title: '最近测试', width: 100,
      render: (_, r) => r.last_test_status
        ? r.last_test_status === 'success'
          ? <Tag color="green">通过</Tag>
          : <Tooltip title={r.last_test_message}><Tag color="red">失败</Tag></Tooltip>
        : '-',
    },
    {
      title: '操作', width: 200, fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            loading={testing === record.id}
            onClick={() => handleTest(record.id)}
          >
            测试
          </Button>
          <Popconfirm title="确定禁用/删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Title level={4} style={{ margin: 0 }}>Provider 管理</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增 Provider</Button>
        </Space>
      </div>

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

      <Modal
        title={editing ? `编辑 — ${editing.display_name}` : '新增 Provider'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        width={720}
        okText="保存"
      >
        <Form form={form} layout="vertical" style={{ maxHeight: '65vh', overflow: 'auto', paddingRight: 8 }}>
          <Form.Item name="provider_key" label="Provider Key" rules={[{ required: !editing }]}>
            <Input disabled={!!editing} placeholder="例如 mimo, gemini, deepseek" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}>
            <Input placeholder="例如 Xiaomi MiMo" />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true }]}>
            <Select options={CATEGORY_OPTIONS} />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_default" label="默认" valuePropName="checked">
              <Switch />
            </Form.Item>
          </div>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="https://api.example.com/v1" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key" extra={editing ? '留空则不修改现有 Key' : ''}>
            <Input.Password placeholder={editing ? '留空则不修改现有 Key' : '输入 API Key'} />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="auth_type" label="认证方式" style={{ flex: 1 }}>
              <Select options={AUTH_TYPE_OPTIONS} />
            </Form.Item>
            <Form.Item name="auth_header_name" label="Header 名称" style={{ flex: 1 }}>
              <Input placeholder="api-key" />
            </Form.Item>
          </div>
          <Form.Item name="default_model" label="默认模型">
            <Input placeholder="mimo-v2.5" />
          </Form.Item>
          <Form.Item name="model_options" label="可选模型（逗号分隔）">
            <Input placeholder="mimo-v2.5, mimo-v2.5-pro" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="timeout_seconds" label="超时（秒）" style={{ flex: 1 }}>
              <InputNumber min={5} max={300} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="retry_count" label="重试次数" style={{ flex: 1 }}>
              <InputNumber min={0} max={10} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="cost_note" label="费用说明">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 3: Feature Routing
// ---------------------------------------------------------------------------
function FeaturesTab() {
  const [data, setData] = useState<AIFeatureConfig[]>([])
  const [providers, setProviders] = useState<AIAPIProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<AIFeatureConfig | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [fRes, pRes] = await Promise.all([getFeatures(), getProviders()])
      setData(fRes.data)
      setProviders(pRes.data)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const getProviderName = (key: string) =>
    providers.find(p => p.provider_key === key)?.display_name || key

  const providerOptions = providers.map(p => ({ value: p.provider_key, label: p.display_name }))

  const openEdit = (record: AIFeatureConfig) => {
    setEditing(record)
    form.setFieldsValue({
      enabled: record.enabled,
      default_provider: record.default_provider,
      default_model: record.default_model,
      fallback_order: record.fallback_order?.join(', ') || '',
      config_json: record.config ? JSON.stringify(record.config, null, 2) : '',
    })
    setEditOpen(true)
  }

  const handleSave = async () => {
    if (!editing) return
    const values = await form.validateFields()

    // Parse config JSON if provided
    let config: Record<string, unknown> | undefined
    const configStr = String(values.config_json || '').trim()
    if (configStr) {
      try {
        config = JSON.parse(configStr)
        if (typeof config !== 'object' || config === null || Array.isArray(config)) {
          message.error('Config 必须是 JSON 对象，例如 {"key": "value"}')
          return
        }
      } catch {
        message.error('Config JSON 格式无效，请检查语法')
        return
      }
    }

    const payload = {
      enabled: values.enabled,
      default_provider: values.default_provider,
      default_model: values.default_model,
      fallback_order: values.fallback_order
        ? String(values.fallback_order).split(',').map((s: string) => s.trim()).filter(Boolean)
        : undefined,
      config: config ?? undefined,
    }
    try {
      await updateFeature(editing.feature_key, payload)
      message.success('保存成功')
      setEditOpen(false)
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '保存失败')
    }
  }

  const columns: ColumnsType<AIFeatureConfig> = [
    {
      title: '功能', dataIndex: 'feature_key',
      render: (k: string) => FEATURE_LABELS[k] || k,
    },
    {
      title: '状态', dataIndex: 'enabled', width: 80,
      render: (v: boolean) => v
        ? <Tag color="green" icon={<CheckCircleOutlined />}>启用</Tag>
        : <Tag color="default" icon={<CloseCircleOutlined />}>停用</Tag>,
    },
    {
      title: '默认 Provider', dataIndex: 'default_provider',
      render: (k: string) => getProviderName(k),
    },
    { title: '默认模型', dataIndex: 'default_model' },
    {
      title: 'Fallback 顺序', dataIndex: 'fallback_order',
      render: (arr: string[] | null) => arr?.map(getProviderName).join(' → ') || '-',
    },
    {
      title: '操作', width: 100,
      render: (_, record) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>功能路由配置</Title>
      <Card>
        <Table
          rowKey="feature_key"
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={false}
          size="middle"
        />
      </Card>

      <Modal
        title={`编辑功能 — ${editing ? FEATURE_LABELS[editing.feature_key] || editing.feature_key : ''}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        width={520}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="default_provider" label="默认 Provider">
            <Select options={providerOptions} />
          </Form.Item>
          <Form.Item name="default_model" label="默认模型">
            <Input />
          </Form.Item>
          <Form.Item name="fallback_order" label="Fallback 顺序（逗号分隔 Provider Key）">
            <Input placeholder="mimo, gemini, deepseek, rule" />
          </Form.Item>
          <Form.Item
            name="config_json"
            label="Config JSON（可选）"
            extra='例如 {"allow_auto_fill": true, "language": "zh"}'
          >
            <Input.TextArea
              rows={4}
              placeholder='{"key": "value"}'
              style={{ fontFamily: 'monospace', fontSize: 13 }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 4: Test & Logs
// ---------------------------------------------------------------------------
function TestTab() {
  const [providers, setProviders] = useState<AIAPIProvider[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<string>('')
  const [logs, setLogs] = useState<AIAPIProvider[]>([])

  useEffect(() => {
    getProviders().then(res => {
      setProviders(res.data)
      setLogs(res.data.filter(p => p.last_test_at))
    })
  }, [])

  const handleTest = async () => {
    if (!selected) { message.warning('请选择 Provider'); return }
    setTesting(true)
    setResult('')
    try {
      const res = await testProvider(selected)
      setResult(JSON.stringify(res.data, null, 2))
      // Refresh logs
      const all = await getProviders()
      setLogs(all.data.filter(p => p.last_test_at))
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setResult(`Error: ${err.response?.data?.detail || '测试失败'}`)
    }
    setTesting(false)
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>测试与日志</Title>

      <Card title="连接测试" style={{ marginBottom: 16 }}>
        <Space>
          <Select
            style={{ width: 280 }}
            placeholder="选择 Provider"
            value={selected}
            onChange={setSelected}
            options={providers.map(p => ({ value: p.id, label: `${p.display_name} (${p.provider_key})` }))}
          />
          <Button type="primary" icon={<ApiOutlined />} loading={testing} onClick={handleTest}>
            测试连接
          </Button>
        </Space>
        {result && (
          <Card size="small" style={{ marginTop: 12 }}>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, maxHeight: 300, overflow: 'auto', margin: 0 }}>
              {result}
            </pre>
          </Card>
        )}
      </Card>

      <Card title="最近测试记录">
        <Table
          rowKey="id"
          dataSource={logs.sort((a, b) => (b.last_test_at || '').localeCompare(a.last_test_at || ''))}
          pagination={false}
          size="small"
          columns={[
            { title: 'Provider', dataIndex: 'display_name', width: 160 },
            {
              title: '结果', dataIndex: 'last_test_status', width: 80,
              render: (v: string | null) => v === 'success'
                ? <Tag color="green">通过</Tag>
                : <Tag color="red">失败</Tag>,
            },
            {
              title: '信息', dataIndex: 'last_test_message', ellipsis: true,
              render: (v: string | null) => v || '-',
            },
            { title: '时间', dataIndex: 'last_test_at', width: 180 },
          ]}
        />
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 5: Tryon API Management
// ---------------------------------------------------------------------------
function TryonTab() {
  const [config, setConfig] = useState<TryonAIConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [form] = Form.useForm()
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getTryonAIConfig()
      setConfig(res.data)
      form.setFieldsValue({
        enabled: res.data.enabled,
        flash_model: res.data.flash_model,
        pro_model: res.data.pro_model,
        timeout_seconds: res.data.timeout_seconds,
        retry_count: res.data.retry_count,
        api_key: '', // never prefill
      })
    } catch { /* ignore */ }
    setLoading(false)
  }, [form])

  useEffect(() => { load() }, [load])

  const handleSave = async (clearKey = false) => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      const payload: Record<string, unknown> = {
        enabled: values.enabled,
        flash_model: values.flash_model?.trim(),
        pro_model: values.pro_model?.trim(),
        timeout_seconds: values.timeout_seconds,
        retry_count: values.retry_count,
      }
      if (clearKey) {
        payload.clear_api_key = true
      } else if (values.api_key && values.api_key.trim()) {
        payload.api_key = values.api_key.trim()
      }
      await updateTryonAIConfig(payload)
      message.success('试衣站配置已保存')
      form.setFieldValue('api_key', '')
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '保存失败')
    }
    setSaving(false)
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await testTryonAIConfig()
      const data: TryonAIConfigTestResult = res.data
      if (data.success) {
        let msg = `测试通过 (${data.latency_ms}ms)`
        const checks: string[] = []
        if (data.model_check.flash_found) checks.push('Flash 模型可用')
        if (data.model_check.pro_found) checks.push('Pro 模型可用')
        if (checks.length > 0) msg += ` — ${checks.join(', ')}`
        message.success(msg)
      } else {
        message.warning(`测试失败: ${data.message}`)
      }
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '测试请求失败')
    }
    setTesting(false)
  }

  const handleClearKey = async () => {
    setClearConfirmOpen(false)
    await handleSave(true)
  }

  if (loading && !config) {
    return <Card loading />
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>试衣站 API 配置</Title>

      <Alert
        type="info"
        showIcon
        message="统一管理说明"
        description="试衣站的 Gemini API Key 和模型配置由后台统一管理。Key 加密存储在后台数据库，不会发送到试衣站浏览器端。修改后无需重启试衣站服务，最多 15 秒内生效。"
        style={{ marginBottom: 16 }}
      />

      <Card title="Provider 状态" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="Provider">Google Gemini / AI Studio</Descriptions.Item>
          <Descriptions.Item label="认证方式">Query ?key=</Descriptions.Item>
          <Descriptions.Item label="Provider 状态">
            {config?.provider_enabled
              ? <Tag color="green">已启用</Tag>
              : <Tag color="red">已停用，请到 Provider 管理中启用</Tag>
            }
          </Descriptions.Item>
          <Descriptions.Item label="API Key 状态">
            {config?.has_api_key
              ? config.key_status === 'ok'
                ? <Tag color="green">已配置</Tag>
                : <Tag color="red">解密失败</Tag>
              : <Tag color="default">未配置</Tag>
            }
          </Descriptions.Item>
          <Descriptions.Item label="最近测试">
            {config?.last_test_status
              ? config.last_test_status === 'success'
                ? <Tag color="green">通过</Tag>
                : <Tag color="red">失败</Tag>
              : <Tag>未测试</Tag>
            }
            {config?.last_test_at && (
              <Text type="secondary" style={{ marginLeft: 8 }}>
                {new Date(config.last_test_at).toLocaleString()}
              </Text>
            )}
          </Descriptions.Item>
          {config?.last_test_message && (
            <Descriptions.Item label="测试信息" span={2}>
              {config.last_test_message}
            </Descriptions.Item>
          )}
          {config?.updated_at && (
            <Descriptions.Item label="更新时间">
              {new Date(config.updated_at).toLocaleString()}
            </Descriptions.Item>
          )}
          {config?.updated_by && (
            <Descriptions.Item label="更新人">{config.updated_by}</Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card title="配置编辑">
        {config && !config.provider_enabled && (
          <Alert
            type="warning"
            showIcon
            message="Gemini Provider 已停用"
            description="试衣开关只控制试衣功能，不会修改共享 Provider，避免影响主站推荐和视觉分析。请先在 Provider 管理中启用 Gemini。"
            style={{ marginBottom: 16 }}
          />
        )}
        <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
          <Form.Item name="enabled" label="启用试衣功能" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item
            name="api_key"
            label="API Key"
            extra="留空则保留原有 Key。Key 加密存储，不会回填或发送给浏览器。"
          >
            <Input.Password placeholder="输入新的 Gemini API Key" />
          </Form.Item>

          <div style={{ marginBottom: 16 }}>
            <Popconfirm
              title="确定清除 API Key？"
              description="清除后试衣功能将无法使用，直到重新配置 Key。"
              open={clearConfirmOpen}
              onConfirm={handleClearKey}
              onCancel={() => setClearConfirmOpen(false)}
              okText="确认清除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button
                danger
                disabled={!config?.has_api_key}
                onClick={() => setClearConfirmOpen(true)}
              >
                清除 API Key
              </Button>
            </Popconfirm>
          </div>

          <Form.Item
            name="flash_model"
            label="Flash 模型 ID"
            rules={[{ required: true, message: '请输入 Flash 模型 ID' }]}
          >
            <Input placeholder="gemini-3.1-flash-image-preview" />
          </Form.Item>

          <Form.Item
            name="pro_model"
            label="Pro 模型 ID"
            rules={[{ required: true, message: '请输入 Pro 模型 ID' }]}
          >
            <Input placeholder="gemini-3-pro-image-preview" />
          </Form.Item>

          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="timeout_seconds" label="超时（秒）" style={{ flex: 1 }}>
              <InputNumber min={10} max={300} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="retry_count" label="重试次数" style={{ flex: 1 }}>
              <InputNumber min={0} max={5} style={{ width: '100%' }} />
            </Form.Item>
          </div>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={saving}
                onClick={() => handleSave(false)}
              >
                保存配置
              </Button>
              <Button
                icon={<ApiOutlined />}
                loading={testing}
                onClick={handleTest}
                disabled={!config?.has_api_key}
              >
                测试连接
              </Button>
              <Button icon={<ReloadOutlined />} onClick={load}>
                刷新
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
export default function AIModelSettingsPage() {
  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        <ApiOutlined style={{ marginRight: 8 }} />
        AI 模型/API 管理中心
      </Title>

      <Tabs
        defaultActiveKey="overview"
        items={[
          { key: 'overview', label: '总览', children: <OverviewTab /> },
          { key: 'tryon', label: '试衣站 API', children: <TryonTab /> },
          { key: 'providers', label: 'Provider 管理', children: <ProvidersTab /> },
          { key: 'features', label: '功能路由', children: <FeaturesTab /> },
          { key: 'test', label: '测试与日志', children: <TestTab /> },
        ]}
      />
    </div>
  )
}
