import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Grid,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  ReloadOutlined,
  SettingOutlined,
  StopOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import ReactECharts from 'echarts-for-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  emergencyStopRealtime,
  forceStopRealtimeSession,
  getReactorAccountBalance,
  getRealtimeOverview,
  getXmaxAccountBalance,
  listRealtimeSessions,
  reconcileRealtimeSession,
  syncRealtimeSessionUsage,
  type ReactorAccountBalance,
  type RealtimeOverview,
  type RealtimeProviderScope,
  type RealtimeSessionItem,
  type RealtimeVisitorUsage,
  type XmaxAccountBalance,
} from '../api/realtimeTryon'

const { Title, Text } = Typography
const AUTO_REFRESH_MS = 15000

function formatUsd(cents?: number | null) {
  const num = Number(cents ?? 0)
  return `$${(num / 100).toFixed(2)}`
}

function errorText(error: unknown) {
  const failure = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
  return failure.response?.data?.detail || failure.response?.data?.message || failure.message || String(error)
}

function initialProviderScope(): RealtimeProviderScope {
  if (typeof window === 'undefined') return 'all'
  const raw = new URLSearchParams(window.location.search).get('provider')
  return raw === 'decart' || raw === 'xmax' || raw === 'reactor' ? raw : 'all'
}

export default function RealtimeTryonPage() {
  const { t } = useTranslation('common')
  const screens = Grid.useBreakpoint()
  const isMobile = screens.md === false
  const navigate = useNavigate()
  const [providerScope, setProviderScope] = useState<RealtimeProviderScope>(initialProviderScope)
  const [overview, setOverview] = useState<RealtimeOverview | null>(null)
  const [sessions, setSessions] = useState<RealtimeSessionItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [stateFilter, setStateFilter] = useState<'all' | 'active' | 'reserved' | 'claimed' | 'ended'>('all')
  const [dayFilter, setDayFilter] = useState('')
  const [searchFilter, setSearchFilter] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [loading, setLoading] = useState(true)
  const [actionBusy, setActionBusy] = useState(false)
  const [balanceBusy, setBalanceBusy] = useState(false)
  const [reactorBalanceBusy, setReactorBalanceBusy] = useState(false)
  const [xmaxBalance, setXmaxBalance] = useState<XmaxAccountBalance | null>(null)
  const [reactorBalance, setReactorBalance] = useState<ReactorAccountBalance | null>(null)
  const [detailRow, setDetailRow] = useState<RealtimeSessionItem | null>(null)
  const [reconcileRow, setReconcileRow] = useState<RealtimeSessionItem | null>(null)
  const [reconcileForm] = Form.useForm<{
    confirmed_seconds?: number
    confirmed_credits?: number
    provider_session_id?: string
  }>()

  const fetchAll = useCallback(async (targetPage = page) => {
    setLoading(true)
    try {
      const [ovRes, listRes] = await Promise.all([
        getRealtimeOverview(providerScope === 'all' ? undefined : providerScope),
        listRealtimeSessions({
          page: targetPage,
          size: pageSize,
          ...(providerScope !== 'all' ? { provider: providerScope } : {}),
          state: stateFilter,
          budget_day: dayFilter.trim() || undefined,
          search: searchFilter.trim() || undefined,
        }),
      ])
      setOverview(ovRes.data)
      setSessions(listRes.data.items || [])
      setTotal(listRes.data.total || 0)
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setLoading(false)
    }
  }, [dayFilter, page, pageSize, providerScope, searchFilter, stateFilter])

  useEffect(() => {
    void fetchAll(page)
  }, [fetchAll, page])

  useEffect(() => {
    if (!autoRefresh) return
    const timer = setInterval(() => {
      void fetchAll(page)
    }, AUTO_REFRESH_MS)
    return () => clearInterval(timer)
  }, [autoRefresh, fetchAll, page])

  async function handleEmergencyStop() {
    setActionBusy(true)
    try {
      const { data } = await emergencyStopRealtime(providerScope)
      message.success(
        t('realtimeSettings.emergencyDone', {
          canceled: data.canceled_reserved,
          signaled: data.signaled_active,
        }),
      )
      await fetchAll(page)
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setActionBusy(false)
    }
  }

  async function handleForceStop(sessionId: string) {
    setActionBusy(true)
    try {
      await forceStopRealtimeSession(sessionId)
      message.success(t('realtimeMonitor.stopSent'))
      await fetchAll(page)
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setActionBusy(false)
    }
  }

  async function handleSyncUsage(sessionId: string) {
    setActionBusy(true)
    try {
      const { data } = await syncRealtimeSessionUsage(sessionId)
      message.success(
        data.synced ? t('realtimeMonitor.syncSuccess') : t('realtimeMonitor.syncUnconfirmed'),
      )
      await fetchAll(page)
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setActionBusy(false)
    }
  }

  async function handleCheckXmaxBalance() {
    setBalanceBusy(true)
    try {
      const { data } = await getXmaxAccountBalance()
      setXmaxBalance(data)
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setBalanceBusy(false)
    }
  }

  async function handleCheckReactorBalance() {
    setReactorBalanceBusy(true)
    try {
      const { data } = await getReactorAccountBalance()
      setReactorBalance(data)
    } catch (error) {
      message.error(errorText(error))
    } finally {
      setReactorBalanceBusy(false)
    }
  }

  function openReconcile(row: RealtimeSessionItem) {
    setReconcileRow(row)
    reconcileForm.setFieldsValue({
      confirmed_seconds: row.provider_seconds ?? 0,
      confirmed_credits: row.provider_credits ?? undefined,
      provider_session_id: row.provider_session_id || '',
    })
  }

  async function submitReconcile() {
    if (!reconcileRow) return
    try {
      const values = await reconcileForm.validateFields()
      setActionBusy(true)
      const isSubcent = reconcileRow.provider_key === 'xmax' || reconcileRow.provider_key === 'reactor'
      await reconcileRealtimeSession(reconcileRow.id, {
        ...(isSubcent && values.confirmed_credits !== undefined
          ? { confirmed_credits: values.confirmed_credits }
          : { confirmed_seconds: values.confirmed_seconds }),
        provider_session_id: values.provider_session_id?.trim() || undefined,
      })
      message.success(t('realtimeMonitor.reconcileSaved'))
      setReconcileRow(null)
      await fetchAll(page)
    } catch (error) {
      if ((error as { errorFields?: unknown })?.errorFields) return
      message.error(errorText(error))
    } finally {
      setActionBusy(false)
    }
  }

  const daily = overview?.daily
  const monthly = overview?.monthly
  const cfg = overview?.config
  const decartSnap = overview?.providers?.decart
  const reactorSnap = overview?.providers?.reactor
  const xmaxSnap = overview?.providers?.xmax
  const trend = overview?.trend_14d || []
  const reasons = overview?.reason_distribution || []
  const visitors = overview?.visitors_today || []

  const trendOption = {
    tooltip: { trigger: 'axis' as const, confine: true },
    legend: {
      type: 'scroll' as const,
      data: [
        t('realtimeMonitor.chartConfirmed'),
        t('realtimeMonitor.chartHeld'),
        t('realtimeMonitor.chartSessions'),
      ],
      top: 0,
    },
    xAxis: { type: 'category' as const, data: trend.map((d) => d.date.slice(5)) },
    yAxis: [
      { type: 'value' as const, name: 'USD' },
      { type: 'value' as const, name: t('realtimeMonitor.chartSessions'), minInterval: 1 },
    ],
    series: [
      {
        name: t('realtimeMonitor.chartConfirmed'),
        type: 'bar',
        stack: 'spend',
        data: trend.map((d) => Number((d.confirmed_cents / 100).toFixed(2))),
        itemStyle: { color: '#34c759' },
      },
      {
        name: t('realtimeMonitor.chartHeld'),
        type: 'bar',
        stack: 'spend',
        data: trend.map((d) => Number((Math.max(0, d.accounted_cents - d.confirmed_cents) / 100).toFixed(2))),
        itemStyle: { color: '#ff9500' },
      },
      {
        name: t('realtimeMonitor.chartSessions'),
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: trend.map((d) => d.sessions),
        itemStyle: { color: '#0071e3' },
      },
    ],
    grid: { top: 44, right: 16, bottom: 16, left: 16, containLabel: true },
  }

  const reasonOption = {
    tooltip: { trigger: 'item' as const, confine: true },
    series: [
      {
        type: 'pie',
        radius: ['34%', '62%'],
        data: reasons.map((r) => ({ value: r.count, name: r.reason })),
        label: { overflow: 'truncate' as const },
      },
    ],
  }

  const columns: ColumnsType<RealtimeSessionItem> = [
    {
      title: t('realtimeMonitor.colTicket'),
      dataIndex: 'id',
      width: 135,
      render: (id: string) => <Text copyable={{ text: id }} code>{id.slice(0, 10)}…</Text>,
    },
    {
      title: t('realtimeMonitor.colEngine'),
      width: 175,
      render: (_, row) => {
        if (row.provider_key === 'reactor') {
          return (
            <Tag color="cyan">
              {`Reactor · ${row.model_id === 'xmax/x2' ? 'X2.0' : 'X2.1'}`}
            </Tag>
          )
        }
        const isXmax = row.provider_key === 'xmax'
        return (
          <Tag color={isXmax ? 'purple' : 'geekblue'}>
            {isXmax ? `Xmax · ${row.model_id || 'x2.1'}` : `Decart · ${row.model_id || 'lucy-vton-3.6'}`}
          </Tag>
        )
      },
    },
    {
      title: t('realtimeMonitor.colState'),
      dataIndex: 'state',
      width: 105,
      render: (state: string, row) => {
        const color = state === 'claimed' ? 'processing' : state === 'reserved' ? 'blue' : 'default'
        return (
          <Space size={4}>
            <Tag color={color}>{state}</Tag>
            {row.stop_requested && row.is_active && <Tag color="red">stopping</Tag>}
          </Space>
        )
      },
    },
    {
      title: t('realtimeMonitor.colVisitor'),
      dataIndex: 'visitor_short',
      width: 108,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: t('realtimeMonitor.colLimit'),
      width: 145,
      render: (_, row) =>
        row.provider_key === 'xmax' || row.provider_key === 'reactor'
          ? `${row.limit_seconds}s / ${row.max_credits ?? row.limit_seconds * (row.provider_key === 'reactor' ? 17 : 1)}cr · ${formatUsd(row.cents_per_minute ?? (row.provider_key === 'reactor' ? 11 : 10))}/m`
          : `${row.limit_seconds}s · ${formatUsd(row.cents_per_second)}/s`,
    },
    {
      title: t('realtimeMonitor.colConfirmedSec'),
      dataIndex: 'provider_seconds',
      width: 145,
      render: (sec: number | null, row) => {
        if ((row.provider_key === 'xmax' || row.provider_key === 'reactor') && row.provider_credits != null) {
          return `${row.provider_credits} cr${sec != null ? ` (~${sec.toFixed(1)}s)` : ''}`
        }
        return sec != null ? `${sec.toFixed(1)}s` : '-'
      },
    },
    {
      title: t('realtimeMonitor.colAccounted'),
      dataIndex: 'accounted_cents',
      width: 130,
      render: (cents: number, row) => {
        const confirmed = row.provider_seconds != null || row.provider_credits != null
        const held = !row.is_active && !confirmed && cents > 0
        return (
          <Space size={4}>
            <Text strong>{formatUsd(cents)}</Text>
            {held && <Tag color="warning">{t('realtimeMonitor.heldTag')}</Tag>}
          </Space>
        )
      },
    },
    {
      title: t('realtimeMonitor.colReason'),
      dataIndex: 'reason',
      width: 140,
      render: (reason: string | null) => (reason ? <Tag>{reason}</Tag> : '-'),
    },
    {
      title: t('realtimeMonitor.colProviderSession'),
      dataIndex: 'provider_session_id',
      width: 150,
      ellipsis: true,
      render: (val: string | null, row) => val || row.provider_temp_key_uid || '-',
    },
    {
      title: t('realtimeMonitor.colCreatedAt'),
      dataIndex: 'created_at',
      width: 168,
    },
    {
      title: t('ai.operation'),
      width: 245,
      fixed: isMobile ? undefined : 'right',
      render: (_, row) => (
        <Space size="small">
          <Button size="small" onClick={() => setDetailRow(row)}>
            {t('actions.detail')}
          </Button>
          {row.can_sync_upstream && (
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={actionBusy}
              onClick={() => { void handleSyncUsage(row.id) }}
            >
              {t('realtimeMonitor.syncUsage')}
            </Button>
          )}
          {row.is_active ? (
            <Popconfirm
              title={t('realtimeMonitor.forceStopConfirm')}
              onConfirm={() => { void handleForceStop(row.id) }}
            >
              <Button size="small" danger loading={actionBusy}>
                {t('realtimeMonitor.forceStop')}
              </Button>
            </Popconfirm>
          ) : (
            <Button size="small" type="link" onClick={() => openReconcile(row)}>
              {t('realtimeMonitor.reconcile')}
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const visitorColumns: ColumnsType<RealtimeVisitorUsage> = [
    { title: t('realtimeMonitor.colVisitor'), dataIndex: 'visitor_short', render: (v: string) => <Text code>{v}</Text> },
    { title: t('realtimeMonitor.colSessions'), dataIndex: 'sessions', width: 80 },
    { title: t('realtimeMonitor.colAccounted'), dataIndex: 'accounted_cents', render: (c: number) => formatUsd(c) },
    { title: t('realtimeMonitor.colRemaining'), dataIndex: 'remaining_cents', render: (c: number) => formatUsd(c) },
  ]

  const isSubcentConfig = cfg && 'cents_per_minute' in cfg
  const isReactorConfig = cfg && cfg.provider_key === 'reactor'
  const rateHeadlineValue = isSubcentConfig
    ? formatUsd(cfg.cents_per_minute ?? (isReactorConfig ? 11 : 10))
    : formatUsd(cfg && 'cents_per_second' in cfg ? cfg.cents_per_second : 2)
  const rateHeadlineSuffix = isSubcentConfig ? '/min' : '/s'

  return (
    <div>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }} wrap>
        <Space direction="vertical" size={2}>
          <Title level={4} style={{ margin: 0 }}>
            <VideoCameraOutlined style={{ marginRight: 8 }} />
            {t('realtimeMonitor.title')}
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('realtimeMonitor.timezoneHint', {
              day: overview?.day || '-',
              reset: overview?.next_daily_reset || '-',
            })}
          </Text>
        </Space>
        <Space wrap>
          <div className="mobile-scroll-x">
            <Segmented
              value={providerScope}
              onChange={(val) => {
                setProviderScope(val as RealtimeProviderScope)
                setPage(1)
              }}
              options={[
                { label: t('realtimeMonitor.scopeAll'), value: 'all' },
                { label: 'Decart Lucy VTON', value: 'decart' },
                { label: 'Reactor (X2.1 / X2.0)', value: 'reactor' },
                { label: 'Xmax X2.1', value: 'xmax' },
              ]}
            />
          </div>
          <Space size={6}>
            <Text type="secondary">{t('realtimeMonitor.autoRefresh')}</Text>
            <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
          </Space>
          <Button icon={<WalletOutlined />} loading={reactorBalanceBusy} onClick={() => { void handleCheckReactorBalance() }}>
            {t('realtimeMonitor.checkReactorBalance')}
          </Button>
          <Button icon={<WalletOutlined />} loading={balanceBusy} onClick={() => { void handleCheckXmaxBalance() }}>
            {t('realtimeMonitor.checkXmaxBalance')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { void fetchAll(page) }} loading={loading}>
            {t('actions.refresh')}
          </Button>
          <Button icon={<SettingOutlined />} onClick={() => navigate('/ai-models?tab=realtime')}>
            {t('realtimeMonitor.openSettings')}
          </Button>
          <Popconfirm title={t('realtimeSettings.emergencyConfirm')} onConfirm={() => { void handleEmergencyStop() }}>
            <Button danger icon={<StopOutlined />} loading={actionBusy}>
              {t('realtimeSettings.emergencyStop')}
            </Button>
          </Popconfirm>
        </Space>
      </Space>

      {reactorBalance && (
        <Alert
          type="info"
          showIcon
          closable
          onClose={() => setReactorBalance(null)}
          style={{ marginBottom: 16 }}
          message={t('realtimeMonitor.reactorBalanceBanner', {
            balance: reactorBalance.balance,
            usd: reactorBalance.balance_usd.toFixed(4),
            accountId: reactorBalance.account_id,
            checkedAt: reactorBalance.checked_at,
          })}
        />
      )}

      {xmaxBalance && (
        <Alert
          type="info"
          showIcon
          closable
          onClose={() => setXmaxBalance(null)}
          style={{ marginBottom: 16 }}
          message={t('realtimeMonitor.xmaxBalanceBanner', {
            balance: xmaxBalance.current_balance,
            consumed24h: xmaxBalance.consumed_24h ?? '-',
            env: xmaxBalance.environment,
            checkedAt: xmaxBalance.checked_at,
          })}
        />
      )}

      {overview?.providers && (
        <Row gutter={[16, 12]} style={{ marginBottom: 16 }}>
          {(['decart', 'reactor', 'xmax'] as const).map((key) => {
            const snap = overview.providers?.[key]
            if (!snap) return null
            const pCfg = snap.config
            const color = key === 'reactor' ? 'cyan' : key === 'xmax' ? 'purple' : 'geekblue'
            const label = key === 'reactor' ? 'Reactor Relay (X2.1 / X2.0)' : key === 'xmax' ? 'Xmax X2.1' : 'Decart Lucy VTON 3.6'
            return (
              <Col xs={24} md={8} key={key}>
                <Card size="small">
                  <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
                    <Space size="small">
                      <Tag color={color}>{label}</Tag>
                      <Tag color={pCfg.ready_to_serve ? 'green' : pCfg.enabled ? 'orange' : 'default'}>
                        {t(pCfg.ready_to_serve ? 'realtimeSettings.readyTag' : pCfg.enabled ? 'realtimeSettings.notReadyTag' : 'status.disabled')}
                      </Tag>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t('realtimeMonitor.engineDaySummary', {
                        spent: formatUsd(snap.daily.accounted_cents),
                        limit: formatUsd(snap.daily.limit_cents),
                        active: snap.active_sessions,
                        max: snap.max_active,
                      })}
                    </Text>
                  </Space>
                </Card>
              </Col>
            )
          })}
        </Row>
      )}

      {cfg && !cfg.ready_to_serve && !(decartSnap?.config.ready_to_serve || reactorSnap?.config.ready_to_serve || xmaxSnap?.config.ready_to_serve) && (
        <Alert
          type={cfg.enabled ? 'warning' : 'info'}
          showIcon
          style={{ marginBottom: 16 }}
          message={t(cfg.enabled ? 'realtimeSettings.blockersTitle' : 'realtimeMonitor.disabledBanner')}
          description={cfg.blocking_reasons.map((code) => t(`realtimeSettings.blockers.${code}`, { defaultValue: code })).join(' · ')}
          action={
            <Button size="small" onClick={() => navigate('/ai-models?tab=realtime')}>
              {t('realtimeMonitor.openSettings')}
            </Button>
          }
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title={t('realtimeMonitor.dailyBudget')}
              value={formatUsd(daily?.accounted_cents)}
              suffix={`/ ${formatUsd(daily?.limit_cents)}`}
              prefix={<DollarOutlined />}
            />
            <Progress percent={Math.min(100, daily?.utilization_pct || 0)} size="small" style={{ marginTop: 8 }} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('realtimeMonitor.confirmedVsHeld', {
                confirmed: formatUsd(daily?.confirmed_cents),
                held: formatUsd(daily?.held_unconfirmed_cents),
                count: daily?.session_count ?? 0,
              })}
            </Text>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title={t('realtimeMonitor.monthlyBudget')}
              value={formatUsd(monthly?.accounted_cents)}
              suffix={`/ ${formatUsd(monthly?.limit_cents)}`}
              prefix={<DollarOutlined />}
            />
            <Progress percent={Math.min(100, monthly?.utilization_pct || 0)} size="small" style={{ marginTop: 8 }} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('realtimeMonitor.confirmedVsHeld', {
                confirmed: formatUsd(monthly?.confirmed_cents),
                held: formatUsd(monthly?.held_unconfirmed_cents),
                count: monthly?.session_count ?? 0,
              })}
            </Text>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title={t('realtimeMonitor.concurrency')}
              value={overview?.active_sessions ?? 0}
              suffix={`/ ${overview?.max_active ?? 1}`}
              prefix={<ThunderboltOutlined />}
            />
            <div style={{ marginTop: 10 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                <ClockCircleOutlined style={{ marginRight: 4 }} />
                {t('realtimeMonitor.startsPerMin', {
                  count: overview?.starts_last_minute ?? 0,
                  limit: overview?.starts_per_minute ?? 3,
                })}
              </Text>
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card className="stat-card">
            <Statistic
              title={t('realtimeMonitor.unitRate')}
              value={rateHeadlineValue}
              suffix={rateHeadlineSuffix}
              prefix={<CheckCircleOutlined />}
            />
            <Space size={6} wrap style={{ marginTop: 10 }}>
              <Tag color={cfg?.ready_to_serve ? 'green' : 'default'}>
                {t(cfg?.ready_to_serve ? 'realtimeSettings.readyTag' : 'realtimeSettings.notReadyTag')}
              </Tag>
              <Tag color={isReactorConfig ? 'cyan' : isSubcentConfig ? 'purple' : 'geekblue'}>
                {isReactorConfig ? 'reactor/xmax-x2-1' : isSubcentConfig ? 'x2.1 · 1080p' : 'lucy-vton-3.6 · 720p'}
              </Tag>
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={14}>
          <Card title={t('realtimeMonitor.trendTitle')}>
            {trend.some((d) => d.sessions > 0) ? (
              <ReactECharts option={trendOption} style={{ height: 240 }} />
            ) : (
              <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>
                {t('empty.noTrend')}
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title={t('realtimeMonitor.reasonsAndVisitors')}>
            {reasons.length > 0 && <ReactECharts option={reasonOption} style={{ height: 150 }} />}
            <Table
              rowKey="visitor_short"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              dataSource={visitors}
              columns={visitorColumns}
              locale={{ emptyText: t('status.noData') }}
            />
          </Card>
        </Col>
      </Row>

      <Card title={t('realtimeMonitor.ledgerTitle')}>
        <Space style={{ marginBottom: 16, width: '100%' }} wrap>
          <Select
            className="admin-toolbar-input"
            value={stateFilter}
            style={{ width: 150 }}
            onChange={(value) => {
              setStateFilter(value)
              setPage(1)
            }}
            options={[
              { value: 'all', label: t('realtimeMonitor.filterAll') },
              { value: 'active', label: t('realtimeMonitor.filterActive') },
              { value: 'reserved', label: 'reserved' },
              { value: 'claimed', label: 'claimed' },
              { value: 'ended', label: t('realtimeMonitor.filterEnded') },
            ]}
          />
          <Input
            className="admin-toolbar-input"
            allowClear
            placeholder={t('realtimeMonitor.dayPlaceholder')}
            value={dayFilter}
            onChange={(e) => {
              setDayFilter(e.target.value)
              setPage(1)
            }}
            style={{ width: 150 }}
          />
          <Button
            onClick={() => {
              if (overview?.day) {
                setDayFilter(overview.day)
                setPage(1)
              }
            }}
          >
            {t('realtimeMonitor.todayOnly')}
          </Button>
          <Input.Search
            className="admin-toolbar-input"
            allowClear
            placeholder={t('realtimeMonitor.searchPlaceholder')}
            value={searchFilter}
            onChange={(e) => {
              setSearchFilter(e.target.value)
              setPage(1)
            }}
            style={{ width: 240 }}
          />
        </Space>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={sessions}
          loading={loading}
          scroll={{ x: 1520 }}
          pagination={{
            current: page,
            pageSize,
            total,
            onChange: (next) => setPage(next),
            showTotal: (count) => t('pagination.total', { count }),
          }}
          size="middle"
        />
      </Card>

      <Modal
        title={t('realtimeMonitor.detailTitle')}
        open={Boolean(detailRow)}
        onCancel={() => setDetailRow(null)}
        footer={null}
        width={620}
      >
        {detailRow && (
          <Descriptions column={1} bordered size="small">
            {Object.entries(detailRow).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {v == null ? '-' : String(v)}
              </Descriptions.Item>
            ))}
          </Descriptions>
        )}
      </Modal>

      <Modal
        title={t('realtimeMonitor.reconcileTitle')}
        open={Boolean(reconcileRow)}
        onCancel={() => setReconcileRow(null)}
        onOk={() => { void submitReconcile() }}
        confirmLoading={actionBusy}
        okText={t('actions.save')}
      >
        {reconcileRow && (
          <Form form={reconcileForm} layout="vertical">
            {reconcileRow.provider_key === 'xmax' || reconcileRow.provider_key === 'reactor' ? (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 14 }}
                  message={t(
                    reconcileRow.provider_key === 'reactor'
                      ? 'realtimeMonitor.reconcileReactorHint'
                      : 'realtimeMonitor.reconcileXmaxHint',
                    {
                      limitSec: reconcileRow.limit_seconds,
                      limitCredits:
                        reconcileRow.max_credits
                        ?? reconcileRow.limit_seconds * (reconcileRow.provider_key === 'reactor' ? 17 : 1),
                      rate: formatUsd(
                        reconcileRow.cents_per_minute
                        ?? (reconcileRow.provider_key === 'reactor' ? 11 : 10),
                      ),
                    },
                  )}
                />
                <Form.Item
                  name="confirmed_credits"
                  label={t('realtimeMonitor.confirmedCreditsInput')}
                >
                  <InputNumber
                    min={0}
                    max={
                      reconcileRow.max_credits
                      ?? reconcileRow.limit_seconds * (reconcileRow.provider_key === 'reactor' ? 17 : 1)
                    }
                    step={1}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
                <Form.Item name="confirmed_seconds" label={t('realtimeMonitor.confirmedSecondsInput')}>
                  <InputNumber min={0} max={reconcileRow.limit_seconds} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
              </>
            ) : (
              <>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 14 }}
                  message={t('realtimeMonitor.reconcileHint', {
                    limit: reconcileRow.limit_seconds,
                    rate: formatUsd(reconcileRow.cents_per_second),
                  })}
                />
                <Form.Item
                  name="confirmed_seconds"
                  label={t('realtimeMonitor.confirmedSecondsInput')}
                  rules={[{ required: true }]}
                >
                  <InputNumber min={0} max={reconcileRow.limit_seconds} step={0.1} style={{ width: '100%' }} />
                </Form.Item>
              </>
            )}
            <Form.Item name="provider_session_id" label={t('realtimeMonitor.colProviderSession')}>
              <Input maxLength={128} placeholder="Provider session ID" />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  )
}
