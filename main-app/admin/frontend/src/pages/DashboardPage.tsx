import { useState, useEffect } from 'react'
import { Row, Col, Card, Statistic, Spin, Typography } from 'antd'
import {
  ShoppingOutlined,
  EyeOutlined,
  RiseOutlined,
  UserOutlined,
  GlobalOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { getOverview, getTrends, getTopPreferences } from '../api/dashboard'
import { useTranslation } from 'react-i18next'

const { Title } = Typography

export default function DashboardPage() {
  const { t } = useTranslation('common')
  const [overview, setOverview] = useState<Record<string, unknown> | null>(null)
  const [trends, setTrends] = useState<Record<string, unknown>[]>([])
  const [prefs, setPrefs] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getOverview().catch(() => ({ data: {} })),
      getTrends().catch(() => ({ data: { trends: [] } })),
      getTopPreferences().catch(() => ({ data: {} })),
    ])
      .then(([o, t, p]) => {
        setOverview(o.data)
        setTrends(t.data.trends || [])
        setPrefs(p.data)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  // Pivot trend data into series by type
  const dateSet = new Set<string>()
  const seriesMap: Record<string, Record<string, number>> = {}
  const seriesMeta: Record<string, { label: string; color: string }> = {
    recommend: { label: t('dashboard.recommend'), color: '#0071e3' },
    'style-lab': { label: t('dashboard.styleLab'), color: '#af52de' },
    main_site: { label: t('dashboard.mainSite'), color: '#34c759' },
    tryon_workbench: { label: t('dashboard.workbench'), color: '#ff9500' },
  }
  for (const t of trends) {
    const date = t.date as string
    const type = t.type as string
    dateSet.add(date)
    if (!seriesMap[type]) seriesMap[type] = {}
    seriesMap[type][date] = (seriesMap[type][date] || 0) + (t.count as number)
  }
  const dates = Array.from(dateSet).sort()
  const seriesKeys = Object.keys(seriesMeta).filter((k) => seriesMap[k])
  const trendSeries = seriesKeys.map((key) => ({
    name: seriesMeta[key].label,
    type: 'line' as const,
    smooth: true,
    data: dates.map((d) => seriesMap[key]?.[d] || 0),
    itemStyle: { color: seriesMeta[key].color },
    areaStyle: { color: seriesMeta[key].color.replace(')', ',0.08)').replace('rgb(', 'rgba(') },
  }))

  const trendOption = {
    tooltip: { trigger: 'axis' as const, confine: true },
    legend: { type: 'scroll' as const, data: trendSeries.map((s) => s.name), top: 0 },
    xAxis: { type: 'category' as const, data: dates },
    yAxis: { type: 'value' as const },
    series: trendSeries,
    grid: { top: 40, right: 16, bottom: 20, left: 16, containLabel: true },
  }

  const colors = (prefs?.top_colors as { color: string; count: number }[]) || []
  const colorOption = {
    tooltip: { trigger: 'item' as const, confine: true },
    series: [
      {
        type: 'pie',
        radius: ['36%', '64%'],
        data: colors.slice(0, 8).map((c) => ({ value: c.count, name: c.color })),
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        label: { overflow: 'truncate' as const },
      },
    ],
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 20, letterSpacing: '-0.02em', fontWeight: 600 }}>{t('dashboard.title')}</Title>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={5}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.products')}
              value={(overview?.total_products as number) || 0}
              prefix={<ShoppingOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={5}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.requestsToday')}
              value={(overview?.today_requests as number) || 0}
              prefix={<EyeOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={5}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.visitsToday')}
              value={(overview?.today_visits as number) || 0}
              prefix={<GlobalOutlined />}
            />
            <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
              {t('dashboard.mainVisits', { count: (overview?.today_visits_main as number) || 0, tryon: (overview?.today_visits_tryon as number) || 0 })}
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={5}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.jdProducts')}
              value={(overview?.jd_products as number) || 0}
              prefix={<RiseOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8} lg={4}>
          <Card className="stat-card">
            <Statistic
              title={t('dashboard.taobaoProducts')}
              value={(overview?.taobao_products as number) || 0}
              prefix={<UserOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title={t('dashboard.trend')}>
            <ReactECharts option={trendOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title={t('dashboard.colors')}>
            <ReactECharts option={colorOption} style={{ height: 300 }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <Card title={t('dashboard.priceDistribution')}>
            <ReactECharts
              option={{
                tooltip: { trigger: 'axis' as const, confine: true },
                xAxis: {
                  type: 'category' as const,
                  data: ((prefs?.price_distribution as { range: string; count: number }[]) || []).map((p) => p.range),
                },
                yAxis: { type: 'value' as const },
                series: [
                  {
                    type: 'bar',
                    data: ((prefs?.price_distribution as { range: string; count: number }[]) || []).map((p) => p.count),
                    itemStyle: { color: '#0071e3', borderRadius: [4, 4, 0, 0] },
                  },
                ],
                grid: { top: 16, right: 16, bottom: 20, left: 16, containLabel: true },
              }}
              style={{ height: 250 }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
