import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Card,
  Row,
  Col,
  Image,
  Button,
  Upload,
  Space,
  Input,
  Popconfirm,
  message,
  Typography,
  List,
  Tag,
  Pagination,
  Spin,
  Empty,
  Radio,
  Tooltip,
  Alert,
} from 'antd'
import {
  UploadOutlined,
  DeleteOutlined,
  SearchOutlined,
  WarningOutlined,
  ReloadOutlined,
  CopyOutlined,
  CloudServerOutlined,
  FileOutlined,
  LockOutlined,
} from '@ant-design/icons'
import { listImages, uploadImage, deleteImage, getOrphans, type BlobScope } from '../api/images'
import { useTranslation } from 'react-i18next'

const { Title, Text } = Typography

interface ImageItem {
  name: string
  display_name?: string
  url: string
  size: number
  updated?: string | null
  content_type?: string | null
  container?: string
}

interface StorageInfo {
  provider?: string
  account_name?: string
  container?: string
  product_container?: string
  media_container?: string
  public_base_url?: string
}

const IMAGE_EXT_RE = /\.(png|jpe?g|webp|gif|bmp|avif|svg)$/i

const FALLBACK_PREVIEW_SVG =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140" viewBox="0 0 200 140">' +
      '<rect width="200" height="140" fill="#f5f5f7"/>' +
      '<text x="100" y="75" text-anchor="middle" fill="#86868b" font-family="sans-serif" font-size="12">Preview unavailable</text>' +
    '</svg>',
  )

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return '0 KB'
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(2)} MB`
  return `${(size / 1024).toFixed(1)} KB`
}

function formatProviderName(provider?: string): string {
  const normalized = (provider || '').trim().toLowerCase()
  if (normalized === 'azure') return 'Azure Blob Storage'
  if (normalized === 'oss') return 'Alibaba Cloud OSS'
  if (normalized === 'gcs') return 'Google Cloud Storage'
  if (normalized === 'local') return 'Local Object Storage'
  return provider || 'Object Storage'
}

function getFileExtension(name: string): string {
  const clean = name.split('?')[0]
  const dot = clean.lastIndexOf('.')
  return dot >= 0 ? clean.slice(dot + 1).toUpperCase() : 'BLOB'
}

export default function ImagesPage() {
  const { t } = useTranslation('common')
  const [images, setImages] = useState<ImageItem[]>([])
  const [storage, setStorage] = useState<StorageInfo | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [scope, setScope] = useState<BlobScope>('products')
  const [loading, setLoading] = useState(false)
  const [orphansLoading, setOrphansLoading] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [prefix, setPrefix] = useState('')
  const [orphans, setOrphans] = useState<string[]>([])
  const [orphanModalVisible, setOrphanModalVisible] = useState(false)
  const requestSeqRef = useRef(0)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPrefix(searchInput)
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const fetchImages = useCallback(
    (targetPage = page, targetScope = scope, targetPrefix = prefix, forceRefresh = false) => {
      const seq = ++requestSeqRef.current
      setLoading(true)
      listImages({
        page: targetPage,
        size: 24,
        prefix: targetPrefix,
        scope: targetScope,
        ...(forceRefresh ? { refresh: true } : {}),
      })
        .then((res) => {
          if (seq !== requestSeqRef.current) return
          setImages(res.data.items || [])
          setTotal(res.data.total || 0)
          if (res.data.storage) {
            setStorage(res.data.storage)
          }
        })
        .catch(() => {
          if (seq !== requestSeqRef.current) return
          message.error(t('images.loadFailed'))
        })
        .finally(() => {
          if (seq === requestSeqRef.current) {
            setLoading(false)
          }
        })
    },
    [page, prefix, scope, t],
  )

  useEffect(() => {
    fetchImages(page, scope, prefix, false)
  }, [page, scope, prefix, fetchImages])

  const handleScopeChange = (nextScope: BlobScope) => {
    setScope(nextScope)
    setPage(1)
  }

  const handleUpload = async (file: File) => {
    try {
      await uploadImage(file, scope)
      message.success(t('images.uploadSuccess'))
      fetchImages(1, scope, prefix, true)
      setPage(1)
    } catch {
      message.error(t('images.uploadFailed'))
    }
    return false
  }

  const handleDelete = async (name: string, targetScope: BlobScope = scope) => {
    await deleteImage(name, targetScope)
    message.success(t('products.deleted'))
    fetchImages(page, scope, prefix, true)
    if (orphanModalVisible && targetScope === 'products') {
      setOrphans((prev) => prev.filter((item) => item !== name && `羽绒服_png/${item}` !== name))
    }
  }

  const handleCopyUrl = async (url: string) => {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      message.success(t('images.copiedUrl'))
    } catch {
      message.info(url)
    }
  }

  const handleCheckOrphans = async () => {
    setOrphansLoading(true)
    try {
      const res = await getOrphans({ refresh: true })
      setOrphans(res.data.orphans || [])
      if (res.data.storage) {
        setStorage(res.data.storage)
      }
      setOrphanModalVisible(true)
    } finally {
      setOrphansLoading(false)
    }
  }

  const activeContainer =
    storage?.container || (scope === 'media' ? storage?.media_container || 'course-media' : storage?.product_container || 'product-images')

  return (
    <div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div>
          <Title level={4} style={{ margin: '0 0 4px' }}>
            {t('images.title')}
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {t('images.subtitle')}
          </Text>
        </div>

        <Space wrap size={8}>
          <Tag color="blue" icon={<CloudServerOutlined />}>
            {t('images.storageProvider')}: {formatProviderName(storage?.provider)}
          </Tag>
          {storage?.account_name && (
            <Tag color="geekblue">
              {t('images.storageAccount')}: {storage.account_name}
            </Tag>
          )}
          <Tag color={scope === 'media' ? 'gold' : 'cyan'}>
            {t('images.container')}: {activeContainer}
          </Tag>
          <Tag>{t('pagination.images', { count: total })}</Tag>
        </Space>
      </div>

      <Card>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <div className="mobile-scroll-x">
            <Radio.Group
              value={scope}
              onChange={(e) => handleScopeChange(e.target.value as BlobScope)}
              optionType="button"
              buttonStyle="solid"
            >
              <Radio.Button value="products">{t('images.scopeProducts')}</Radio.Button>
              <Radio.Button value="samples">{t('images.scopeSamples')}</Radio.Button>
              <Radio.Button value="media">{t('images.scopeMedia')}</Radio.Button>
            </Radio.Group>
          </div>

          <Space wrap style={{ width: '100%' }}>
            <Input
              className="admin-toolbar-input"
              placeholder={t('images.prefixPlaceholder')}
              prefix={<SearchOutlined />}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onPressEnter={() => {
                setPrefix(searchInput)
                setPage(1)
              }}
              style={{ width: 280 }}
              allowClear
            />
            <Button
              icon={<ReloadOutlined />}
              loading={loading}
              onClick={() => fetchImages(page, scope, prefix, true)}
            >
              {t('actions.refresh')}
            </Button>
            <Upload beforeUpload={handleUpload} showUploadList={false} accept="image/*">
              <Button type="primary" icon={<UploadOutlined />}>
                {t('actions.upload')}
              </Button>
            </Upload>
            <Button icon={<WarningOutlined />} loading={orphansLoading} onClick={handleCheckOrphans}>
              {t('images.checkOrphans')}
            </Button>
          </Space>
        </div>

        {scope === 'media' && (
          <Alert
            type="info"
            showIcon
            icon={<LockOutlined />}
            message={t('images.privateMediaNote')}
            style={{ marginBottom: 16 }}
          />
        )}

        <Spin spinning={loading}>
          {images.length === 0 && !loading ? (
            <Empty description={t('images.emptyImages')} style={{ padding: '48px 0' }} />
          ) : (
            <Row gutter={[14, 14]} style={{ minHeight: 160 }}>
              {images.map((img) => {
                const label = img.display_name || img.name.replace(/^羽绒服_png\//, '')
                const isPublicImage = scope !== 'media' && IMAGE_EXT_RE.test(label) && Boolean(img.url)
                return (
                  <Col key={img.name} xs={12} sm={8} md={6} lg={4}>
                    <Card
                      size="small"
                      hoverable
                      cover={
                        isPublicImage ? (
                          <Image
                            src={img.url}
                            fallback={FALLBACK_PREVIEW_SVG}
                            height={140}
                            style={{ objectFit: 'cover', width: '100%' }}
                          />
                        ) : (
                          <div
                            style={{
                              height: 140,
                              display: 'flex',
                              flexDirection: 'column',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: 6,
                              background: 'rgba(15, 23, 42, 0.04)',
                              color: '#64748b',
                            }}
                          >
                            {scope === 'media' ? (
                              <LockOutlined style={{ fontSize: 26 }} />
                            ) : (
                              <FileOutlined style={{ fontSize: 26 }} />
                            )}
                            <Tag style={{ margin: 0 }}>{getFileExtension(label)}</Tag>
                          </div>
                        )
                      }
                      actions={[
                        <Tooltip key="copy" title={t('images.copyUrl')}>
                          <CopyOutlined onClick={() => handleCopyUrl(img.url)} />
                        </Tooltip>,
                        <Popconfirm
                          key="del"
                          title={t('products.confirmDelete')}
                          onConfirm={() => handleDelete(img.name)}
                        >
                          <DeleteOutlined style={{ color: '#ff4d4f' }} />
                        </Popconfirm>,
                      ]}
                    >
                      <Tooltip title={label}>
                        <Text ellipsis strong style={{ display: 'block', fontSize: 12.5 }}>
                          {label}
                        </Text>
                      </Tooltip>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {formatBytes(img.size)}
                      </Text>
                    </Card>
                  </Col>
                )
              })}
            </Row>
          )}
        </Spin>

        <div style={{ marginTop: 18, textAlign: 'right' }}>
          <Pagination
            current={page}
            pageSize={24}
            total={total}
            showSizeChanger={false}
            onChange={(p) => setPage(p)}
            showTotal={(count) => t('pagination.images', { count })}
          />
        </div>
      </Card>

      {orphanModalVisible && (
        <Card title={t('images.orphanTitle')} style={{ marginTop: 16 }}>
          {orphans.length === 0 ? (
            <Text>{t('empty.noOrphans')}</Text>
          ) : (
            <List
              size="small"
              dataSource={orphans}
              renderItem={(name) => (
                <List.Item
                  actions={[
                    <Popconfirm
                      key="del"
                      title={t('products.confirmDelete')}
                      onConfirm={() => handleDelete(name, 'products')}
                    >
                      <Button size="small" danger>
                        {t('actions.delete')}
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <Tag color="orange">{name}</Tag>
                </List.Item>
              )}
            />
          )}
        </Card>
      )}
    </div>
  )
}
