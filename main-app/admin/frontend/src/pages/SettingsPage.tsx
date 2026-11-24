import { useEffect, useState } from 'react'
import { Card, Form, Input, Button, Space, Tag, message, Typography } from 'antd'
import { LockOutlined, SafetyOutlined } from '@ant-design/icons'
import { changePassword, getMe, saveRecoveryQuestion } from '../api/auth'
import { useTranslation } from 'react-i18next'

const { Title, Text } = Typography

function extractErrorMessage(e: unknown, fallback: string): string {
  const err = e as { response?: { data?: { detail?: unknown; message?: unknown } } }
  const detail = err.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  const msg = err.response?.data?.message
  if (typeof msg === 'string' && msg.trim()) return msg
  return fallback
}

export default function SettingsPage() {
  const { t } = useTranslation('common')
  const [loading, setLoading] = useState(false)
  const [recoveryLoading, setRecoveryLoading] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState<string | null>(null)
  const [form] = Form.useForm()
  const [recoveryForm] = Form.useForm()

  useEffect(() => {
    void getMe()
      .then((res) => {
        const q = (res.data as { recovery_question?: string | null })?.recovery_question || null
        setCurrentQuestion(q)
        if (q) {
          recoveryForm.setFieldValue('security_question', q)
        }
      })
      .catch(() => {})
  }, [recoveryForm])

  const onFinish = async (values: { old_password: string; new_password: string; confirm: string }) => {
    if (values.new_password !== values.confirm) {
      message.error(t('settings.mismatch'))
      return
    }
    setLoading(true)
    try {
      await changePassword(values.old_password, values.new_password)
      message.success(t('settings.changed'))
      form.resetFields()
    } catch (e: unknown) {
      message.error(extractErrorMessage(e, t('settings.failed')))
    } finally {
      setLoading(false)
    }
  }

  const onRecoveryFinish = async (values: {
    current_password: string
    security_question: string
    security_answer: string
  }) => {
    setRecoveryLoading(true)
    try {
      const res = await saveRecoveryQuestion({
        current_password: values.current_password,
        security_question: values.security_question.trim(),
        security_answer: values.security_answer.trim(),
      })
      const savedQ = (res.data as { security_question?: string })?.security_question || values.security_question.trim()
      setCurrentQuestion(savedQ)
      message.success(t('settings.recoverySaved'))
      recoveryForm.setFieldsValue({ current_password: '', security_answer: '', security_question: savedQ })
    } catch (e: unknown) {
      message.error(extractErrorMessage(e, t('settings.recoverySaveFailed')))
    } finally {
      setRecoveryLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 560 }}>
      <Title level={4} style={{ marginBottom: 16 }}>{t('settings.title')}</Title>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card>
          <Form form={form} layout="vertical" onFinish={onFinish}>
            <Form.Item name="old_password" label={t('settings.current')} rules={[{ required: true }]}>
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>
            <Form.Item name="new_password" label={t('settings.new')} rules={[{ required: true, min: 6, message: t('settings.min') }]}>
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>
            <Form.Item name="confirm" label={t('settings.confirm')} rules={[{ required: true }]}>
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" loading={loading}>{t('settings.change')}</Button>
            </Form.Item>
          </Form>
        </Card>

        <Card title={t('settings.recoveryTitle')}>
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
              {t('settings.recoverySubtitle')}
            </Text>
            {currentQuestion ? (
              <Tag color="green">{`${t('settings.recoveryStatusSet')}: ${currentQuestion}`}</Tag>
            ) : (
              <Tag>{t('settings.recoveryStatusUnset')}</Tag>
            )}
          </div>
          <Form form={recoveryForm} layout="vertical" onFinish={onRecoveryFinish}>
            <Form.Item
              name="current_password"
              label={t('settings.current')}
              rules={[{ required: true, message: t('settings.recoveryRequired') }]}
            >
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>
            <Form.Item
              name="security_question"
              label={t('settings.securityQuestion')}
              rules={[{ required: true, message: t('settings.recoveryRequired') }]}
            >
              <Input prefix={<SafetyOutlined />} placeholder={t('settings.securityQuestionPlaceholder')} />
            </Form.Item>
            <Form.Item
              name="security_answer"
              label={t('settings.securityAnswer')}
              rules={[{ required: true, message: t('settings.recoveryRequired') }]}
            >
              <Input.Password prefix={<SafetyOutlined />} placeholder={t('settings.securityAnswerPlaceholder')} />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" loading={recoveryLoading}>
                {t('settings.saveRecovery')}
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </Space>
    </div>
  )
}
