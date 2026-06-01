import { useState } from 'react'
import { Card, Form, Input, Button, message, Typography } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { changePassword } from '../api/auth'

const { Title } = Typography

export default function SettingsPage() {
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const onFinish = async (values: { old_password: string; new_password: string; confirm: string }) => {
    if (values.new_password !== values.confirm) {
      message.error('两次密码不一致')
      return
    }
    setLoading(true)
    try {
      await changePassword(values.old_password, values.new_password)
      message.success('密码已修改')
      form.resetFields()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '修改失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 500 }}>
      <Title level={4} style={{ marginBottom: 16 }}>修改密码</Title>
      <Card>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item name="old_password" label="当前密码" rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 6, message: '密码至少 6 位' }]}>
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Form.Item name="confirm" label="确认新密码" rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>修改密码</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
