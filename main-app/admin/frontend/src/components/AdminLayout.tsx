import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Typography, theme, Drawer, Button, Grid } from 'antd'
import {
  DashboardOutlined,
  ShoppingOutlined,
  HistoryOutlined,
  MonitorOutlined,
  PictureOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  TagsOutlined,
  UserOutlined,
  TeamOutlined,
  LogoutOutlined,
  SettingOutlined,
  ApiOutlined,
  SoundOutlined,
  VideoCameraOutlined,
  MenuOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { useTranslation } from 'react-i18next'
import LanguageSwitcher from '../i18n/LanguageSwitcher'

const { Header, Sider, Content } = Layout
const { Text } = Typography

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const screens = Grid.useBreakpoint()
  const isMobile = screens.lg === false
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { token: themeToken } = theme.useToken()
  const { t } = useTranslation('common')
  const menuItems: MenuProps['items'] = [
    { key: '/', icon: <DashboardOutlined />, label: t('nav.dashboard') },
    { key: '/products', icon: <ShoppingOutlined />, label: t('nav.products') },
    { key: '/history', icon: <HistoryOutlined />, label: t('nav.history') },
    { key: '/system', icon: <MonitorOutlined />, label: t('nav.system') },
    { key: '/images', icon: <PictureOutlined />, label: t('nav.images') },
    { key: '/tryon-tasks', icon: <ThunderboltOutlined />, label: t('nav.tryon') },
    { key: '/realtime-tryon', icon: <VideoCameraOutlined />, label: t('nav.realtimeTryon') },
    { key: '/ai-models', icon: <ApiOutlined />, label: t('nav.aiModels') },
    { key: '/prompts', icon: <FileTextOutlined />, label: t('nav.prompts') },
    { key: '/annotations', icon: <TagsOutlined />, label: t('nav.annotations') },
    { key: '/profiles', icon: <UserOutlined />, label: t('nav.profiles') },
    { key: '/sample-models', icon: <TeamOutlined />, label: t('nav.samples') },
    { key: '/voice-clones', icon: <SoundOutlined />, label: t('nav.voice') },
  ]

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
    setDrawerOpen(false)
  }

  const handleLogout = () => {
    localStorage.removeItem('admin_token')
    navigate('/login')
  }

  const dropdownItems: MenuProps['items'] = [
    { key: 'settings', icon: <SettingOutlined />, label: t('nav.settings'), onClick: () => navigate('/settings') },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: t('nav.logout'), onClick: handleLogout },
  ]

  // Determine selected key
  const selectedKey = menuItems?.find(
    (item) => item && 'key' in item && location.pathname.startsWith(item.key as string) && item.key !== '/'
  )?.key as string || '/'

  const activeKey = location.pathname === '/' ? '/' : selectedKey
  const navMenu = (
    <Menu
      mode="inline"
      selectedKeys={[activeKey]}
      items={menuItems}
      onClick={handleMenuClick}
      style={{ border: 'none', background: 'transparent' }}
    />
  )

  return (
    <Layout style={{ minHeight: '100dvh' }}>
      {!isMobile ? (
        <Sider className="admin-sider"
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          width={240}
          style={{
            background: 'rgba(255,255,255,0.72)',
            backdropFilter: 'saturate(180%) blur(20px)',
            borderRight: '1px solid rgba(0,0,0,0.06)',
          }}
        >
          <div style={{ padding: '20px 16px', textAlign: 'center' }}>
            <Text strong style={{ fontSize: collapsed ? 14 : 18, color: '#1d1d1f' }}>
              {collapsed ? t('app.shortName') : t('app.name')}
            </Text>
          </div>
          {navMenu}
        </Sider>
      ) : (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={260}
          className="admin-mobile-drawer"
          title={t('app.name')}
          styles={{ body: { padding: 0 } }}
        >
          {navMenu}
        </Drawer>
      )}
      <Layout style={{ minWidth: 0 }}>
        <Header className="admin-header"
          style={{
            background: 'rgba(255,255,255,0.72)',
            backdropFilter: 'saturate(180%) blur(20px)',
            borderBottom: '1px solid rgba(0,0,0,0.06)',
            padding: isMobile
              ? 'env(safe-area-inset-top) max(12px, env(safe-area-inset-right)) 0 max(8px, env(safe-area-inset-left))'
              : '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: isMobile ? 'space-between' : 'flex-end',
            gap: 8,
            minHeight: 56,
            height: 'auto',
          }}
        >
          {isMobile && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
              <Button
                type="text"
                aria-label="Menu"
                icon={<MenuOutlined />}
                onClick={() => setDrawerOpen(true)}
                style={{ width: 44, height: 44, flexShrink: 0 }}
              />
              <Text strong ellipsis style={{ fontSize: 16, color: '#1d1d1f' }}>
                {t('app.shortName')}
              </Text>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 8 : 16, flexShrink: 0 }}>
            <LanguageSwitcher />
            <Dropdown menu={{ items: dropdownItems }} placement="bottomRight" trigger={['click']}>
              <Button
                type="text"
                aria-label={t('nav.settings')}
                style={{ height: 44, paddingInline: 6, display: 'inline-flex', alignItems: 'center' }}
              >
                <Avatar
                  icon={<UserOutlined />}
                  style={{ backgroundColor: themeToken.colorPrimary }}
                />
              </Button>
            </Dropdown>
          </div>
        </Header>
        <Content
          style={{
            padding: isMobile ? '12px 12px max(20px, env(safe-area-inset-bottom))' : 24,
            overflow: 'auto',
            minWidth: 0,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
