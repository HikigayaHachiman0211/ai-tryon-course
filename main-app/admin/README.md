# AI 羽绒服推荐 — 站长管理后台

## 快速开始

### Docker Compose（推荐）

```bash
cd admin
docker compose up --build
```

访问 http://localhost:8081 ，首次运行前请通过环境变量设置管理员账号和密码。

### 本地开发

**后端：**
```bash
cd admin/backend
pip install -r requirements.txt
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_tryon"
export JWT_SECRET_KEY="<your-jwt-secret-at-least-32-characters>"
uvicorn app.main:app --reload --port 8081
```

**前端：**
```bash
cd admin/frontend
npm install
npm run dev
```

前端开发服务器运行在 5173 端口，自动代理 `/api` 请求到 8081。

## 架构

```
admin/
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # 入口
│   │   ├── config.py        # 配置
│   │   ├── database.py      # ORM 模型
│   │   ├── auth.py          # JWT 认证
│   │   ├── routers/         # 11 个路由模块
│   │   └── services/        # 业务服务
│   └── requirements.txt
├── frontend/         # React + Ant Design 前端
│   ├── src/
│   │   ├── pages/           # 12 个页面
│   │   ├── api/             # 11 个 API 模块
│   │   ├── components/      # 布局 + 路由守卫
│   │   └── utils/           # Axios 封装
│   └── package.json
├── integration/      # 主站集成模块
├── Dockerfile        # 多阶段构建
└── docker-compose.yml
```

## 功能模块

| 模块 | 路由 | 说明 |
|------|------|------|
| 仪表盘 | `/` | 概览统计、趋势图、偏好分析 |
| 商品管理 | `/products` | CRUD、批量导入、链接验证 |
| 推荐历史 | `/history` | GCS 历史记录浏览 |
| 系统监控 | `/system` | 健康检查、错误日志、配置 |
| 图片管理 | `/images` | GCS 图片浏览、上传、孤儿检测 |
| AI 试穿 | `/tryon-tasks` | 任务队列、成功率、重试 |
| Prompt 管理 | `/prompts` | Monaco 编辑器、版本对比、测试 |
| 标注中心 | `/annotations` | 标注审核、置信度、批量操作 |
| 用户画像 | `/profiles` | 体型分析、尺码分布 |
| 示例模特 | `/sample-models` | 上传管理、排序、启停 |

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `DATABASE_URL` | 是 | PostgreSQL 连接串 |
| `JWT_SECRET_KEY` | 是 | JWT 签名密钥 |
| `ADMIN_INIT_USERNAME` | 否 | 初始管理员用户名（默认 admin） |
| `ADMIN_INIT_PASSWORD` | 否 | 初始管理员密码 |
| `MAIN_SITE_URL` | 否 | 主站地址 |
| `GCS_BUCKET_NAME` | 否 | GCS 存储桶 |
| `GEMINI_API_KEY` | 否 | Gemini API Key（Prompt 测试用） |
