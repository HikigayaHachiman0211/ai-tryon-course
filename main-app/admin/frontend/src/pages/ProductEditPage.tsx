import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Form, Input, InputNumber, Select, Button, Space, message, Upload, Image, Typography, Tag } from 'antd'
import { UploadOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { getProduct, createProduct, updateProduct, uploadImage } from '../api/products'

const { Title } = Typography
const { Option } = Select
const { TextArea } = Input

const STYLE_TYPES = ['户外运动', '商务通勤', '日常休闲', '时尚潮流', '轻薄便携', '极寒防护', '亲子家庭']
const COLORS = ['黑色', '白色', '灰色', '深蓝', '浅蓝', '红色', '绿色', '棕色', '卡其', '粉色', '紫色', '橙色', '黄色', '米色', '银色', '金色', '酒红']

export default function ProductEditPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const isNew = id === 'new'

  useEffect(() => {
    if (!isNew && id) {
      getProduct(Number(id)).then((res) => {
        form.setFieldsValue(res.data)
        setImageUrl(res.data.image_url)
      })
    }
  }, [id])

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true)
    try {
      if (isNew) {
        await createProduct(values)
        message.success('创建成功')
      } else {
        await updateProduct(Number(id), values)
        message.success('更新成功')
      }
      navigate('/products')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (file: File) => {
    try {
      const res = await uploadImage(file)
      form.setFieldValue('image_path', res.data.image_path)
      setImageUrl(res.data.image_url)
      message.success('图片上传成功')
    } catch {
      message.error('图片上传失败')
    }
    return false
  }

  return (
    <div style={{ maxWidth: 800 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/products')}>返回</Button>
        <Title level={4} style={{ margin: 0 }}>{isNew ? '新增商品' : '编辑商品'}</Title>
      </Space>

      <Card>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item name="title" label="商品标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>

          <Form.Item label="商品图片">
            <Space>
              {imageUrl && <Image src={imageUrl} width={120} style={{ borderRadius: 8 }} />}
              <Upload
                beforeUpload={handleUpload}
                showUploadList={false}
                accept="image/*"
              >
                <Button icon={<UploadOutlined />}>上传图片</Button>
              </Upload>
            </Space>
          </Form.Item>

          <Form.Item name="image_path" label="图片路径" rules={[{ required: true }]}>
            <Input />
          </Form.Item>

          <Form.Item name="price" label="价格" rules={[{ required: true }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} prefix="¥" />
          </Form.Item>

          <Form.Item name="style_type" label="款式类型">
            <Select allowClear>
              {STYLE_TYPES.map((s) => <Option key={s} value={s}>{s}</Option>)}
            </Select>
          </Form.Item>

          <Form.Item name="color_family" label="颜色色系">
            <Select allowClear>
              {COLORS.map((c) => <Option key={c} value={c}>{c}</Option>)}
            </Select>
          </Form.Item>

          <Form.Item name="body_fit" label="版型与身材适配度">
            <Input />
          </Form.Item>

          <Form.Item name="product_url" label="商品链接">
            <Input placeholder="https://..." />
          </Form.Item>

          <Form.Item name="size_notes" label="尺码说明">
            <TextArea rows={3} />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                {isNew ? '创建' : '保存'}
              </Button>
              <Button onClick={() => navigate('/products')}>取消</Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
