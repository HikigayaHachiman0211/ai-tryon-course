import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Button, Tag, Space, Modal, Form, Input, Select, Switch, Grid,
  InputNumber, message, Typography, Tabs, Descriptions, Alert, Tooltip, Popconfirm, Divider, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined,
  ThunderboltOutlined, ReloadOutlined, SyncOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getProviders, createProvider, updateProvider, deleteProvider, testProvider, syncProviderModels,
  getFeatures, updateFeature,
  getTryonAIConfig, updateTryonAIConfig, testTryonAIConfig,
  type AIAPIProvider, type AIFeatureConfig,
  type TotokensAPIProfile, type TotokensAPIProfileUpdate, type TotokensAPIScope,
  type TryonAIConfig, type TryonAIConfigTestResult,
} from '../api/aiConfig'
import { useTranslation } from 'react-i18next'
import VideoSettingsTab from './VideoSettingsTab'
import RealtimeSettingsTab from './RealtimeSettingsTab'

const { Title, Text } = Typography
const { TextArea } = Input

const CATEGORY_OPTIONS = [
  { value: 'llm', key: 'aiLabels.llm' }, { value: 'vision', key: 'aiLabels.vision' }, { value: 'multi', key: 'aiLabels.multi' },
  { value: 'asr', key: 'aiLabels.asr' }, { value: 'tts', key: 'aiLabels.tts' }, { value: 'voice_clone', key: 'aiLabels.voiceClone' },
  { value: 'tryon', key: 'aiLabels.tryon' }, { value: 'custom', key: 'aiLabels.custom' },
  { value: 'video', key: 'videoSettings.title' },
  { value: 'realtime', key: 'realtimeSettings.categoryLabel' },
]

const AUTH_TYPE_OPTIONS = [
  { value: 'api_key_header', label: 'API Key Header' }, { value: 'bearer', label: 'Bearer Token' },
  { value: 'query_key', label: 'Query ?key=' }, { value: 'none', key: 'aiLabels.authNone' }, { value: 'custom', key: 'aiLabels.authCustom' },
]

const FEATURE_LABEL_KEYS: Record<string, string> = {
  recommendation: 'aiLabels.recommendation', vision_analysis: 'aiLabels.visionAnalysis', assistant_chat: 'aiLabels.assistant',
  tryon: 'aiLabels.tryon', asr: 'aiLabels.asr', tts: 'aiLabels.tts', voice_clone: 'aiLabels.voiceClone',
  tryon_video: 'videoSettings.title',
  tryon_realtime: 'realtimeSettings.title',
  tryon_realtime_xmax: 'realtimeSettings.xmaxTitle',
  tryon_realtime_reactor: 'realtimeSettings.reactorTitle',
}

// ---------------------------------------------------------------------------
// Tab 1: Overview
// ---------------------------------------------------------------------------
function OverviewTab() {
  const { t } = useTranslation('common')
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
          message={t('aiExtra.missingKey')}
          description={missingKeys.map(p => p.display_name).join(', ')}
          style={{ marginBottom: 16 }}
        />
      )}

      <Card title={t('ai.overview')} loading={loading}>
        <Table
          rowKey="feature_key"
          dataSource={features}
          pagination={false}
          size="small"
          scroll={{ x: 'max-content' }}
          columns={[
            { title: t('ai.feature'), dataIndex: 'feature_key', render: (k: string) => FEATURE_LABEL_KEYS[k] ? t(FEATURE_LABEL_KEYS[k]) : k },
            {
              title: t('tryon.status'), dataIndex: 'enabled', width: 80,
              render: (v: boolean) => v
                ? <Tag color="green" icon={<CheckCircleOutlined />}>{t('status.enabled')}</Tag>
                : <Tag color="default" icon={<CloseCircleOutlined />}>{t('status.disabled')}</Tag>,
            },
            { title: t('ai.provider'), dataIndex: 'default_provider', render: (k: string) => getProviderName(k) },
            { title: t('ai.model'), dataIndex: 'default_model' },
            {
              title: t('ai.fallback'), dataIndex: 'fallback_order',
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
  const { t } = useTranslation('common')
  const screens = Grid.useBreakpoint()
  const isMobile = screens.md === false
  const [data, setData] = useState<AIAPIProvider[]>([])
  const [loading, setLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<AIAPIProvider | null>(null)
  const [form] = Form.useForm()
  const [testing, setTesting] = useState<number | null>(null)
  const [syncing, setSyncing] = useState<number | null>(null)

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
        message.success(t('actions.save'))
      } else {
        await createProvider(payload)
        message.success(t('actions.create'))
      }
      setEditOpen(false)
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.unknown'))
    }
  }

  const handleTest = async (id: number) => {
    setTesting(id)
    try {
      const res = await testProvider(id)
      if (res.data.success) {
        message.success(`${t('status.passed')} (${res.data.latency_ms}ms)`)
      } else {
        message.warning(`${t('status.failed')}: ${res.data.message}`)
      }
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.network'))
    }
    setTesting(null)
  }

  const handleSyncModels = async (id: number) => {
    setSyncing(id)
    try {
      const res = await syncProviderModels(id)
      if (res.data.source === 'builtin') {
        message.info(t('aiExtra.syncedBuiltinModels', { count: res.data.synced_count }))
      } else {
        message.success(t('aiExtra.syncedModels', { count: res.data.synced_count }))
      }
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string; message?: string } } }
      message.error(err.response?.data?.detail || err.response?.data?.message || t('errors.network'))
    }
    setSyncing(null)
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteProvider(id)
      message.success(t('actions.confirm'))
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.unknown'))
    }
  }

  const columns: ColumnsType<AIAPIProvider> = [
    { title: t('ai.displayName'), dataIndex: 'display_name', width: 160 },
    { title: 'Key', dataIndex: 'provider_key', width: 120 },
    {
      title: t('ai.category'), dataIndex: 'category', width: 100,
      render: (v: string) => { const item = CATEGORY_OPTIONS.find(c => c.value === v); return item ? t(item.key) : v },
    },
    { title: 'Base URL', dataIndex: 'base_url', ellipsis: true },
    { title: t('ai.model'), dataIndex: 'default_model', width: 160 },
    {
      title: 'API Key', dataIndex: 'api_key_masked', width: 120,
      render: (v: string, r) => r.has_api_key ? <Text code>{v}</Text> : <Text type="secondary">{t('ai.configured')}</Text>,
    },
    {
      title: t('ai.enabled'), dataIndex: 'enabled', width: 70,
      render: (v: boolean) => v ? <Tag color="green">{t('status.enabled')}</Tag> : <Tag>{t('status.disabled')}</Tag>,
    },
    {
      title: t('ai.default'), dataIndex: 'is_default', width: 60,
      render: (v: boolean) => v ? <Tag color="blue">{t('status.default')}</Tag> : '-',
    },
    {
      title: t('ai.recentTest'), width: 100,
      render: (_, r) => r.last_test_status
        ? r.last_test_status === 'success'
          ? <Tag color="green">{t('status.passed')}</Tag>
          : <Tooltip title={r.last_test_message}><Tag color="red">{t('status.failed')}</Tag></Tooltip>
        : '-',
    },
    {
      title: t('ai.operation'), width: 255, fixed: isMobile ? undefined : 'right',
      render: (_, record) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>{t('actions.edit')}</Button>
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            loading={testing === record.id}
            onClick={() => handleTest(record.id)}
          >
            {t('actions.test')}
          </Button>
          {['opencode_go', 'gemini', 'deepseek', 'mimo', 'totokens'].includes(record.provider_key) && (
            <Tooltip title={t('actions.syncModels')}>
              <Button
                size="small"
                icon={<SyncOutlined spin={syncing === record.id} />}
                loading={syncing === record.id}
                onClick={() => handleSyncModels(record.id)}
              />
            </Tooltip>
          )}
          <Popconfirm title={t('ai.deleteConfirm')} onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <Title level={4} style={{ margin: 0 }}>{t('ai.providers')}</Title>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={load}>{t('actions.refresh')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>{t('ai.create')}</Button>
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
        title={editing ? `${t('actions.edit')} — ${editing.display_name}` : t('ai.newTitle')}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        width={720}
        okText={t('actions.save')}
      >
        <Form form={form} layout="vertical" style={{ maxHeight: '65vh', overflow: 'auto', paddingRight: 8 }}>
          <Form.Item name="provider_key" label="Provider Key" rules={[{ required: !editing }]}>
            <Input disabled={!!editing} placeholder={t('aiForm.providerKeyPlaceholder')} />
          </Form.Item>
          <Form.Item name="display_name" label={t('ai.displayName')} rules={[{ required: true }]}>
            <Input placeholder={t('aiForm.displayNamePlaceholder')} />
          </Form.Item>
          <Form.Item name="category" label={t('ai.category')} rules={[{ required: true }]}>
            <Select options={CATEGORY_OPTIONS.map((item) => ({ value: item.value, label: t(item.key) }))} />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="enabled" label={t('ai.enabled')} valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_default" label={t('ai.default')} valuePropName="checked">
              <Switch />
            </Form.Item>
          </div>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="https://api.example.com/v1" />
          </Form.Item>
          <Form.Item name="api_key" label={t('ai.key')} extra={editing ? t('ai.optional') : ''}>
            <Input.Password placeholder={editing ? t('ai.optional') : t('ai.key')} />
          </Form.Item>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            <Form.Item name="auth_type" label={t('ai.authType')} style={{ flex: '1 1 200px' }}>
              <Select options={AUTH_TYPE_OPTIONS.map((item) => ({ value: item.value, label: item.key ? t(item.key) : item.label }))} />
            </Form.Item>
            <Form.Item name="auth_header_name" label={t('ai.header')} style={{ flex: '1 1 200px' }}>
              <Input placeholder="api-key" />
            </Form.Item>
          </div>
          <Form.Item name="default_model" label={t('ai.model')}>
            <Input placeholder="mimo-v2.6-flash" />
          </Form.Item>
          <Form.Item name="model_options" label={t('ai.options')}>
            <Input placeholder="mimo-v2.6-flash, mimo-v2.6-pro" />
          </Form.Item>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            <Form.Item name="timeout_seconds" label={t('ai.timeout')} style={{ flex: '1 1 160px' }}>
              <InputNumber min={5} max={300} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="retry_count" label={t('ai.retry')} style={{ flex: '1 1 160px' }}>
              <InputNumber min={0} max={10} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="cost_note" label={t('ai.cost')}>
            <Input placeholder={t('ai.optional')} />
          </Form.Item>
          <Form.Item name="notes" label={t('ai.notes')}>
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
  const { t } = useTranslation('common')
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
          message.error('Config must be a JSON object, for example {"key": "value"}')
          return
        }
      } catch {
        message.error('Invalid Config JSON')
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
      message.success(t('actions.save'))
      setEditOpen(false)
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.unknown'))
    }
  }

  const columns: ColumnsType<AIFeatureConfig> = [
    {
      title: t('ai.feature'), dataIndex: 'feature_key',
      render: (k: string) => FEATURE_LABEL_KEYS[k] ? t(FEATURE_LABEL_KEYS[k]) : k,
    },
    {
      title: t('ai.enabled'), dataIndex: 'enabled', width: 80,
      render: (v: boolean) => v
        ? <Tag color="green" icon={<CheckCircleOutlined />}>{t('status.enabled')}</Tag>
        : <Tag color="default" icon={<CloseCircleOutlined />}>{t('status.disabled')}</Tag>,
    },
    {
      title: t('ai.provider'), dataIndex: 'default_provider',
      render: (k: string) => getProviderName(k),
    },
    { title: t('ai.model'), dataIndex: 'default_model' },
    {
      title: t('ai.fallback'), dataIndex: 'fallback_order',
      render: (arr: string[] | null) => arr?.map(getProviderName).join(' → ') || '-',
    },
    {
      title: t('ai.operation'), width: 100,
      render: (_, record) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>{t('actions.edit')}</Button>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('ai.features')}</Title>
      <Card>
        <Table
          rowKey="feature_key"
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={false}
          size="middle"
          scroll={{ x: 'max-content' }}
        />
      </Card>

      <Modal
        title={`${t('actions.edit')} — ${editing && FEATURE_LABEL_KEYS[editing.feature_key] ? t(FEATURE_LABEL_KEYS[editing.feature_key]) : editing?.feature_key || ''}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleSave}
        width={520}
        okText={t('actions.save')}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="enabled" label={t('ai.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="default_provider" label={t('ai.provider')}>
            <Select options={providerOptions} />
          </Form.Item>
          <Form.Item name="default_model" label={t('ai.model')}>
            <Input />
          </Form.Item>
          <Form.Item name="fallback_order" label={t('ai.fallback')}>
            <Input placeholder="mimo, gemini, deepseek, opencode_go, rule" />
          </Form.Item>
          <Form.Item
            name="config_json"
            label="Config JSON (optional)"
            extra={t('aiForm.configExtra')}
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
  const { t } = useTranslation('common')
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
    if (!selected) { message.warning(t('aiExtra.selectProvider')); return }
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
      setResult(`Error: ${err.response?.data?.detail || t('status.failed')}`)
    }
    setTesting(false)
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('ai.tests')}</Title>

      <Card title={t('aiExtra.connection')} style={{ marginBottom: 16 }}>
        <Space wrap style={{ width: '100%' }}>
          <Select
            className="admin-toolbar-input"
            style={{ width: 280 }}
            placeholder={t('aiExtra.selectProvider')}
            value={selected}
            onChange={setSelected}
            options={providers.map(p => ({ value: p.id, label: `${p.display_name} (${p.provider_key})` }))}
          />
          <Button type="primary" icon={<ApiOutlined />} loading={testing} onClick={handleTest}>
            {t('ai.testConnection')}
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

      <Card title={t('ai.recentTests')}>
        <Table
          rowKey="id"
          dataSource={logs.sort((a, b) => (b.last_test_at || '').localeCompare(a.last_test_at || ''))}
          pagination={false}
          size="small"
          scroll={{ x: 'max-content' }}
          columns={[
            { title: t('ai.provider'), dataIndex: 'display_name', width: 160 },
            {
              title: t('prompts.result'), dataIndex: 'last_test_status', width: 80,
              render: (v: string | null) => v === 'success'
                ? <Tag color="green">{t('status.passed')}</Tag>
                : <Tag color="red">{t('status.failed')}</Tag>,
            },
            {
              title: t('ai.info'), dataIndex: 'last_test_message', ellipsis: true,
              render: (v: string | null) => v || '-',
            },
            { title: t('history.time'), dataIndex: 'last_test_at', width: 180 },
          ]}
        />
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 5: Tryon API Management
// ---------------------------------------------------------------------------
interface DraftTotokensProfile extends TotokensAPIProfile {
  draftApiKey: string
  modelsText: string
}

const TOTOKENS_SCOPE_KEY: Record<TotokensAPIScope, string> = {
  gemini: 'tryonRelay.scopeGemini',
  gpt_1k: 'tryonRelay.scopeGpt1k',
  gpt_2k4k: 'tryonRelay.scopeGpt2k4k',
  gpt_all: 'tryonRelay.scopeGptAll',
  custom: 'tryonRelay.scopeCustom',
}

const BUILTIN_PROFILE_LABEL_KEY: Record<string, string> = {
  totokens_gemini: 'tryonRelay.builtinLabelGemini',
  totokens_gpt_1k: 'tryonRelay.builtinLabelGpt1k',
  totokens_gpt_2k4k: 'tryonRelay.builtinLabelGpt2k4k',
}

function toDraftProfiles(items: TotokensAPIProfile[] | undefined): DraftTotokensProfile[] {
  return (items || []).map(item => ({
    ...item,
    draftApiKey: '',
    modelsText: (item.models || []).join(', '),
  }))
}

function TryonTab() {
  const { t } = useTranslation('common')
  const [config, setConfig] = useState<TryonAIConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testingProfileId, setTestingProfileId] = useState<string | null>(null)
  const [profiles, setProfiles] = useState<DraftTotokensProfile[]>([])
  const [deletedProfileIds, setDeletedProfileIds] = useState<string[]>([])
  const [form] = Form.useForm()
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)

  const syncFromConfig = useCallback((data: TryonAIConfig) => {
    setConfig(data)
    setProfiles(toDraftProfiles(data.totokens_apis))
    setDeletedProfileIds([])
    form.setFieldsValue({
      enabled: data.enabled,
      provider_key: data.provider_key,
      base_url: data.base_url,
      flash_model: data.flash_model,
      pro_model: data.pro_model,
      timeout_seconds: data.timeout_seconds,
      retry_count: data.retry_count,
      api_key: '', // never prefill
    })
  }, [form])

  const load = useCallback(async (providerKey?: string) => {
    setLoading(true)
    try {
      const res = await getTryonAIConfig(providerKey)
      syncFromConfig(res.data)
    } catch { /* ignore */ }
    setLoading(false)
  }, [syncFromConfig])

  useEffect(() => { load() }, [load])

  const updateProfileField = (id: string, patch: Partial<DraftTotokensProfile>) => {
    setProfiles(prev => prev.map(item => (item.id === id ? { ...item, ...patch } : item)))
  }

  const handleAddProfile = () => {
    const uid = `totokens_custom_${Date.now().toString(36)}`
    const fallbackUrl = form.getFieldValue('base_url') || config?.base_url || 'https://totokens.cc'
    setProfiles(prev => [
      ...prev,
      {
        id: uid,
        scope: 'gpt_all',
        label: t('tryonRelay.defaultProfileName'),
        builtin: false,
        enabled: true,
        base_url: fallbackUrl,
        has_api_key: false,
        key_status: 'ok',
        default_model: 'gpt-image-2',
        models: ['gpt-image-2'],
        timeout_seconds: 120,
        last_test_status: null,
        last_test_message: null,
        last_test_at: null,
        draftApiKey: '',
        modelsText: 'gpt-image-2',
      },
    ])
  }

  const handleSave = async (clearKey = false) => {
    setSaving(true)
    try {
      const values = await form.validateFields()
      const payload: Record<string, unknown> = {
        enabled: values.enabled,
        provider_key: values.provider_key,
        flash_model: values.flash_model?.trim(),
        pro_model: values.pro_model?.trim(),
        timeout_seconds: values.timeout_seconds,
        retry_count: values.provider_key === 'totokens' ? 0 : values.retry_count,
      }
      if (values.provider_key === 'totokens') {
        payload.base_url = values.base_url?.trim()
        const updates: TotokensAPIProfileUpdate[] = profiles.map(item => {
          const parsedModels = item.modelsText
            .split(/[\n,]/)
            .map(s => s.trim())
            .filter(Boolean)
          const itemPayload: TotokensAPIProfileUpdate = {
            id: item.id,
            enabled: item.enabled,
            base_url: item.base_url?.trim() || undefined,
            default_model: item.default_model?.trim() || undefined,
            models: parsedModels,
            timeout_seconds: item.timeout_seconds,
          }
          if (!item.builtin) {
            itemPayload.scope = item.scope
            itemPayload.label = item.label?.trim() || item.id
          }
          if (item.draftApiKey && item.draftApiKey.trim()) {
            itemPayload.api_key = item.draftApiKey.trim()
          }
          return itemPayload
        })
        deletedProfileIds.forEach(delId => {
          updates.push({ id: delId, delete: true })
        })
        payload.totokens_apis = updates
      }
      if (clearKey) {
        payload.clear_api_key = true
      } else if (values.api_key && values.api_key.trim()) {
        payload.api_key = values.api_key.trim()
      }
      const res = await updateTryonAIConfig(payload)
      message.success(t('ai.saveConfig'))
      syncFromConfig(res.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.unknown'))
    }
    setSaving(false)
  }

  const handleClearProfileKey = async (profileId: string) => {
    setSaving(true)
    try {
      const res = await updateTryonAIConfig({
        provider_key: 'totokens',
        totokens_apis: [{ id: profileId, clear_api_key: true }],
      })
      message.success(t('ai.saveConfig'))
      syncFromConfig(res.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.unknown'))
    }
    setSaving(false)
  }

  const handleDeleteProfile = (item: DraftTotokensProfile) => {
    if (item.builtin) return
    setProfiles(prev => prev.filter(p => p.id !== item.id))
    const existsOnServer = (config?.totokens_apis || []).some(p => p.id === item.id)
    if (existsOnServer) {
      setDeletedProfileIds(prev => (prev.includes(item.id) ? prev : [...prev, item.id]))
    }
  }

  const handleTestProfile = async (profileId: string) => {
    setTestingProfileId(profileId)
    try {
      const res = await testTryonAIConfig({ provider_key: 'totokens', profile_id: profileId })
      const data: TryonAIConfigTestResult = res.data
      if (data.success) {
        const count = (data.models_matched || []).length
        const suffix = count > 0 ? ` — ${t('tryonRelay.matchedModels', { count })}` : ''
        message.success(`${t('status.passed')} (${data.latency_ms}ms)${suffix}`)
      } else {
        message.warning(`${t('status.failed')}: ${data.message}`)
      }
      void load('totokens')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.network'))
    }
    setTestingProfileId(null)
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const res = await testTryonAIConfig()
      const data: TryonAIConfigTestResult = res.data
      if (data.success) {
        let msg = `${t('status.passed')} (${data.latency_ms}ms)`
        const checks: string[] = []
        if (data.model_check.flash_found) checks.push(`${config?.flash_model || t('ai.flash')} ✓`)
        if (data.model_check.pro_found) checks.push(`${config?.pro_model || t('aiExtra.pro')} ✓`)
        if (checks.length > 0) msg += ` — ${checks.join(', ')}`
        message.success(msg)
      } else {
        message.warning(`${t('status.failed')}: ${data.message}`)
      }
      load()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.network'))
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

  const hasAnyTotokensKey = Boolean(config?.has_api_key || config?.totokens_has_api_key)
  const canTestMain = config?.provider_key === 'totokens'
    ? (hasAnyTotokensKey && config.provider_key === config.active_provider_key)
    : Boolean(config?.has_api_key && config.provider_key === config.active_provider_key)

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>{t('ai.tryonConfig')}</Title>

      <Alert
        type="info"
        showIcon
        message={t('ai.unifiedHelp')}
        description={config?.provider_key === 'totokens' ? t('tryonRelay.help') : t('ai.unifiedHelp')}
        style={{ marginBottom: 16 }}
      />

      {config?.provider_key === 'gemini' && (
        <Alert
          type={config.totokens_enabled && config.totokens_has_api_key ? 'success' : 'warning'}
          showIcon
          message={
            config.totokens_enabled && config.totokens_has_api_key
              ? t('tryonRelay.companionReady', {
                count: config.totokens_configured_count ?? 1,
                model: config.totokens_chatgpt_model || 'gpt-image-2',
              })
              : t('tryonRelay.companionPending', { model: config.totokens_chatgpt_model || 'gpt-image-2' })
          }
          action={
            <Button size="small" onClick={() => { void load('totokens') }}>
              {t('tryonRelay.switchToRelay')}
            </Button>
          }
          style={{ marginBottom: 16 }}
        />
      )}

      <Card title={t('ai.provider')} style={{ marginBottom: 16 }}>
        <Descriptions column={{ xs: 1, sm: 2 }} size="small">
          <Descriptions.Item label="Provider">{config?.provider_key === 'totokens' ? 'ToTokens' : 'Google Gemini / AI Studio'}</Descriptions.Item>
          <Descriptions.Item label={t('ai.authType')}>{config?.provider_key === 'totokens' ? 'Bearer' : 'API Key'}</Descriptions.Item>
          <Descriptions.Item label={t('ai.provider')}>
            {config?.provider_enabled
              ? <Tag color="green">{t('status.enabled')}</Tag>
              : <Tag color="red">{t('status.disabled')}</Tag>
            }
          </Descriptions.Item>
          <Descriptions.Item label={t('ai.key')}>
            {(config?.provider_key === 'totokens' ? hasAnyTotokensKey : config?.has_api_key)
              ? config?.key_status === 'decrypt_failed'
                ? <Tag color="red">{t('status.failed')}</Tag>
                : <Tag color="green">{t('status.configured')}</Tag>
              : <Tag color="default">{t('ai.configured')}</Tag>
            }
          </Descriptions.Item>
          <Descriptions.Item label={t('ai.recentTest')}>
            {config?.last_test_status
              ? config.last_test_status === 'success'
                ? <Tag color="green">{t('status.passed')}</Tag>
                : <Tag color="red">{t('status.failed')}</Tag>
              : <Tag>{t('status.unknown')}</Tag>
            }
            {config?.last_test_at && (
              <Text type="secondary" style={{ marginLeft: 8 }}>
                {new Date(config.last_test_at).toLocaleString()}
              </Text>
            )}
          </Descriptions.Item>
          {config?.last_test_message && (
            <Descriptions.Item label={t('ai.info')} span={2}>
              {config.last_test_message}
            </Descriptions.Item>
          )}
          {config?.updated_at && (
            <Descriptions.Item label={t('prompts.updatedAt')}>
              {new Date(config.updated_at).toLocaleString()}
            </Descriptions.Item>
          )}
          {config?.updated_by && (
            <Descriptions.Item label={t('prompts.updatedBy')}>{config.updated_by}</Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card title={t('actions.edit')}>
        {config && !config.provider_enabled && (
          <Alert
            type="warning"
            showIcon
            message={t('status.disabled')}
            description={t('ai.unifiedHelp')}
            style={{ marginBottom: 16 }}
          />
        )}
        <Form form={form} layout="vertical" style={{ maxWidth: config?.provider_key === 'totokens' ? 920 : 600 }}>
          <Form.Item name="provider_key" label={t('tryonRelay.provider')} rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'gemini', label: 'Google Gemini / AI Studio' },
                { value: 'totokens', label: 'ToTokens' },
              ]}
              onChange={(value: string) => { void load(value) }}
            />
          </Form.Item>

          <Form.Item name="enabled" label={t('ai.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>

          {config?.provider_key === 'totokens' && (
            <Form.Item name="base_url" label={t('tryonRelay.baseUrl')} rules={[{ required: true }]}>
              <Input placeholder="https://totokens.cc" />
            </Form.Item>
          )}

          {config?.provider_key === 'totokens' && (
            <div style={{ marginBottom: 24 }}>
              <Divider orientation="left" style={{ marginTop: 8 }}>{t('tryonRelay.multiApiTitle')}</Divider>
              <Alert
                type="info"
                showIcon
                message={t('tryonRelay.multiApiHint')}
                style={{ marginBottom: 16 }}
              />
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                {profiles.map(profile => {
                  const titleText = profile.builtin && BUILTIN_PROFILE_LABEL_KEY[profile.id]
                    ? t(BUILTIN_PROFILE_LABEL_KEY[profile.id])
                    : profile.label
                  const scopeText = t(TOTOKENS_SCOPE_KEY[profile.scope] || 'tryonRelay.scopeCustom')
                  return (
                    <Card
                      key={profile.id}
                      size="small"
                      title={(
                        <Space wrap>
                          <Text strong>{titleText}</Text>
                          <Tag color="blue">{scopeText}</Tag>
                          {profile.has_api_key
                            ? profile.key_status === 'ok'
                              ? <Tag color="green">{t('status.configured')}</Tag>
                              : <Tag color="red">{t('status.failed')}</Tag>
                            : <Tag>{t('status.notConfigured')}</Tag>
                          }
                          {profile.last_test_status && (
                            <Tag color={profile.last_test_status === 'success' ? 'green' : 'red'}>
                              {profile.last_test_status === 'success' ? t('status.passed') : t('status.failed')}
                              {profile.last_test_message ? `: ${profile.last_test_message}` : ''}
                            </Tag>
                          )}
                        </Space>
                      )}
                      extra={(
                        <Space>
                          <Switch
                            size="small"
                            checked={profile.enabled}
                            onChange={checked => updateProfileField(profile.id, { enabled: checked })}
                          />
                          <Button
                            size="small"
                            icon={<ApiOutlined />}
                            loading={testingProfileId === profile.id}
                            disabled={!profile.has_api_key}
                            onClick={() => { void handleTestProfile(profile.id) }}
                          >
                            {t('tryonRelay.testProfile')}
                          </Button>
                          {profile.has_api_key && (
                            <Popconfirm
                              title={t('tryonRelay.confirmClearProfile')}
                              onConfirm={() => { void handleClearProfileKey(profile.id) }}
                              okText={t('actions.confirm')}
                              cancelText={t('actions.cancel')}
                              okButtonProps={{ danger: true }}
                            >
                              <Button size="small" danger>
                                {t('actions.clear')}
                              </Button>
                            </Popconfirm>
                          )}
                          {!profile.builtin && (
                            <Popconfirm
                              title={t('tryonRelay.confirmDeleteProfile')}
                              onConfirm={() => handleDeleteProfile(profile)}
                              okText={t('actions.confirm')}
                              cancelText={t('actions.cancel')}
                              okButtonProps={{ danger: true }}
                            >
                              <Button size="small" danger icon={<DeleteOutlined />} />
                            </Popconfirm>
                          )}
                        </Space>
                      )}
                    >
                      <Row gutter={[12, 12]}>
                        {!profile.builtin && (
                          <>
                            <Col xs={24} md={12}>
                              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>{t('tryonRelay.profileName')}</Text>
                              <Input
                                value={profile.label}
                                onChange={e => updateProfileField(profile.id, { label: e.target.value })}
                              />
                            </Col>
                            <Col xs={24} md={12}>
                              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>{t('tryonRelay.profileScope')}</Text>
                              <Select
                                style={{ width: '100%' }}
                                value={profile.scope}
                                onChange={val => updateProfileField(profile.id, { scope: val })}
                                options={[
                                  { value: 'gemini', label: t('tryonRelay.scopeGemini') },
                                  { value: 'gpt_1k', label: t('tryonRelay.scopeGpt1k') },
                                  { value: 'gpt_2k4k', label: t('tryonRelay.scopeGpt2k4k') },
                                  { value: 'gpt_all', label: t('tryonRelay.scopeGptAll') },
                                  { value: 'custom', label: t('tryonRelay.scopeCustom') },
                                ]}
                              />
                            </Col>
                          </>
                        )}
                        <Col xs={24} md={12}>
                          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>{t('ai.key')}</Text>
                          <Input.Password
                            value={profile.draftApiKey}
                            placeholder={profile.has_api_key ? t('tryonRelay.keyPlaceholderSaved') : t('tryonRelay.keyPlaceholderNew')}
                            onChange={e => updateProfileField(profile.id, { draftApiKey: e.target.value })}
                          />
                        </Col>
                        <Col xs={24} md={12}>
                          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>{t('tryonRelay.defaultModel')}</Text>
                          <Input
                            value={profile.default_model}
                            onChange={e => updateProfileField(profile.id, { default_model: e.target.value })}
                          />
                        </Col>
                        <Col xs={24} md={12}>
                          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>{t('tryonRelay.supportedModels')}</Text>
                          <Input
                            value={profile.modelsText}
                            onChange={e => updateProfileField(profile.id, { modelsText: e.target.value })}
                          />
                        </Col>
                        <Col xs={16} md={8}>
                          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>{t('tryonRelay.baseUrl')}</Text>
                          <Input
                            value={profile.base_url}
                            placeholder="https://totokens.cc"
                            onChange={e => updateProfileField(profile.id, { base_url: e.target.value })}
                          />
                        </Col>
                        <Col xs={8} md={4}>
                          <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>{t('ai.timeout')}</Text>
                          <InputNumber
                            min={10}
                            max={300}
                            style={{ width: '100%' }}
                            value={profile.timeout_seconds}
                            onChange={val => updateProfileField(profile.id, { timeout_seconds: Number(val || 120) })}
                          />
                        </Col>
                      </Row>
                    </Card>
                  )
                })}
                <Button icon={<PlusOutlined />} onClick={handleAddProfile} block>
                  {t('tryonRelay.addProfile')}
                </Button>
              </Space>
            </div>
          )}

          <Form.Item
            name="api_key"
            label={config?.provider_key === 'totokens' ? t('tryonRelay.fallbackKeyLabel') : t('ai.key')}
            extra={config?.provider_key === 'totokens' ? t('tryonRelay.fallbackKeyHint') : t('ai.optional')}
          >
            <Input.Password placeholder={t('ai.key')} />
          </Form.Item>

          <div style={{ marginBottom: 16 }}>
            <Popconfirm
              title={t('ai.confirmClear')}
              description={t('ai.clearKeyHelp')}
              open={clearConfirmOpen}
              onConfirm={handleClearKey}
              onCancel={() => setClearConfirmOpen(false)}
              okText={t('actions.confirm')}
              cancelText={t('actions.cancel')}
              okButtonProps={{ danger: true }}
            >
              <Button
                danger
                disabled={!config?.has_api_key || config.provider_key !== config.active_provider_key}
                onClick={() => setClearConfirmOpen(true)}
              >
                {t('ai.clearKey')}
              </Button>
            </Popconfirm>
          </div>

          <Form.Item
            name="flash_model"
            label={config?.provider_key === 'totokens' ? t('tryonRelay.geminiModel') : t('ai.flash')}
            rules={[{ required: true, message: t('ai.flash') }]}
          >
            <Input placeholder={config?.provider_key === 'totokens' ? 'gemini-3.1-flash-image' : 'gemini-3.1-flash-image-preview'} />
          </Form.Item>

          <Form.Item
            name="pro_model"
            label={config?.provider_key === 'totokens' ? t('tryonRelay.gptModel') : t('aiExtra.pro')}
            extra={config?.provider_key === 'totokens' ? t('tryonRelay.gptModelExtra') : undefined}
            rules={[{ required: true, message: t('aiExtra.pro') }]}
          >
            <Input placeholder={config?.provider_key === 'totokens' ? 'gpt-image-2' : 'gemini-3-pro-image-preview'} />
          </Form.Item>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            <Form.Item name="timeout_seconds" label={t('ai.timeout')} style={{ flex: '1 1 160px' }}>
              <InputNumber min={10} max={300} style={{ width: '100%' }} />
            </Form.Item>
            {config?.provider_key !== 'totokens' && (
              <Form.Item name="retry_count" label={t('ai.retry')} style={{ flex: '1 1 160px' }}>
                <InputNumber min={0} max={5} style={{ width: '100%' }} />
              </Form.Item>
            )}
          </div>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={saving}
                onClick={() => handleSave(false)}
              >
                {t('ai.saveConfig')}
              </Button>
              <Button
                icon={<ApiOutlined />}
                loading={testing}
                onClick={handleTest}
                disabled={!canTestMain}
              >
                {t('aiExtra.testConnection')}
              </Button>
              <Button icon={<ReloadOutlined />} onClick={() => { void load() }}>
                {t('actions.refresh')}
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
function initialTabKey() {
  if (typeof window === 'undefined') return 'overview'
  const tab = new URLSearchParams(window.location.search).get('tab')
  const allowed = new Set(['overview', 'tryon', 'video', 'realtime', 'providers', 'features', 'test'])
  return tab && allowed.has(tab) ? tab : 'overview'
}

export default function AIModelSettingsPage() {
  const { t } = useTranslation('common')
  const [activeTab, setActiveTab] = useState<string>(initialTabKey)

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        <ApiOutlined style={{ marginRight: 8 }} />
        {t('ai.title')}
      </Title>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'overview', label: t('ai.overview'), children: <OverviewTab /> },
          { key: 'tryon', label: t('ai.tryon'), children: <TryonTab /> },
          { key: 'video', label: t('videoSettings.title'), children: <VideoSettingsTab /> },
          { key: 'realtime', label: t('realtimeSettings.tabTitle'), children: <RealtimeSettingsTab /> },
          { key: 'providers', label: t('ai.providers'), children: <ProvidersTab /> },
          { key: 'features', label: t('ai.features'), children: <FeaturesTab /> },
          { key: 'test', label: t('ai.tests'), children: <TestTab /> },
        ]}
      />
    </div>
  )
}
