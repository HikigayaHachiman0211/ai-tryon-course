import { useState, useEffect } from 'react'
import { Card, Row, Col, Image, Button, Upload, Space, Input, Popconfirm, message, Typography, List, Tag, Pagination } from 'antd'
import { UploadOutlined, DeleteOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons'
import { listImages, uploadImage, deleteImage, getOrphans } from '../api/images'

const { Title, Text } = Typography

interface ImageItem {
  name: string
  url: string
  size: number
  updated: string
}

export default function ImagesPage() {
  const [images, setImages] = useState<ImageItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [prefix, setPrefix] = useState('')
  const [orphans, setOrphans] = useState<string[]>([])
  const [orphanModalVisible, setOrphanModalVisible] = useState(false)

  const fetchImages = (p = page) => {
    setLoading(true)
    listImages({ page: p, size: 24, prefix })
      .then((res) => {
        setImages(res.data.items || [])
        setTotal(res.data.total || 0)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchImages(1); setPage(1) }, [prefix])

  const handleUpload = async (file: File) => {
    try {
      await uploadImage(file)
      message.success('上传成功')
      fetchImages()
    } catch {
      message.error('上传失败')
    }
    return false
  }

  const handleDelete = async (name: string) => {
    await deleteImage(name)
    message.success('已删除')
    fetchImages()
  }

  const handleCheckOrphans = async () => {
    const res = await getOrphans()
    setOrphans(res.data.orphans || [])
    setOrphanModalVisible(true)
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>GCS 图片管理</Title>
      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            placeholder="按前缀搜索..."
            prefix={<SearchOutlined />}
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            style={{ width: 250 }}
            allowClear
          />
          <Upload beforeUpload={handleUpload} showUploadList={false} accept="image/*">
            <Button type="primary" icon={<UploadOutlined />}>上传图片</Button>
          </Upload>
          <Button icon={<WarningOutlined />} onClick={handleCheckOrphans}>检查孤儿图片</Button>
        </Space>

        <Row gutter={[12, 12]}>
          {images.map((img) => (
            <Col key={img.name} xs={12} sm={8} md={6} lg={4}>
              <Card
                size="small"
                cover={<Image src={img.url} height={120} style={{ objectFit: 'cover' }} />}
                actions={[
                  <Popconfirm key="del" title="确认删除？" onConfirm={() => handleDelete(img.name)}>
                    <DeleteOutlined />
                  </Popconfirm>,
                ]}
              >
                <Text ellipsis style={{ fontSize: 12 }}>{img.name}</Text>
                <br />
                <Text type="secondary" style={{ fontSize: 11 }}>{(img.size / 1024).toFixed(1)} KB</Text>
              </Card>
            </Col>
          ))}
        </Row>

        <div style={{ marginTop: 16, textAlign: 'right' }}>
          <Pagination
            current={page}
            pageSize={24}
            total={total}
            onChange={(p) => { setPage(p); fetchImages(p) }}
            showTotal={(t) => `共 ${t} 张`}
          />
        </div>
      </Card>

      {orphanModalVisible && (
        <Card title="孤儿图片（无关联商品）" style={{ marginTop: 16 }}>
          {orphans.length === 0 ? (
            <Text>没有孤儿图片</Text>
          ) : (
            <List
              size="small"
              dataSource={orphans}
              renderItem={(name) => (
                <List.Item actions={[
                  <Popconfirm key="del" title="确认删除？" onConfirm={() => handleDelete(name)}>
                    <Button size="small" danger>删除</Button>
                  </Popconfirm>,
                ]}>
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
