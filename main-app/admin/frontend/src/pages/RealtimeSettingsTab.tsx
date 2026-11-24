import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  type FormInstance,
} from 'antd'
import {
  ApiOutlined,
  CloudDownloadOutlined,
  KeyOutlined,
  MonitorOutlined,
  ReloadOutlined,
  SafetyOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  emergencyStopReactorRealtime,
  emergencyStopRealtime,
  emergencyStopXmaxRealtime,
  fetchRealtimeOfficialData,
  generateReactorRealtimeAccessCode,
  generateRealtimeAccessCode,
  generateXmaxRealtimeAccessCode,
  getReactorRealtimeConfig,
  getRealtimeConfig,
  getXmaxRealtimeConfig,
  testReactorRealtimeConnection,
  testRealtimeConnection,
  testXmaxRealtimeConnection,
  updateReactorRealtimeConfig,
  updateRealtimeConfig,
  updateXmaxRealtimeConfig,
  type OfficialRealtimeDataResponse,
  type ReactorModelId,
  type ReactorRealtimeConfig,
  type ReactorRealtimeConfigUpdatePayload,
  type RealtimeConfig,
  type RealtimeConfigUpdatePayload,
  type RealtimeProviderKey,
  type XmaxRealtimeConfig,
  type XmaxRealtimeConfigUpdatePayload,
} from '../api/realtimeTryon'

type DecartFormValues = RealtimeConfigUpdatePayload & {
  enabled: boolean
  require_access_code: boolean
  max_seconds: number
  default_seconds: number
  cents_per_second: number
  daily_cents: number
  monthly_cents: number
  visitor_daily_cents: number
  max_active: number
  starts_per_minute: number
  origin: string
  default_prompt: string
}

type XmaxFormValues = XmaxRealtimeConfigUpdatePayload & {
  enabled: boolean
  environment: 'global' | 'china'
  base_url: string
  default_model: 'x2.1' | 'x2.1-flash'
  allowed_models: Array<'x2.1' | 'x2.1-flash'>
  camera_preset: string
  face_restoration: boolean
  require_access_code: boolean
  min_seconds: number
  max_seconds: number
  default_seconds: number
  credits_per_second: number
  cents_per_minute: number
  daily_cents: number
  monthly_cents: number
  visitor_daily_cents: number
  min_account_credits: number
  max_active: number
  starts_per_minute: number
  origin: string
  default_prompt: string
}

type ReactorFormValues = ReactorRealtimeConfigUpdatePayload & {
  enabled: boolean
  base_url: string
  default_model: ReactorModelId
  allowed_models: ReactorModelId[]
  require_access_code: boolean
  min_seconds: number
  max_seconds: number
  default_seconds: number
  credits_per_second: number
  cents_per_minute: number
  daily_cents: number
  monthly_cents: number
  visitor_daily_cents: number
  min_account_credits: number
  max_active: number
  starts_per_minute: number
  origin: string
  default_prompt: string
}

const DECART_DEFAULTS: DecartFormValues = {
  enabled: false,
  require_access_code: true,
  origin: '',
  cents_per_second: 2,
  max_seconds: 20,
  default_seconds: 15,
  daily_cents: 200,
  monthly_cents: 1000,
  visitor_daily_cents: 80,
  max_active: 1,
  starts_per_minute: 3,
  default_prompt:
    "Replace the person's outfit with the garment shown in the reference image, keeping natural body motion, lighting, and face identity.",
  api_key: '',
  access_code: '',
}

const XMAX_DEFAULTS: XmaxFormValues = {
  enabled: false,
  environment: 'global',
  base_url: 'https://api.xmax.ai/open/api/v1',
  default_model: 'x2.1',
  allowed_models: ['x2.1', 'x2.1-flash'],
  camera_preset: '1080x1920',
  face_restoration: true,
  require_access_code: true,
  origin: '',
  min_seconds: 10,
  max_seconds: 60,
  default_seconds: 30,
  credits_per_second: 1,
  cents_per_minute: 10,
  daily_cents: 200,
  monthly_cents: 1000,
  visitor_daily_cents: 50,
  min_account_credits: 60,
  max_active: 1,
  starts_per_minute: 3,
  default_prompt: '将参考图的服装穿戴到视频角色身上，跟随角色原有动作。',
  api_key: '',
  access_code: '',
}

const REACTOR_DEFAULTS: ReactorFormValues = {
  enabled: false,
  base_url: 'https://api.reactor.inc',
  default_model: 'reactor/xmax-x2-1',
  allowed_models: ['reactor/xmax-x2-1', 'xmax/x2'],
  require_access_code: true,
  origin: '',
  min_seconds: 10,
  max_seconds: 60,
  default_seconds: 30,
  credits_per_second: 17,
  cents_per_minute: 11,
  daily_cents: 200,
  monthly_cents: 1000,
  visitor_daily_cents: 50,
  min_account_credits: 1000,
  max_active: 1,
  starts_per_minute: 3,
  default_prompt: '将参考图的服装穿戴到视频角色身上，保持人物面部、姿态和自然光影，服装贴合身体动作。',
  api_key: '',
  access_code: '',
}

const XMAX_CAMERA_OPTIONS: Record<'x2.1' | 'x2.1-flash', string[]> = {
  'x2.1': ['1080x1920', '1920x1080', '1152x1536', '1536x1152', '1408x1408'],
  'x2.1-flash': ['704x1280', '1280x704', '768x1024', '1024x768', '960x960'],
}

function errorText(error: unknown) {
  const failure = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
  return failure.response?.data?.detail || failure.response?.data?.message || failure.message || String(error)
}

function formatUsd(cents?: number) {
  const value = Number(cents ?? 0)
  return `$${(value / 100).toFixed(2)}`
}

type OfficialNotice = {
  source: OfficialRealtimeDataResponse['source']
  summary: string
  warning?: string | null
}

function StatusTags({
  title,
  config,
  extraTag,
}: {
  title: string
  config: RealtimeConfig | XmaxRealtimeConfig | ReactorRealtimeConfig | null
  extraTag?: React.ReactNode
}) {
  const { t } = useTranslation('common')
  return (
    <Space size="small" wrap>
      <span>{title}</span>
      <Tag color={config?.enabled ? 'processing' : 'default'}>
        {t(config?.enabled ? 'status.enabled' : 'status.disabled')}
      </Tag>
      <Tag color={config?.has_api_key && config?.key_decrypt_ok ? 'success' : 'warning'}>
        {t(config?.has_api_key ? 'realtimeSettings.keySaved' : 'realtimeSettings.keyMissing')}
      </Tag>
      {config?.require_access_code ? (
        <Tag color={config.has_access_code && config.access_code_decrypt_ok ? 'success' : 'warning'}>
          {t(config.has_access_code ? 'realtimeSettings.codeSaved' : 'realtimeSettings.codeMissing')}
        </Tag>
      ) : (
        <Tag color="blue">{t('realtimeSettings.codeOptionalTag')}</Tag>
      )}
      <Tag color={config?.ready_to_serve ? 'green' : 'default'}>
        {t(config?.ready_to_serve ? 'realtimeSettings.readyTag' : 'realtimeSettings.notReadyTag')}
      </Tag>
      {extraTag}
    </Space>
  )
}

function SharedAlerts({
  helpText,
  blockers,
  blockerPrefix,
  generatedCode,
  onCloseGeneratedCode,
  officialNotice,
  onCloseOfficialNotice,
  feedback,
}: {
  helpText: string
  blockers: string[]
  blockerPrefix: string
  generatedCode: string | null
  onCloseGeneratedCode: () => void
  officialNotice: OfficialNotice | null
  onCloseOfficialNotice: () => void
  feedback: { error: boolean; text: string } | null
}) {
  const { t } = useTranslation('common')
  const nonDisabledBlockers = blockers.filter((r) => r !== 'feature_disabled')
  return (
    <>
      <Alert type="info" showIcon message={helpText} style={{ marginBottom: 16 }} />

      {nonDisabledBlockers.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('realtimeSettings.blockersTitle')}
          description={nonDisabledBlockers
            .map((code) => t(`${blockerPrefix}.${code}`, { defaultValue: t(`realtimeSettings.blockers.${code}`, { defaultValue: code }) }))
            .join(' · ')}
        />
      )}

      {generatedCode && (
        <Alert
          type="success"
          showIcon
          closable
          onClose={onCloseGeneratedCode}
          style={{ marginBottom: 16 }}
          message={t('realtimeSettings.generatedCodeTitle')}
          description={
            <Space direction="vertical" size={4}>
              <Typography.Text copyable code>{generatedCode}</Typography.Text>
              <Typography.Text type="secondary">{t('realtimeSettings.generatedCodeHint')}</Typography.Text>
            </Space>
          }
        />
      )}

      {officialNotice && (
        <Alert
          type={officialNotice.warning ? 'warning' : 'info'}
          showIcon
          closable
          onClose={onCloseOfficialNotice}
          style={{ marginBottom: 16 }}
          message={`${t('realtimeSettings.fetchOfficialDone')} (${officialNotice.source})`}
          description={
            <Space direction="vertical" size={2}>
              <span>{officialNotice.summary}</span>
              {officialNotice.warning && (
                <Typography.Text type="secondary">{officialNotice.warning}</Typography.Text>
              )}
              <Typography.Text type="secondary">{t('realtimeSettings.fetchOfficialHint')}</Typography.Text>
            </Space>
          }
        />
      )}

      {feedback && (
        <Alert
          type={feedback.error ? 'error' : 'success'}
          showIcon
          message={feedback.text}
          style={{ marginBottom: 16 }}
        />
      )}
    </>
  )
}

function AccessCodeAndOriginSection({
  watchedRequireCode,
  config,
  busy,
  onGenerateCode,
  onClearCode,
}: {
  watchedRequireCode: boolean
  config: RealtimeConfig | XmaxRealtimeConfig | ReactorRealtimeConfig | null
  busy: boolean
  onGenerateCode: () => void
  onClearCode: () => void
}) {
  const { t } = useTranslation('common')
  return (
    <>
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Form.Item name="require_access_code" label={t('realtimeSettings.requireAccessCode')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Col>
        <Col xs={24} sm={16}>
          <Form.Item
            name="origin"
            label={t('realtimeSettings.origin')}
            extra={t('realtimeSettings.originHelp', { effective: config?.effective_origin || '-' })}
          >
            <Input placeholder={config?.effective_origin || 'https://tryon-workbench.example.azurecontainerapps.io'} />
          </Form.Item>
        </Col>
      </Row>

      {watchedRequireCode && (
        <Row gutter={16}>
          <Col xs={24} md={14}>
            <Form.Item
              name="access_code"
              label={t('realtimeSettings.accessCode')}
              extra={
                config?.has_access_code
                  ? t('realtimeSettings.codeSavedHint', { length: config.access_code_length })
                  : t('realtimeSettings.codeMissingHint')
              }
            >
              <Input.Password
                autoComplete="new-password"
                placeholder={t('realtimeSettings.codePlaceholder')}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={10} style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, paddingTop: 6 }}>
            <Button icon={<KeyOutlined />} loading={busy} onClick={onGenerateCode}>
              {t('realtimeSettings.generateCode')}
            </Button>
            <Popconfirm title={t('realtimeSettings.clearCodeConfirm')} onConfirm={onClearCode}>
              <Button danger disabled={busy || !config?.has_access_code}>
                {t('realtimeSettings.clearCode')}
              </Button>
            </Popconfirm>
          </Col>
        </Row>
      )}
    </>
  )
}

function SharedBudgetLimitsAndPrompt({
  watchedDaily,
  watchedMonthly,
  watchedVisitor,
  maxCostText,
  visitorMaxSessions,
  dailyMaxSessions,
  monthlyMaxSessions,
}: {
  watchedDaily: number
  watchedMonthly: number
  watchedVisitor: number
  maxCostText: string
  visitorMaxSessions: number
  dailyMaxSessions: number
  monthlyMaxSessions: number
}) {
  const { t } = useTranslation('common')
  return (
    <>
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Form.Item
            name="daily_cents"
            label={t('realtimeSettings.dailyCents')}
            extra={formatUsd(watchedDaily)}
            rules={[{ required: true }]}
          >
            <InputNumber min={0} max={10000000} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item
            name="monthly_cents"
            label={t('realtimeSettings.monthlyCents')}
            extra={formatUsd(watchedMonthly)}
            rules={[{ required: true }]}
          >
            <InputNumber min={0} max={10000000} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={8}>
          <Form.Item
            name="visitor_daily_cents"
            label={t('realtimeSettings.visitorDailyCents')}
            extra={formatUsd(watchedVisitor)}
            rules={[{ required: true }]}
          >
            <InputNumber min={0} max={10000000} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col xs={24} sm={12}>
          <Form.Item name="max_active" label={t('realtimeSettings.maxActive')} rules={[{ required: true }]}>
            <InputNumber min={1} max={5} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item name="starts_per_minute" label={t('realtimeSettings.startsPerMinute')} rules={[{ required: true }]}>
            <InputNumber min={1} max={30} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <Form.Item name="default_prompt" label={t('realtimeSettings.defaultPrompt')}>
        <Input.TextArea rows={2} maxLength={280} showCount />
      </Form.Item>

      <Alert
        type="success"
        showIcon
        icon={<SafetyOutlined />}
        style={{ marginBottom: 18 }}
        message={t('realtimeSettings.capacityEstimate', {
          maxCost: maxCostText,
          visitorSessions: visitorMaxSessions,
          dailySessions: dailyMaxSessions,
          monthlySessions: monthlyMaxSessions,
        })}
      />
    </>
  )
}

async function runFetchOfficial<T extends object>(
  provider: RealtimeProviderKey,
  form: FormInstance<T>,
  setFetchingOfficial: (v: boolean) => void,
  setOfficialNotice: (v: OfficialNotice | null) => void,
  setFeedback: (v: { error: boolean; text: string } | null) => void,
  setLiveBalance?: (v: number | null) => void,
) {
  setFetchingOfficial(true)
  try {
    const rawValues = form.getFieldsValue() as Record<string, unknown>
    const rawKey = typeof rawValues.api_key === 'string' ? rawValues.api_key.trim() : ''
    const { data } = await fetchRealtimeOfficialData(provider, {
      base_url: typeof rawValues.base_url === 'string' ? rawValues.base_url.trim() : undefined,
      environment: typeof rawValues.environment === 'string' ? rawValues.environment : undefined,
      api_key: rawKey || undefined,
    })
    if (data.suggested_fields && Object.keys(data.suggested_fields).length > 0) {
      form.setFieldsValue(data.suggested_fields as Parameters<FormInstance<T>['setFieldsValue']>[0])
    }
    if (setLiveBalance && typeof data.account_info?.balance === 'number') {
      setLiveBalance(data.account_info.balance)
    }
    setOfficialNotice({
      source: data.source,
      summary: data.summary,
      warning: data.warning,
    })
  } catch (error) {
    setFeedback({ error: true, text: errorText(error) })
  } finally {
    setFetchingOfficial(false)
  }
}

function DecartSettingsPanel() {
  const { t } = useTranslation('common')
  const navigate = useNavigate()
  const [form] = Form.useForm<DecartFormValues>()
  const [config, setConfig] = useState<RealtimeConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [fetchingOfficial, setFetchingOfficial] = useState(false)
  const [generatedCode, setGeneratedCode] = useState<string | null>(null)
  const [officialNotice, setOfficialNotice] = useState<OfficialNotice | null>(null)
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const watchedCps = Form.useWatch('cents_per_second', form) ?? config?.cents_per_second ?? DECART_DEFAULTS.cents_per_second
  const watchedMaxSec = Form.useWatch('max_seconds', form) ?? config?.max_seconds ?? DECART_DEFAULTS.max_seconds
  const watchedDaily = Form.useWatch('daily_cents', form) ?? config?.daily_cents ?? DECART_DEFAULTS.daily_cents
  const watchedMonthly = Form.useWatch('monthly_cents', form) ?? config?.monthly_cents ?? DECART_DEFAULTS.monthly_cents
  const watchedVisitor = Form.useWatch('visitor_daily_cents', form) ?? config?.visitor_daily_cents ?? DECART_DEFAULTS.visitor_daily_cents
  const watchedRequireCode = Form.useWatch('require_access_code', form) ?? config?.require_access_code ?? DECART_DEFAULTS.require_access_code

  const applyConfig = useCallback((data: RealtimeConfig) => {
    setConfig(data)
    form.setFieldsValue({
      enabled: data.enabled ?? DECART_DEFAULTS.enabled,
      require_access_code: data.require_access_code ?? DECART_DEFAULTS.require_access_code,
      origin: data.origin ?? DECART_DEFAULTS.origin,
      max_seconds: data.max_seconds ?? DECART_DEFAULTS.max_seconds,
      default_seconds: data.default_seconds ?? DECART_DEFAULTS.default_seconds,
      cents_per_second: data.cents_per_second ?? DECART_DEFAULTS.cents_per_second,
      daily_cents: data.daily_cents ?? DECART_DEFAULTS.daily_cents,
      monthly_cents: data.monthly_cents ?? DECART_DEFAULTS.monthly_cents,
      visitor_daily_cents: data.visitor_daily_cents ?? DECART_DEFAULTS.visitor_daily_cents,
      max_active: data.max_active ?? DECART_DEFAULTS.max_active,
      starts_per_minute: data.starts_per_minute ?? DECART_DEFAULTS.starts_per_minute,
      default_prompt: data.default_prompt || DECART_DEFAULTS.default_prompt,
      api_key: '',
      access_code: '',
    })
  }, [form])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await getRealtimeConfig()
      if (mountedRef.current) applyConfig(data)
    } catch (error) {
      if (mountedRef.current) setFeedback({ error: true, text: errorText(error) })
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [applyConfig])

  useEffect(() => {
    void load()
  }, [load])

  async function save(options: { clearApiKey?: boolean; clearAccessCode?: boolean } = {}) {
    setBusy(true)
    try {
      const values = await form.validateFields()
      const { api_key: rawKey, access_code: rawCode, ...rest } = values
      const payload: RealtimeConfigUpdatePayload = {
        ...rest,
        origin: values.origin?.trim() ?? '',
        default_prompt: values.default_prompt?.trim() ?? '',
      }
      if (options.clearApiKey) payload.clear_api_key = true
      else if (rawKey?.trim()) payload.api_key = rawKey.trim()
      if (options.clearAccessCode) payload.clear_access_code = true
      else if (rawCode?.trim()) payload.access_code = rawCode.trim()

      const { data } = await updateRealtimeConfig(payload)
      applyConfig(data)
      if (options.clearAccessCode || rawCode?.trim()) setGeneratedCode(null)
      setOfficialNotice(null)
      setFeedback({ error: false, text: `${t('actions.save')} ✓` })
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleGenerateCode() {
    setBusy(true)
    try {
      const { data } = await generateRealtimeAccessCode()
      applyConfig(data.config)
      setGeneratedCode(data.access_code)
      setFeedback({ error: false, text: t('realtimeSettings.codeGenerated') })
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleTestConnection() {
    setBusy(true)
    try {
      const { data } = await testRealtimeConnection()
      setFeedback({
        error: !data.success,
        text: `${data.success ? '✓' : `HTTP ${data.status_code || 'ERR'}`} · ${data.latency_ms} ms · ${data.message}`,
      })
      await load()
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleEmergencyStop() {
    setBusy(true)
    try {
      const { data } = await emergencyStopRealtime('decart')
      setFeedback({
        error: false,
        text: t('realtimeSettings.emergencyDone', {
          canceled: data.canceled_reserved,
          signaled: data.signaled_active,
        }),
      })
      await load()
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  const maxSessionCents = Math.max(1, watchedCps * watchedMaxSec)

  return (
    <Card
      title={<StatusTags title={t('realtimeSettings.title')} config={config} />}
      extra={
        <Space wrap>
          <Button
            icon={<CloudDownloadOutlined />}
            loading={fetchingOfficial}
            onClick={() => {
              void runFetchOfficial('decart', form, setFetchingOfficial, setOfficialNotice, setFeedback)
            }}
          >
            {t('realtimeSettings.fetchOfficial')}
          </Button>
          <Button icon={<MonitorOutlined />} onClick={() => navigate('/realtime-tryon?provider=decart')}>
            {t('realtimeSettings.openMonitor')}
          </Button>
          <Popconfirm title={t('realtimeSettings.emergencyConfirm')} onConfirm={() => { void handleEmergencyStop() }}>
            <Button danger icon={<StopOutlined />} loading={busy}>
              {t('realtimeSettings.emergencyStop')}
            </Button>
          </Popconfirm>
        </Space>
      }
    >
      <SharedAlerts
        helpText={t('realtimeSettings.help')}
        blockers={config?.blocking_reasons || []}
        blockerPrefix="realtimeSettings.blockers"
        generatedCode={generatedCode}
        onCloseGeneratedCode={() => setGeneratedCode(null)}
        officialNotice={officialNotice}
        onCloseOfficialNotice={() => setOfficialNotice(null)}
        feedback={feedback}
      />

      <Spin spinning={loading}>
        <Form form={form} initialValues={DECART_DEFAULTS} layout="vertical" style={{ maxWidth: 820 }}>
          <Row gutter={16} align="middle">
            <Col xs={24} sm={12}>
              <Form.Item name="enabled" label={t('realtimeSettings.enabled')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label={t('realtimeSettings.modelLabel')}>
                <Tag color="geekblue">lucy-vton-3.6 · 720p</Tag>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} md={14}>
              <Form.Item
                name="api_key"
                label={t('realtimeSettings.apiKey')}
                extra={t(config?.has_api_key ? 'realtimeSettings.keySavedHint' : 'realtimeSettings.keyMissing')}
              >
                <Input.Password
                  autoComplete="new-password"
                  placeholder={t(config?.has_api_key ? 'realtimeSettings.keySavedHint' : 'realtimeSettings.keyPlaceholder')}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={10} style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, paddingTop: 6 }}>
              <Button
                icon={<ApiOutlined />}
                loading={busy}
                disabled={loading || !config?.has_api_key}
                onClick={() => { void handleTestConnection() }}
              >
                {t('realtimeSettings.test')}
              </Button>
              <Popconfirm title={t('realtimeSettings.clearKeyConfirm')} onConfirm={() => { void save({ clearApiKey: true }) }}>
                <Button danger disabled={busy || !config?.has_api_key}>
                  {t('realtimeSettings.clearKey')}
                </Button>
              </Popconfirm>
            </Col>
          </Row>

          <AccessCodeAndOriginSection
            watchedRequireCode={watchedRequireCode}
            config={config}
            busy={busy}
            onGenerateCode={() => { void handleGenerateCode() }}
            onClearCode={() => { void save({ clearAccessCode: true }) }}
          />

          <Divider>{t('realtimeSettings.budgetSection')}</Divider>

          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item
                name="cents_per_second"
                label={t('realtimeSettings.centsPerSecond')}
                extra={`${formatUsd(watchedCps)}/s`}
                rules={[{ required: true }]}
              >
                <InputNumber min={2} max={1000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="max_seconds"
                label={t('realtimeSettings.maxSeconds')}
                extra={`${t('realtimeSettings.maxSessionCost')}: ${formatUsd(maxSessionCents)}`}
                rules={[{ required: true }]}
              >
                <InputNumber min={10} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="default_seconds" label={t('realtimeSettings.defaultSeconds')} rules={[{ required: true }]}>
                <InputNumber min={10} max={watchedMaxSec} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <SharedBudgetLimitsAndPrompt
            watchedDaily={watchedDaily}
            watchedMonthly={watchedMonthly}
            watchedVisitor={watchedVisitor}
            maxCostText={formatUsd(maxSessionCents)}
            visitorMaxSessions={Math.floor(watchedVisitor / maxSessionCents)}
            dailyMaxSessions={Math.floor(watchedDaily / maxSessionCents)}
            monthlyMaxSessions={Math.floor(watchedMonthly / maxSessionCents)}
          />

          <Space wrap>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={busy} disabled={loading} onClick={() => { void save() }}>
              {t('actions.save')}
            </Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => { void load() }}>
              {t('actions.refresh')}
            </Button>
          </Space>

          <Typography.Paragraph type="secondary" style={{ marginTop: 14, marginBottom: 6 }}>
            {t('realtimeSettings.testHelp')}
          </Typography.Paragraph>
          <Typography.Link href="https://docs.platform.decart.ai/getting-started/pricing" target="_blank" rel="noopener noreferrer">
            {t('realtimeSettings.docs')}
          </Typography.Link>
        </Form>
      </Spin>
    </Card>
  )
}

function ReactorSettingsPanel() {
  const { t } = useTranslation('common')
  const navigate = useNavigate()
  const [form] = Form.useForm<ReactorFormValues>()
  const [config, setConfig] = useState<ReactorRealtimeConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [fetchingOfficial, setFetchingOfficial] = useState(false)
  const [generatedCode, setGeneratedCode] = useState<string | null>(null)
  const [liveBalance, setLiveBalance] = useState<number | null>(null)
  const [officialNotice, setOfficialNotice] = useState<OfficialNotice | null>(null)
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const watchedCpm = Form.useWatch('cents_per_minute', form) ?? config?.cents_per_minute ?? REACTOR_DEFAULTS.cents_per_minute
  const watchedCreditsPs = Form.useWatch('credits_per_second', form) ?? config?.credits_per_second ?? REACTOR_DEFAULTS.credits_per_second
  const watchedMinSec = Form.useWatch('min_seconds', form) ?? config?.min_seconds ?? REACTOR_DEFAULTS.min_seconds
  const watchedMaxSec = Form.useWatch('max_seconds', form) ?? config?.max_seconds ?? REACTOR_DEFAULTS.max_seconds
  const watchedDaily = Form.useWatch('daily_cents', form) ?? config?.daily_cents ?? REACTOR_DEFAULTS.daily_cents
  const watchedMonthly = Form.useWatch('monthly_cents', form) ?? config?.monthly_cents ?? REACTOR_DEFAULTS.monthly_cents
  const watchedVisitor = Form.useWatch('visitor_daily_cents', form) ?? config?.visitor_daily_cents ?? REACTOR_DEFAULTS.visitor_daily_cents
  const watchedRequireCode = Form.useWatch('require_access_code', form) ?? config?.require_access_code ?? REACTOR_DEFAULTS.require_access_code

  const applyConfig = useCallback((data: ReactorRealtimeConfig) => {
    setConfig(data)
    form.setFieldsValue({
      enabled: data.enabled ?? REACTOR_DEFAULTS.enabled,
      base_url: data.base_url || REACTOR_DEFAULTS.base_url,
      default_model: data.default_model || REACTOR_DEFAULTS.default_model,
      allowed_models: data.allowed_models?.length ? data.allowed_models : REACTOR_DEFAULTS.allowed_models,
      require_access_code: data.require_access_code ?? REACTOR_DEFAULTS.require_access_code,
      origin: data.origin ?? REACTOR_DEFAULTS.origin,
      min_seconds: data.min_seconds ?? REACTOR_DEFAULTS.min_seconds,
      max_seconds: data.max_seconds ?? REACTOR_DEFAULTS.max_seconds,
      default_seconds: data.default_seconds ?? REACTOR_DEFAULTS.default_seconds,
      credits_per_second: data.credits_per_second ?? REACTOR_DEFAULTS.credits_per_second,
      cents_per_minute: data.cents_per_minute ?? REACTOR_DEFAULTS.cents_per_minute,
      daily_cents: data.daily_cents ?? REACTOR_DEFAULTS.daily_cents,
      monthly_cents: data.monthly_cents ?? REACTOR_DEFAULTS.monthly_cents,
      visitor_daily_cents: data.visitor_daily_cents ?? REACTOR_DEFAULTS.visitor_daily_cents,
      min_account_credits: data.min_account_credits ?? REACTOR_DEFAULTS.min_account_credits,
      max_active: data.max_active ?? REACTOR_DEFAULTS.max_active,
      starts_per_minute: data.starts_per_minute ?? REACTOR_DEFAULTS.starts_per_minute,
      default_prompt: data.default_prompt || REACTOR_DEFAULTS.default_prompt,
      api_key: '',
      access_code: '',
    })
  }, [form])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await getReactorRealtimeConfig()
      if (mountedRef.current) applyConfig(data)
    } catch (error) {
      if (mountedRef.current) setFeedback({ error: true, text: errorText(error) })
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [applyConfig])

  useEffect(() => {
    void load()
  }, [load])

  async function save(options: { clearApiKey?: boolean; clearAccessCode?: boolean } = {}) {
    setBusy(true)
    try {
      const values = await form.validateFields()
      const { api_key: rawKey, access_code: rawCode, ...rest } = values
      const payload: ReactorRealtimeConfigUpdatePayload = {
        ...rest,
        base_url: values.base_url?.trim() ?? '',
        origin: values.origin?.trim() ?? '',
        default_prompt: values.default_prompt?.trim() ?? '',
      }
      if (options.clearApiKey) payload.clear_api_key = true
      else if (rawKey?.trim()) payload.api_key = rawKey.trim()
      if (options.clearAccessCode) payload.clear_access_code = true
      else if (rawCode?.trim()) payload.access_code = rawCode.trim()

      const { data } = await updateReactorRealtimeConfig(payload)
      applyConfig(data)
      if (options.clearAccessCode || rawCode?.trim()) setGeneratedCode(null)
      setOfficialNotice(null)
      setFeedback({ error: false, text: `${t('actions.save')} ✓` })
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleGenerateCode() {
    setBusy(true)
    try {
      const { data } = await generateReactorRealtimeAccessCode()
      applyConfig(data.config)
      setGeneratedCode(data.access_code)
      setFeedback({ error: false, text: t('realtimeSettings.codeGenerated') })
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleTestConnection() {
    setBusy(true)
    try {
      const { data } = await testReactorRealtimeConnection()
      if (typeof data.current_balance === 'number') setLiveBalance(data.current_balance)
      setFeedback({
        error: !data.success,
        text: `${data.success ? '✓' : `HTTP ${data.status_code || 'ERR'}`} · ${data.latency_ms} ms · ${data.message}`,
      })
      await load()
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleEmergencyStop() {
    setBusy(true)
    try {
      const { data } = await emergencyStopReactorRealtime()
      setFeedback({
        error: false,
        text: t('realtimeSettings.emergencyDone', {
          canceled: data.canceled_reserved,
          signaled: data.signaled_active,
        }),
      })
      await load()
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  const maxSessionCents = Math.max(1, Math.ceil((watchedMaxSec * watchedCpm) / 60))
  const maxSessionCredits = Math.ceil(watchedMaxSec * watchedCreditsPs)

  return (
    <Card
      title={
        <StatusTags
          title={t('realtimeSettings.reactorTitle')}
          config={config}
          extraTag={
            liveBalance !== null ? (
              <Tag color="cyan">{t('realtimeSettings.reactorBalanceTag', { balance: liveBalance })}</Tag>
            ) : undefined
          }
        />
      }
      extra={
        <Space wrap>
          <Button
            icon={<CloudDownloadOutlined />}
            loading={fetchingOfficial}
            onClick={() => {
              void runFetchOfficial('reactor', form, setFetchingOfficial, setOfficialNotice, setFeedback, setLiveBalance)
            }}
          >
            {t('realtimeSettings.fetchOfficial')}
          </Button>
          <Button icon={<MonitorOutlined />} onClick={() => navigate('/realtime-tryon?provider=reactor')}>
            {t('realtimeSettings.openMonitor')}
          </Button>
          <Popconfirm title={t('realtimeSettings.reactorEmergencyConfirm')} onConfirm={() => { void handleEmergencyStop() }}>
            <Button danger icon={<StopOutlined />} loading={busy}>
              {t('realtimeSettings.emergencyStop')}
            </Button>
          </Popconfirm>
        </Space>
      }
    >
      <SharedAlerts
        helpText={t('realtimeSettings.reactorHelp')}
        blockers={config?.blocking_reasons || []}
        blockerPrefix="realtimeSettings.reactorBlockers"
        generatedCode={generatedCode}
        onCloseGeneratedCode={() => setGeneratedCode(null)}
        officialNotice={officialNotice}
        onCloseOfficialNotice={() => setOfficialNotice(null)}
        feedback={feedback}
      />

      <Spin spinning={loading}>
        <Form form={form} initialValues={REACTOR_DEFAULTS} layout="vertical" style={{ maxWidth: 860 }}>
          <Row gutter={16} align="middle">
            <Col xs={24} sm={8}>
              <Form.Item name="enabled" label={t('realtimeSettings.reactorEnabled')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="default_model" label={t('realtimeSettings.reactorDefaultModel')}>
                <Select
                  options={[
                    { value: 'reactor/xmax-x2-1', label: 'Xmax X2.1 (reactor/xmax-x2-1)' },
                    { value: 'xmax/x2', label: 'Xmax X2.0 (xmax/x2)' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="allowed_models" label={t('realtimeSettings.reactorAllowedModels')}>
                <Select
                  mode="multiple"
                  options={[
                    { value: 'reactor/xmax-x2-1', label: 'reactor/xmax-x2-1 (X2.1)' },
                    { value: 'xmax/x2', label: 'xmax/x2 (X2.0)' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="base_url" label={t('realtimeSettings.reactorBaseUrl')}>
            <Input placeholder="https://api.reactor.inc" />
          </Form.Item>

          <Row gutter={16}>
            <Col xs={24} md={14}>
              <Form.Item
                name="api_key"
                label={t('realtimeSettings.reactorApiKey')}
                extra={t(config?.has_api_key ? 'realtimeSettings.keySavedHint' : 'realtimeSettings.keyMissing')}
              >
                <Input.Password
                  autoComplete="new-password"
                  placeholder={t(config?.has_api_key ? 'realtimeSettings.keySavedHint' : 'realtimeSettings.reactorKeyPlaceholder')}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={10} style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, paddingTop: 6 }}>
              <Button
                icon={<ApiOutlined />}
                loading={busy}
                disabled={loading || !config?.has_api_key}
                onClick={() => { void handleTestConnection() }}
              >
                {t('realtimeSettings.reactorTest')}
              </Button>
              <Popconfirm title={t('realtimeSettings.reactorClearKeyConfirm')} onConfirm={() => { void save({ clearApiKey: true }) }}>
                <Button danger disabled={busy || !config?.has_api_key}>
                  {t('realtimeSettings.clearKey')}
                </Button>
              </Popconfirm>
            </Col>
          </Row>

          <AccessCodeAndOriginSection
            watchedRequireCode={watchedRequireCode}
            config={config}
            busy={busy}
            onGenerateCode={() => { void handleGenerateCode() }}
            onClearCode={() => { void save({ clearAccessCode: true }) }}
          />

          <Divider>{t('realtimeSettings.budgetSection')}</Divider>

          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item name="credits_per_second" label={t('realtimeSettings.xmaxCreditsPerSecond')} rules={[{ required: true }]}>
                <InputNumber min={1} max={10000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="cents_per_minute"
                label={t('realtimeSettings.xmaxCentsPerMinute')}
                extra={`${formatUsd(watchedCpm)}/min`}
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={10000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="min_account_credits" label={t('realtimeSettings.xmaxMinAccountCredits')} rules={[{ required: true }]}>
                <InputNumber min={0} max={10000000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item name="min_seconds" label={t('realtimeSettings.xmaxMinSeconds')} rules={[{ required: true }]}>
                <InputNumber min={10} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="max_seconds"
                label={t('realtimeSettings.maxSeconds')}
                extra={`${t('realtimeSettings.maxSessionCost')}: ${maxSessionCredits} cr / ${formatUsd(maxSessionCents)}`}
                rules={[{ required: true }]}
              >
                <InputNumber min={watchedMinSec} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="default_seconds" label={t('realtimeSettings.defaultSeconds')} rules={[{ required: true }]}>
                <InputNumber min={watchedMinSec} max={watchedMaxSec} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <SharedBudgetLimitsAndPrompt
            watchedDaily={watchedDaily}
            watchedMonthly={watchedMonthly}
            watchedVisitor={watchedVisitor}
            maxCostText={`${formatUsd(maxSessionCents)} (${maxSessionCredits} cr)`}
            visitorMaxSessions={Math.floor(watchedVisitor / maxSessionCents)}
            dailyMaxSessions={Math.floor(watchedDaily / maxSessionCents)}
            monthlyMaxSessions={Math.floor(watchedMonthly / maxSessionCents)}
          />

          <Space wrap>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={busy} disabled={loading} onClick={() => { void save() }}>
              {t('actions.save')}
            </Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => { void load() }}>
              {t('actions.refresh')}
            </Button>
          </Space>

          <Typography.Paragraph type="secondary" style={{ marginTop: 14, marginBottom: 6 }}>
            {t('realtimeSettings.reactorTestHelp')}
          </Typography.Paragraph>
          <Typography.Link href="https://www.reactor.inc/models/xmax-x2-1" target="_blank" rel="noopener noreferrer">
            {t('realtimeSettings.reactorDocs')}
          </Typography.Link>
        </Form>
      </Spin>
    </Card>
  )
}

function XmaxSettingsPanel() {
  const { t } = useTranslation('common')
  const navigate = useNavigate()
  const [form] = Form.useForm<XmaxFormValues>()
  const [config, setConfig] = useState<XmaxRealtimeConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [fetchingOfficial, setFetchingOfficial] = useState(false)
  const [generatedCode, setGeneratedCode] = useState<string | null>(null)
  const [liveBalance, setLiveBalance] = useState<number | null>(null)
  const [officialNotice, setOfficialNotice] = useState<OfficialNotice | null>(null)
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const watchedModel = Form.useWatch('default_model', form) ?? config?.default_model ?? XMAX_DEFAULTS.default_model
  const watchedCpm = Form.useWatch('cents_per_minute', form) ?? config?.cents_per_minute ?? XMAX_DEFAULTS.cents_per_minute
  const watchedCreditsPs = Form.useWatch('credits_per_second', form) ?? config?.credits_per_second ?? XMAX_DEFAULTS.credits_per_second
  const watchedMinSec = Form.useWatch('min_seconds', form) ?? config?.min_seconds ?? XMAX_DEFAULTS.min_seconds
  const watchedMaxSec = Form.useWatch('max_seconds', form) ?? config?.max_seconds ?? XMAX_DEFAULTS.max_seconds
  const watchedDaily = Form.useWatch('daily_cents', form) ?? config?.daily_cents ?? XMAX_DEFAULTS.daily_cents
  const watchedMonthly = Form.useWatch('monthly_cents', form) ?? config?.monthly_cents ?? XMAX_DEFAULTS.monthly_cents
  const watchedVisitor = Form.useWatch('visitor_daily_cents', form) ?? config?.visitor_daily_cents ?? XMAX_DEFAULTS.visitor_daily_cents
  const watchedRequireCode = Form.useWatch('require_access_code', form) ?? config?.require_access_code ?? XMAX_DEFAULTS.require_access_code

  const applyConfig = useCallback((data: XmaxRealtimeConfig) => {
    setConfig(data)
    form.setFieldsValue({
      enabled: data.enabled ?? XMAX_DEFAULTS.enabled,
      environment: data.environment ?? XMAX_DEFAULTS.environment,
      base_url: data.base_url || XMAX_DEFAULTS.base_url,
      default_model: data.default_model || XMAX_DEFAULTS.default_model,
      allowed_models: data.allowed_models?.length ? data.allowed_models : XMAX_DEFAULTS.allowed_models,
      camera_preset: data.camera_preset || XMAX_DEFAULTS.camera_preset,
      face_restoration: data.face_restoration ?? XMAX_DEFAULTS.face_restoration,
      require_access_code: data.require_access_code ?? XMAX_DEFAULTS.require_access_code,
      origin: data.origin ?? XMAX_DEFAULTS.origin,
      min_seconds: data.min_seconds ?? XMAX_DEFAULTS.min_seconds,
      max_seconds: data.max_seconds ?? XMAX_DEFAULTS.max_seconds,
      default_seconds: data.default_seconds ?? XMAX_DEFAULTS.default_seconds,
      credits_per_second: data.credits_per_second ?? XMAX_DEFAULTS.credits_per_second,
      cents_per_minute: data.cents_per_minute ?? XMAX_DEFAULTS.cents_per_minute,
      daily_cents: data.daily_cents ?? XMAX_DEFAULTS.daily_cents,
      monthly_cents: data.monthly_cents ?? XMAX_DEFAULTS.monthly_cents,
      visitor_daily_cents: data.visitor_daily_cents ?? XMAX_DEFAULTS.visitor_daily_cents,
      min_account_credits: data.min_account_credits ?? XMAX_DEFAULTS.min_account_credits,
      max_active: data.max_active ?? XMAX_DEFAULTS.max_active,
      starts_per_minute: data.starts_per_minute ?? XMAX_DEFAULTS.starts_per_minute,
      default_prompt: data.default_prompt || XMAX_DEFAULTS.default_prompt,
      api_key: '',
      access_code: '',
    })
  }, [form])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await getXmaxRealtimeConfig()
      if (mountedRef.current) applyConfig(data)
    } catch (error) {
      if (mountedRef.current) setFeedback({ error: true, text: errorText(error) })
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [applyConfig])

  useEffect(() => {
    void load()
  }, [load])

  async function save(options: { clearApiKey?: boolean; clearAccessCode?: boolean } = {}) {
    setBusy(true)
    try {
      const values = await form.validateFields()
      const { api_key: rawKey, access_code: rawCode, ...rest } = values
      const payload: XmaxRealtimeConfigUpdatePayload = {
        ...rest,
        base_url: values.base_url?.trim() ?? '',
        origin: values.origin?.trim() ?? '',
        default_prompt: values.default_prompt?.trim() ?? '',
      }
      if (options.clearApiKey) payload.clear_api_key = true
      else if (rawKey?.trim()) payload.api_key = rawKey.trim()
      if (options.clearAccessCode) payload.clear_access_code = true
      else if (rawCode?.trim()) payload.access_code = rawCode.trim()

      const { data } = await updateXmaxRealtimeConfig(payload)
      applyConfig(data)
      if (options.clearAccessCode || rawCode?.trim()) setGeneratedCode(null)
      setOfficialNotice(null)
      setFeedback({ error: false, text: `${t('actions.save')} ✓` })
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleGenerateCode() {
    setBusy(true)
    try {
      const { data } = await generateXmaxRealtimeAccessCode()
      applyConfig(data.config)
      setGeneratedCode(data.access_code)
      setFeedback({ error: false, text: t('realtimeSettings.codeGenerated') })
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleTestConnection() {
    setBusy(true)
    try {
      const { data } = await testXmaxRealtimeConnection()
      if (typeof data.current_balance === 'number') setLiveBalance(data.current_balance)
      setFeedback({
        error: !data.success,
        text: `${data.success ? '✓' : `HTTP ${data.status_code || 'ERR'}`} · ${data.latency_ms} ms · ${data.message}`,
      })
      await load()
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  async function handleEmergencyStop() {
    setBusy(true)
    try {
      const { data } = await emergencyStopXmaxRealtime()
      setFeedback({
        error: false,
        text: t('realtimeSettings.emergencyDone', {
          canceled: data.canceled_reserved,
          signaled: data.signaled_active,
        }),
      })
      await load()
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally {
      setBusy(false)
    }
  }

  const maxSessionCents = Math.max(1, Math.ceil((watchedMaxSec * watchedCpm) / 60))
  const maxSessionCredits = Math.ceil(watchedMaxSec * watchedCreditsPs)
  const presetOptions = (XMAX_CAMERA_OPTIONS[watchedModel] || XMAX_CAMERA_OPTIONS['x2.1']).map((p) => ({
    value: p,
    label: p,
  }))

  return (
    <Card
      title={
        <StatusTags
          title={t('realtimeSettings.xmaxTitle')}
          config={config}
          extraTag={
            liveBalance !== null ? (
              <Tag color="purple">{t('realtimeSettings.xmaxBalanceTag', { balance: liveBalance })}</Tag>
            ) : undefined
          }
        />
      }
      extra={
        <Space wrap>
          <Button
            icon={<CloudDownloadOutlined />}
            loading={fetchingOfficial}
            onClick={() => {
              void runFetchOfficial('xmax', form, setFetchingOfficial, setOfficialNotice, setFeedback, setLiveBalance)
            }}
          >
            {t('realtimeSettings.fetchOfficial')}
          </Button>
          <Button icon={<MonitorOutlined />} onClick={() => navigate('/realtime-tryon?provider=xmax')}>
            {t('realtimeSettings.openMonitor')}
          </Button>
          <Popconfirm title={t('realtimeSettings.xmaxEmergencyConfirm')} onConfirm={() => { void handleEmergencyStop() }}>
            <Button danger icon={<StopOutlined />} loading={busy}>
              {t('realtimeSettings.emergencyStop')}
            </Button>
          </Popconfirm>
        </Space>
      }
    >
      <SharedAlerts
        helpText={t('realtimeSettings.xmaxHelp')}
        blockers={config?.blocking_reasons || []}
        blockerPrefix="realtimeSettings.xmaxBlockers"
        generatedCode={generatedCode}
        onCloseGeneratedCode={() => setGeneratedCode(null)}
        officialNotice={officialNotice}
        onCloseOfficialNotice={() => setOfficialNotice(null)}
        feedback={feedback}
      />

      <Spin spinning={loading}>
        <Form form={form} initialValues={XMAX_DEFAULTS} layout="vertical" style={{ maxWidth: 860 }}>
          <Row gutter={16} align="middle">
            <Col xs={24} sm={8}>
              <Form.Item name="enabled" label={t('realtimeSettings.xmaxEnabled')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="environment" label={t('realtimeSettings.xmaxEnvironment')}>
                <Select
                  onChange={(env: 'global' | 'china') => {
                    form.setFieldValue(
                      'base_url',
                      env === 'china' ? 'https://cloud.xmax.22duck.cn/open/api/v1' : 'https://api.xmax.ai/open/api/v1',
                    )
                  }}
                  options={[
                    { value: 'global', label: 'Global (api.xmax.ai)' },
                    { value: 'china', label: 'China (cloud.xmax.22duck.cn)' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="default_model" label={t('realtimeSettings.xmaxDefaultModel')}>
                <Select
                  onChange={(nextM: 'x2.1' | 'x2.1-flash') => {
                    const presets = XMAX_CAMERA_OPTIONS[nextM] || XMAX_CAMERA_OPTIONS['x2.1']
                    const cur = form.getFieldValue('camera_preset')
                    if (!presets.includes(cur)) {
                      form.setFieldValue('camera_preset', presets[0])
                    }
                  }}
                  options={[
                    { value: 'x2.1', label: 'X2.1 (1080p Agora)' },
                    { value: 'x2.1-flash', label: 'X2.1 Flash (720p Agora)' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} sm={10}>
              <Form.Item name="allowed_models" label={t('realtimeSettings.xmaxAllowedModels')}>
                <Select
                  mode="multiple"
                  options={[
                    { value: 'x2.1', label: 'x2.1 (1080p)' },
                    { value: 'x2.1-flash', label: 'x2.1-flash (720p)' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col xs={24} sm={7}>
              <Form.Item name="camera_preset" label={t('realtimeSettings.xmaxCameraPreset')}>
                <Select options={presetOptions} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={7}>
              <Form.Item name="face_restoration" label={t('realtimeSettings.xmaxFaceRestoration')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="base_url" label={t('realtimeSettings.xmaxBaseUrl')}>
            <Input placeholder="https://api.xmax.ai/open/api/v1" />
          </Form.Item>

          <Row gutter={16}>
            <Col xs={24} md={14}>
              <Form.Item
                name="api_key"
                label={t('realtimeSettings.xmaxApiKey')}
                extra={t(config?.has_api_key ? 'realtimeSettings.keySavedHint' : 'realtimeSettings.keyMissing')}
              >
                <Input.Password
                  autoComplete="new-password"
                  placeholder={t(config?.has_api_key ? 'realtimeSettings.keySavedHint' : 'realtimeSettings.xmaxKeyPlaceholder')}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={10} style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, paddingTop: 6 }}>
              <Button
                icon={<ApiOutlined />}
                loading={busy}
                disabled={loading || !config?.has_api_key}
                onClick={() => { void handleTestConnection() }}
              >
                {t('realtimeSettings.xmaxTest')}
              </Button>
              <Popconfirm title={t('realtimeSettings.xmaxClearKeyConfirm')} onConfirm={() => { void save({ clearApiKey: true }) }}>
                <Button danger disabled={busy || !config?.has_api_key}>
                  {t('realtimeSettings.clearKey')}
                </Button>
              </Popconfirm>
            </Col>
          </Row>

          <AccessCodeAndOriginSection
            watchedRequireCode={watchedRequireCode}
            config={config}
            busy={busy}
            onGenerateCode={() => { void handleGenerateCode() }}
            onClearCode={() => { void save({ clearAccessCode: true }) }}
          />

          <Divider>{t('realtimeSettings.budgetSection')}</Divider>

          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item name="credits_per_second" label={t('realtimeSettings.xmaxCreditsPerSecond')} rules={[{ required: true }]}>
                <InputNumber min={1} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="cents_per_minute"
                label={t('realtimeSettings.xmaxCentsPerMinute')}
                extra={`${formatUsd(watchedCpm)}/min`}
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={10000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="min_account_credits" label={t('realtimeSettings.xmaxMinAccountCredits')} rules={[{ required: true }]}>
                <InputNumber min={0} max={10000000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item name="min_seconds" label={t('realtimeSettings.xmaxMinSeconds')} rules={[{ required: true }]}>
                <InputNumber min={10} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item
                name="max_seconds"
                label={t('realtimeSettings.maxSeconds')}
                extra={`${t('realtimeSettings.maxSessionCost')}: ${maxSessionCredits} cr / ${formatUsd(maxSessionCents)}`}
                rules={[{ required: true }]}
              >
                <InputNumber min={watchedMinSec} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="default_seconds" label={t('realtimeSettings.defaultSeconds')} rules={[{ required: true }]}>
                <InputNumber min={watchedMinSec} max={watchedMaxSec} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <SharedBudgetLimitsAndPrompt
            watchedDaily={watchedDaily}
            watchedMonthly={watchedMonthly}
            watchedVisitor={watchedVisitor}
            maxCostText={`${formatUsd(maxSessionCents)} (${maxSessionCredits} cr)`}
            visitorMaxSessions={Math.floor(watchedVisitor / maxSessionCents)}
            dailyMaxSessions={Math.floor(watchedDaily / maxSessionCents)}
            monthlyMaxSessions={Math.floor(watchedMonthly / maxSessionCents)}
          />

          <Space wrap>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={busy} disabled={loading} onClick={() => { void save() }}>
              {t('actions.save')}
            </Button>
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => { void load() }}>
              {t('actions.refresh')}
            </Button>
          </Space>

          <Typography.Paragraph type="secondary" style={{ marginTop: 14, marginBottom: 6 }}>
            {t('realtimeSettings.xmaxTestHelp')}
          </Typography.Paragraph>
          <Typography.Link href="https://platform.xmax.ai/docs/capabilities/realtime-video" target="_blank" rel="noopener noreferrer">
            {t('realtimeSettings.xmaxDocs')}
          </Typography.Link>
        </Form>
      </Spin>
    </Card>
  )
}

export default function RealtimeSettingsTab() {
  const { t } = useTranslation('common')
  const [engine, setEngine] = useState<RealtimeProviderKey>('decart')

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div className="mobile-scroll-x">
        <Segmented
          value={engine}
          onChange={(value) => setEngine(value as RealtimeProviderKey)}
          options={[
            { label: t('realtimeSettings.engineDecart'), value: 'decart' },
            { label: t('realtimeSettings.engineReactor'), value: 'reactor' },
            { label: t('realtimeSettings.engineXmax'), value: 'xmax' },
          ]}
        />
      </div>
      {engine === 'decart' ? (
        <DecartSettingsPanel />
      ) : engine === 'reactor' ? (
        <ReactorSettingsPanel />
      ) : (
        <XmaxSettingsPanel />
      )}
    </Space>
  )
}
