import { useState, useEffect } from 'react'
import { Row, Col, Card, Descriptions, Tag, Spin, Typography, Table, Alert } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, InfoCircleOutlined } from '@ant-design/icons'
import { getHealth, getErrors, getConfig, getDbStats } from '../api/system'

const { Title, Text } = Typography

export default function SystemPage() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null)
  const [errors, setErrors] = useState<Record<string, unknown>[]>([])
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [dbStats, setDbStats] = useState<Record<string, number> | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getHealth().catch(() => ({ data: { status: 'unreachable' } })),
      getErrors().catch(() => ({ data: [] })),
      getConfig().catch(() => ({ data: {} })),
      getDbStats().catch(() => ({ data: {} })),
    ]).then(([h, e, c, d]) => {
      setHealth(h.data)
      setErrors(Array.isArray(e.data) ? e.data : e.data.errors || [])
      setConfig(c.data)
      setDbStats(d.data)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  const isHealthy = health?.status === 'ok' || health?.status === 'healthy'

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>系统监控</Title>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card title="主站健康状态">
            <Tag color={isHealthy ? 'green' : 'red'} icon={isHealthy ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
              {String(health?.status || 'unknown')}
            </Tag>
            {health?.main_site && typeof health.main_site === 'object' ? (
              <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
                <Descriptions.Item label="URL">{String((health.main_site as Record<string, unknown>)?.url || '-')}</Descriptions.Item>
                <Descriptions.Item label="延迟">{String((health.main_site as Record<string, unknown>)?.latency_ms || '-')} ms</Descriptions.Item>
              </Descriptions>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="数据库统计">
            {dbStats && (
              <Descriptions column={2} size="small">
                {Object.entries(dbStats).map(([k, v]) => (
                  <Descriptions.Item key={k} label={k}>
                    {typeof v === 'object' ? JSON.stringify(v) : String(v ?? '-')}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            )}
          </Card>
        </Col>
      </Row>

      <Card title="运行配置" style={{ marginTop: 16 }}>
        {config && (
          <Descriptions column={2} size="small" bordered>
            {Object.entries(config).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                <Text code>{String(v)}</Text>
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}
      </Card>

      <Card title="最近错误" style={{ marginTop: 16 }}>
        {errors.length === 0 ? (
          <Alert message="暂无错误记录" type="success" showIcon />
        ) : (
          <Table
            rowKey={(_, i) => String(i)}
            dataSource={errors}
            columns={[
              { title: '时间', dataIndex: 'timestamp', width: 180 },
              { title: '类型', dataIndex: 'type', width: 120 },
              { title: '消息', dataIndex: 'message', ellipsis: true },
            ]}
            size="small"
            pagination={{ pageSize: 10 }}
          />
        )}
      </Card>
    </div>
  )
}
