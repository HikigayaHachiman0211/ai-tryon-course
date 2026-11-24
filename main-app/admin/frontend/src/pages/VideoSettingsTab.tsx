import { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Divider, Form, Input, InputNumber, Popconfirm, Row, Select, Space, Spin, Switch, Tag, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import request from '../utils/request'

interface VideoConfig {
  enabled: boolean
  has_api_key: boolean
  base_url: string
  project_id: string
  timeout_seconds: number
  rate_limit_per_minute: number
  daily_quota_limit: number
  api_key?: string
}

function errorText(error: unknown) {
  const failure = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
  return failure.response?.data?.detail || failure.response?.data?.message || failure.message || String(error)
}

export default function VideoSettingsTab() {
  const { t } = useTranslation('common')
  const [form] = Form.useForm<VideoConfig>()
  const [config, setConfig] = useState<VideoConfig | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [feedback, setFeedback] = useState<{ error: boolean; text: string } | null>(null)

  useEffect(() => {
    let mounted = true
    request.get<VideoConfig>('/api/ai-config/video').then(({ data }) => {
      if (!mounted) return
      setConfig(data)
      form.setFieldsValue({ ...data, api_key: '' })
    }).catch(error => { if (mounted) setFeedback({ error: true, text: errorText(error) }) })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [form])

  async function save(clearKey = false) {
    setBusy(true)
    try {
      const values = await form.validateFields()
      const { api_key: key, ...settings } = values
      const { data } = await request.put<VideoConfig>('/api/ai-config/video', {
        ...settings, project_id: values.project_id?.trim() || '',
        ...(clearKey ? { clear_api_key: true } : key?.trim() ? { api_key: key.trim() } : {}),
      })
      setConfig(data)
      form.setFieldsValue({ ...data, api_key: '' })
      setFeedback({ error: false, text: `${t('actions.save')} ✓` })
    } catch (error) {
      setFeedback({ error: true, text: errorText(error) })
    } finally { setBusy(false) }
  }

  async function check() {
    setBusy(true)
    try {
      const { data } = await request.post<{ success: boolean; latency_ms: number; status_code: number }>('/api/ai-config/video/test')
      setFeedback({ error: !data.success, text: `${data.success ? '✓' : 'HTTP ' + data.status_code} · ${data.latency_ms} ms` })
    } catch (error) { setFeedback({ error: true, text: errorText(error) }) }
    finally { setBusy(false) }
  }

  return (
    <Card
      title={
        <Space size="small" wrap>
          <span>{t('videoSettings.title')}</span>
          <Tag color={config?.enabled ? 'processing' : 'default'}>
            {t(config?.enabled ? 'status.enabled' : 'status.disabled')}
          </Tag>
          <Tag color={config?.has_api_key ? 'success' : 'warning'}>
            {t(config?.has_api_key ? 'videoSettings.keySaved' : 'videoSettings.keyMissing')}
          </Tag>
        </Space>
      }
    >
      <Alert type="info" showIcon message={t('videoSettings.help')} style={{ marginBottom: 20 }} />
      {feedback && (
        <Alert
          type={feedback.error ? 'error' : 'success'}
          showIcon
          message={feedback.text}
          style={{ marginBottom: 16 }}
        />
      )}
      <Spin spinning={loading}>
        <Form form={form} layout="vertical" style={{ maxWidth: 760 }}>
          <Form.Item name="enabled" label={t('videoSettings.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>

          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="base_url" label={t('videoSettings.baseUrl')} rules={[{ required: true }]}>
                <Select options={[
                  { value: 'https://01router.com/api/v1', label: `${t('videoSettings.live')} · https://01router.com/api/v1` },
                  { value: 'https://01router.com/api/sandbox/v1', label: t('videoSettings.sandbox') },
                ]} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name="project_id"
                label={t('videoSettings.project')}
                extra={t('videoSettings.projectHelp')}
                rules={[{ pattern: /^[A-Za-z0-9_-]*$/, max: 160 }]}
              >
                <Input placeholder="project-id" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="api_key"
            label={t('videoSettings.apiKey')}
            extra={<Tag color={config?.has_api_key ? 'success' : 'warning'}>{t(config?.has_api_key ? 'videoSettings.keySaved' : 'videoSettings.keyMissing')}</Tag>}
          >
            <Input.Password autoComplete="new-password" placeholder={t(config?.has_api_key ? 'videoSettings.keySaved' : 'videoSettings.keyMissing')} />
          </Form.Item>

          <Divider style={{ margin: '12px 0 18px' }} />

          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item name="timeout_seconds" label={t('videoSettings.timeout')}>
                <InputNumber min={10} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="rate_limit_per_minute" label={t('videoSettings.rpm')} rules={[{ required: true }]}>
                <InputNumber min={1} max={1000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="daily_quota_limit" label={t('videoSettings.daily')} rules={[{ required: true }]}>
                <InputNumber min={1} max={100000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Typography.Paragraph type="secondary" style={{ marginBottom: 18 }}>
            {t('videoSettings.quotaHelp')}
          </Typography.Paragraph>

          <Space wrap>
            <Button type="primary" loading={busy} disabled={loading} onClick={() => { void save() }}>{t('actions.save')}</Button>
            <Button disabled={busy || loading || !config?.has_api_key} onClick={() => { void check() }}>{t('videoSettings.test')}</Button>
            <Popconfirm title={t('videoSettings.clearKey')} onConfirm={() => save(true)}>
              <Button danger disabled={busy || !config?.has_api_key}>{t('videoSettings.clearKey')}</Button>
            </Popconfirm>
          </Space>

          <Typography.Paragraph type="secondary" style={{ marginTop: 14, marginBottom: 6 }}>
            {t('videoSettings.testHelp')}
          </Typography.Paragraph>
          <Typography.Link href="https://01router.com/docs/agent" target="_blank" rel="noopener noreferrer">
            {t('videoSettings.docs')}
          </Typography.Link>
        </Form>
      </Spin>
    </Card>
  )
}
