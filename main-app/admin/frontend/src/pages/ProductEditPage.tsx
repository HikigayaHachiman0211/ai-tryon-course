import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Form, Input, InputNumber, Select, Button, Space, message, Upload, Image, Typography, Tag } from 'antd'
import { UploadOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { getProduct, createProduct, updateProduct, uploadImage } from '../api/products'
import { useTranslation } from 'react-i18next'

const { Title } = Typography
const { Option } = Select
const { TextArea } = Input

const STYLE_TYPES: Array<[string, string]> = [
  ['户外运动', 'options.styles.outdoor'], ['商务通勤', 'options.styles.business'], ['日常休闲', 'options.styles.casual'],
  ['时尚潮流', 'options.styles.fashion'], ['轻薄便携', 'options.styles.light'], ['极寒防护', 'options.styles.cold'], ['亲子家庭', 'options.styles.family'],
]
const COLORS: Array<[string, string]> = [
  ['黑色', 'options.colors.black'], ['白色', 'options.colors.white'], ['灰色', 'options.colors.gray'], ['深蓝', 'options.colors.navy'],
  ['浅蓝', 'options.colors.lightBlue'], ['红色', 'options.colors.red'], ['绿色', 'options.colors.green'], ['棕色', 'options.colors.brown'],
  ['卡其', 'options.colors.khaki'], ['粉色', 'options.colors.pink'], ['紫色', 'options.colors.purple'], ['橙色', 'options.colors.orange'],
  ['黄色', 'options.colors.yellow'], ['米色', 'options.colors.beige'], ['银色', 'options.colors.silver'], ['金色', 'options.colors.gold'], ['酒红', 'options.colors.wine'],
]

export function productFormValues(data: Record<string, unknown>): Record<string, unknown> {
  const canonical = data.canonical && typeof data.canonical === 'object' ? data.canonical : {}
  return { ...data, ...canonical }
}

export default function ProductEditPage() {
  const { t } = useTranslation('common')
  const { id } = useParams()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const isNew = id === 'new'

  useEffect(() => {
    if (!isNew && id) {
      getProduct(Number(id)).then((res) => {
        form.setFieldsValue(productFormValues(res.data))
        setImageUrl(res.data.image_url)
      })
    }
  }, [id])

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true)
    try {
      if (isNew) {
        await createProduct(values)
        message.success(t('actions.create'))
      } else {
        await updateProduct(Number(id), values)
        message.success(t('actions.save'))
      }
      navigate('/products')
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      message.error(err.response?.data?.detail || t('errors.unknown'))
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (file: File) => {
    try {
      const res = await uploadImage(file)
      form.setFieldValue('image_path', res.data.image_path)
      setImageUrl(res.data.image_url)
      message.success(t('images.uploadSuccess'))
    } catch {
      message.error(t('images.uploadFailed'))
    }
    return false
  }

  return (
    <div style={{ maxWidth: 800 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/products')}>{t('actions.back')}</Button>
        <Title level={4} style={{ margin: 0 }}>{isNew ? t('products.add') : t('actions.edit')}</Title>
      </Space>

      <Card>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item name="title" label={t('products.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>

          <Form.Item label={t('products.image')}>
            <Space>
              {imageUrl && <Image src={imageUrl} width={120} style={{ borderRadius: 8 }} />}
              <Upload
                beforeUpload={handleUpload}
                showUploadList={false}
                accept="image/*"
              >
                <Button icon={<UploadOutlined />}>{t('actions.upload')}</Button>
              </Upload>
            </Space>
          </Form.Item>

          <Form.Item name="image_path" label="image_path" rules={[{ required: true }]}>
            <Input />
          </Form.Item>

          <Form.Item name="price" label={t('products.price')} rules={[{ required: true }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} prefix="¥" />
          </Form.Item>

          <Form.Item name="style_type" label={t('annotations.styleType')}>
            <Select allowClear>
              {STYLE_TYPES.map(([value, key]) => <Option key={value} value={value}>{t(key)}</Option>)}
            </Select>
          </Form.Item>

          <Form.Item name="color_family" label={t('products.color')}>
            <Select allowClear>
              {COLORS.map(([value, key]) => <Option key={value} value={value}>{t(key)}</Option>)}
            </Select>
          </Form.Item>

          <Form.Item name="body_fit" label={t('annotations.bodyFit')}>
            <Input />
          </Form.Item>

          <Form.Item name="product_url" label={t('products.link')}>
            <Input placeholder="https://..." />
          </Form.Item>

          <Form.Item name="size_notes" label={t('history.recommendedSize')}>
            <TextArea rows={3} />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                {isNew ? t('actions.create') : t('actions.save')}
              </Button>
              <Button onClick={() => navigate('/products')}>{t('actions.cancel')}</Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
