import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Typography, theme } from 'antd'
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
} from '@ant-design/icons'
import type { MenuProps } from 'antd'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const menuItems: MenuProps['items'] = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/products', icon: <ShoppingOutlined />, label: '商品管理' },
  { key: '/history', icon: <HistoryOutlined />, label: '推荐历史' },
  { key: '/system', icon: <MonitorOutlined />, label: '系统监控' },
  { key: '/images', icon: <PictureOutlined />, label: '图片管理' },
  { key: '/tryon-tasks', icon: <ThunderboltOutlined />, label: 'AI 试穿' },
  { key: '/ai-models', icon: <ApiOutlined />, label: 'AI 模型/API' },
  { key: '/prompts', icon: <FileTextOutlined />, label: 'Prompt 管理' },
  { key: '/annotations', icon: <TagsOutlined />, label: '标注中心' },
  { key: '/profiles', icon: <UserOutlined />, label: '用户画像' },
  { key: '/sample-models', icon: <TeamOutlined />, label: '示例模特' },
  { key: '/voice-clones', icon: <SoundOutlined />, label: '声音克隆' },
]

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const { token: themeToken } = theme.useToken()

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
  }

  const handleLogout = () => {
    localStorage.removeItem('admin_token')
    navigate('/login')
  }

  const dropdownItems: MenuProps['items'] = [
    { key: 'settings', icon: <SettingOutlined />, label: '修改密码', onClick: () => navigate('/settings') },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
  ]

  // Determine selected key
  const selectedKey = menuItems?.find(
    (item) => item && 'key' in item && location.pathname.startsWith(item.key as string) && item.key !== '/'
  )?.key as string || '/'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
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
            {collapsed ? 'AI' : 'AI 管理后台'}
          </Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname === '/' ? '/' : selectedKey]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ border: 'none', background: 'transparent' }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: 'rgba(255,255,255,0.72)',
            backdropFilter: 'saturate(180%) blur(20px)',
            borderBottom: '1px solid rgba(0,0,0,0.06)',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            height: 56,
          }}
        >
          <Dropdown menu={{ items: dropdownItems }} placement="bottomRight">
            <Avatar
              icon={<UserOutlined />}
              style={{ backgroundColor: themeToken.colorPrimary, cursor: 'pointer' }}
            />
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
