import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Alert, Card, Form, Input, Button, Modal, Radio, Space, message, Typography } from 'antd'
import { UserOutlined, LockOutlined, KeyOutlined, SafetyOutlined } from '@ant-design/icons'
import {
  getRecoveryOptions,
  login,
  resetPassword,
  type RecoveryMethod,
  type RecoveryOptionsResponse,
} from '../api/auth'
import { useTranslation } from 'react-i18next'
import LanguageSwitcher from '../i18n/LanguageSwitcher'

const { Title, Text } = Typography

function extractErrorMessage(e: unknown, fallback: string): string {
  const err = e as { response?: { data?: { detail?: unknown; message?: unknown } } }
  const detail = err.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  const msg = err.response?.data?.message
  if (typeof msg === 'string' && msg.trim()) return msg
  return fallback
}

export default function LoginPage() {
  const { t } = useTranslation('common')
  const [loginForm] = Form.useForm()
  const [forgotForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [loginError, setLoginError] = useState<string | null>(null)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [resetLoading, setResetLoading] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const [optionsLoading, setOptionsLoading] = useState(false)
  const [recoveryOptions, setRecoveryOptions] = useState<RecoveryOptionsResponse | null>(null)
  const selectedMethod = (Form.useWatch('method', forgotForm) as RecoveryMethod | undefined) || 'recovery_key'
  const navigate = useNavigate()
  const location = useLocation()

  const loadRecoveryOptions = async (username: string) => {
    const clean = (username || 'admin').trim() || 'admin'
    setOptionsLoading(true)
    try {
      const res = await getRecoveryOptions(clean)
      setRecoveryOptions(res.data)
      const nextMethod: RecoveryMethod = res.data.has_security_question ? 'security_question' : 'recovery_key'
      forgotForm.setFieldValue('method', nextMethod)
    } catch {
      setRecoveryOptions(null)
    } finally {
      setOptionsLoading(false)
    }
  }

  const openForgotModal = () => {
    const initialUsername = (loginForm.getFieldValue('username') as string | undefined)?.trim() || 'admin'
    setResetError(null)
    forgotForm.resetFields()
    forgotForm.setFieldsValue({ username: initialUsername, method: 'recovery_key' })
    setForgotOpen(true)
    void loadRecoveryOptions(initialUsername)
  }

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    setLoginError(null)
    try {
      const res = await login(values.username, values.password)
      localStorage.setItem('admin_token', res.data.access_token)
      message.success(t('auth.loginSuccess'))
      const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/'
      navigate(from)
    } catch (e: unknown) {
      const errMsg = extractErrorMessage(e, t('auth.loginFailed'))
      setLoginError(errMsg)
      message.error(errMsg)
    } finally {
      setLoading(false)
    }
  }

  const onResetFinish = async (values: {
    username: string
    method: RecoveryMethod
    proof: string
    new_password: string
  }) => {
    setResetLoading(true)
    setResetError(null)
    try {
      await resetPassword({
        username: values.username.trim(),
        method: values.method,
        proof: values.proof,
        new_password: values.new_password,
      })
      message.success(t('auth.resetSuccess'))
      loginForm.setFieldsValue({ username: values.username.trim(), password: '' })
      setLoginError(null)
      setForgotOpen(false)
    } catch (e: unknown) {
      const errMsg = extractErrorMessage(e, t('auth.resetFailed'))
      setResetError(errMsg)
      message.error(errMsg)
    } finally {
      setResetLoading(false)
    }
  }

  const neitherRecoveryAvailable = Boolean(
    recoveryOptions && !recoveryOptions.has_security_question && !recoveryOptions.has_recovery_key,
  )

  return (
    <div className="admin-login-shell">
      <Card className="admin-login-card">
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={3} style={{ marginBottom: 4 }}>
            {t('app.brand')}
          </Title>
          <Text type="secondary">{t('auth.loginTitle')}</Text>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}><LanguageSwitcher /></div>
        {loginError && (
          <Alert
            type="error"
            showIcon
            message={loginError}
            style={{ marginBottom: 16 }}
          />
        )}
        <Form form={loginForm} onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: t('auth.requiredUsername') }]}>
            <Input prefix={<UserOutlined />} placeholder={t('auth.username')} />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: t('auth.requiredPassword') }]}>
            <Input.Password prefix={<LockOutlined />} placeholder={t('auth.password')} />
          </Form.Item>
          <Form.Item style={{ marginBottom: 8 }}>
            <Button type="primary" htmlType="submit" loading={loading} block>
              {t('auth.login')}
            </Button>
          </Form.Item>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button type="link" size="small" onClick={openForgotModal} style={{ paddingRight: 0 }}>
              {t('auth.forgotPassword')}
            </Button>
          </div>
        </Form>
      </Card>

      <Modal
        title={t('auth.forgotTitle')}
        open={forgotOpen}
        onCancel={() => setForgotOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Form
          form={forgotForm}
          layout="vertical"
          onFinish={onResetFinish}
          initialValues={{ username: 'admin', method: 'recovery_key' }}
        >
          {resetError && (
            <Alert type="error" showIcon message={resetError} style={{ marginBottom: 16 }} />
          )}
          <Form.Item
            name="username"
            label={t('auth.username')}
            rules={[{ required: true, message: t('auth.requiredUsername') }]}
          >
            <Input
              prefix={<UserOutlined />}
              onBlur={(e) => { void loadRecoveryOptions(e.target.value) }}
            />
          </Form.Item>

          <Form.Item name="method" label={t('auth.forgotMethod')}>
            <Radio.Group
              onChange={() => {
                setResetError(null)
                forgotForm.setFieldValue('proof', '')
              }}
              disabled={optionsLoading}
            >
              <Space direction="vertical">
                <Radio
                  value="security_question"
                  disabled={Boolean(recoveryOptions && !recoveryOptions.has_security_question)}
                >
                  {t('auth.methodSecurityQuestion')}
                </Radio>
                <Radio
                  value="recovery_key"
                  disabled={Boolean(recoveryOptions && !recoveryOptions.has_recovery_key)}
                >
                  {t('auth.methodRecoveryKey')}
                </Radio>
              </Space>
            </Radio.Group>
          </Form.Item>

          {neitherRecoveryAvailable ? (
            <Alert type="warning" showIcon message={t('auth.noRecoveryMethod')} style={{ marginBottom: 16 }} />
          ) : selectedMethod === 'security_question' ? (
            recoveryOptions?.security_question ? (
              <Alert
                type="info"
                showIcon
                message={`${t('auth.securityQuestionLabel')}: ${recoveryOptions.security_question}`}
                style={{ marginBottom: 16 }}
              />
            ) : (
              <Alert type="info" showIcon message={t('auth.noSecurityQuestionHint')} style={{ marginBottom: 16 }} />
            )
          ) : (
            <Alert type="info" showIcon message={t('auth.recoveryKeyHint')} style={{ marginBottom: 16 }} />
          )}

          <Form.Item
            name="proof"
            label={selectedMethod === 'security_question' ? t('auth.securityAnswer') : t('auth.recoveryKey')}
            rules={[
              {
                required: true,
                message: selectedMethod === 'security_question'
                  ? t('auth.securityAnswerRequired')
                  : t('auth.recoveryKeyRequired'),
              },
            ]}
          >
            <Input.Password
              prefix={selectedMethod === 'security_question' ? <SafetyOutlined /> : <KeyOutlined />}
              placeholder={selectedMethod === 'security_question' ? t('auth.securityAnswer') : t('auth.recoveryKey')}
            />
          </Form.Item>

          <Form.Item
            name="new_password"
            label={t('auth.newPassword')}
            rules={[{ required: true, min: 6, message: t('auth.passwordMin') }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('auth.newPassword')} />
          </Form.Item>

          <Form.Item
            name="confirm_password"
            label={t('auth.confirmPassword')}
            dependencies={['new_password']}
            rules={[
              { required: true, message: t('auth.confirmPassword') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error(t('auth.passwordMismatch')))
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('auth.confirmPassword')} />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setForgotOpen(false)}>{t('actions.cancel')}</Button>
              <Button type="primary" htmlType="submit" loading={resetLoading} disabled={neitherRecoveryAvailable}>
                {t('auth.resetSubmit')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
