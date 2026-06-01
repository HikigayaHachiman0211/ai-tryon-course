# Project4.15-AI-Try-on — 项目全景概述

> 本文档旨在让 AI Agent 快速、全面地理解本项目的背景、架构、数据流、技术栈和各子模块关系。  
> 协作准则请参阅根目录的 [CLAUDE.md](CLAUDE.md)。

---

## 一、项目定位与商业目标

**AI 羽绒服智能推荐 + 虚拟试穿平台**

- **核心价值**：用户上传全身照并填写个人偏好（颜色、MBTI、尺码、风格等），系统通过 **Google Gemini AI** 分析用户体型特征，在 4700+ 件羽绒服商品中进行多维度打分推荐，并支持将推荐结果发送至独立的 AI 虚拟试穿服务进行一键试衣。
- **目标用户**：冬季服饰消费者（中国市场），涵盖男款、女款、中性款。
- **数据来源**：京东商品数据（Excel 表格 + 商品图片），后续已扩展支持淘宝数据。

---

## 二、项目演进路线

本项目经历了三个阶段的迭代：

### 阶段 1：数据采集与预处理（根目录脚本）

根目录下的独立 Python 脚本负责原始数据的采集和清洗：

| 脚本 | 功能 |
|------|------|
| `download_jd_images.py` | 从京东 Excel 表格（`京东数据表格1776267016.xlsx`）中批量下载商品图片，支持多线程并发、断点续传、重试机制 |
| `prune_jd_rows_by_images.py` | 反向清洗：删除 Excel 中图片下载失败的行，确保数据与图片一一对应 |
| `build_jd_database.py` | 将 Excel 数据与 PNG 图片匹配（模糊匹配 + 精确匹配），提取颜色（文本关键词 + 像素视觉分析）、款式类型、版型适配度、风格特征、功能属性，输出结构化的 `database.json` |

**关键数据管道**：
```
京东 Excel (.xlsx)  →  download_jd_images.py  →  downloaded_jd_images/羽绒服/
                    →  prune_jd_rows_by_images.py  →  清洗后的 Excel
                    →  build_jd_database.py  →  database.json (4721 条结构化商品记录)
```

### 阶段 2：AI 虚拟试穿工作台（PJ111ForGemini）

独立的 FastAPI 应用，专注于 **AI 虚拟试穿**（Virtual Try-On）功能：

- **AI 引擎**：Google Gemini（flash/pro 模型），支持 Vertex AI、API Key、AI Studio 三种接入方式
- **核心能力**：接收用户全身照 + 服装参考图，利用精心设计的 Prompt 生成逼真的虚拟试穿效果图
- **Prompt 设计**（`prompt.txt`）：约 60 行精细指令，涵盖身份保持、服装保真、自然穿着质量、严格负面约束等
- **部署**：Google Cloud Run（`ai-tryon-workbench-20260417`）
- **存储**：Firestore（任务状态）+ GCS（结果图片）
- **前端**：内置简单的静态 HTML 页面（`static/index.html`），支持通过 `window.postMessage` 接收外部传入的用户照片和服装图片

### 阶段 3：完整前后端平台（Project4.15-AI-Try-on-with-frontend）

**当前主力版本**，集成了推荐引擎 + 前端 + 试穿打通的完整平台，并包含独立的站长管理后台（`admin/` 子目录）：

---

## 三、当前系统架构（Project4.15-AI-Try-on-with-frontend）

### 3.1 技术栈总览

| 层 | 技术 | 版本/说明 |
|---|------|----------|
| **后端** | FastAPI + SQLAlchemy 2.0 + Uvicorn | Python 3.11 |
| **前端** | React 19 + TypeScript + Vite 8 | 构建为静态文件，由 FastAPI 托管 |
| **数据库** | PostgreSQL (Cloud SQL) / 本地 SQLite | 通过 `DATABASE_URL` 环境变量切换 |
| **对象存储** | Google Cloud Storage (GCS) | 桶名: `<your-gcs-bucket>` |
| **AI 模型** | Google Gemini (`gemini-2.5-flash-lite`) + Deepseek (`deepseek-v4-flash`) | 双引擎：Gemini 支持图片+文本分析，Deepseek 纯文本推断 |
| **虚拟试穿** | Gemini Imagen (独立 Cloud Run 服务) | `ai-tryon-workbench-20260417` |
| **部署** | Google Cloud Run (asia-east1) | Docker 多阶段构建 (Node 22 Alpine + Python 3.11 Slim) |
| **CI/CD** | Cloud Build | `cloudbuild.app.yaml` (主站) / `cloudbuild.admin.yaml` (管理后台) |
| **管理后台** | React 19 + Ant Design + FastAPI | 独立 Cloud Run 服务 `ai-tryon-admin` |

### 3.2 核心目录结构

```
Project4.15-AI-Try-on-with-frontend/
├── Dockerfile                      # 多阶段构建: 前端 → 后端
├── database.json                   # 商品种子数据 (4721 条)
├── DESIGN.md                       # Apple 风格设计系统规范
├── AWESOME_DESIGN.md               # Awesome Design 方法论参考
├── CLAUDE.md                       # AI 协作行为准则
├── frontend_build_prompt.md        # 前端构建详细提示词
├── admin-dashboard-prompt.md       # 管理后台建设提示词
├── admin/                          # 站长管理后台（独立服务）
│   ├── Dockerfile                  # 双阶段构建 (Node 22 + Python 3.11)
│   ├── docker-compose.yml          # 本地开发编排
│   ├── backend/                    # FastAPI 后端
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── main.py             # 应用入口，路由注册，SPA 托管
│   │       ├── auth.py             # JWT 认证 & 密码哈希
│   │       ├── config.py           # 环境变量配置 (Settings)
│   │       ├── database.py         # SQLAlchemy 模型 (10 张表)
│   │       ├── routers/            # 12 个功能路由模块
│   │       └── services/           # 业务服务 (GCS/统计/标注引擎)
│   ├── frontend/                   # React + Ant Design 前端
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   └── src/
│   │       ├── App.tsx             # HashRouter 路由定义
│   │       ├── pages/              # 13 个管理页面
│   │       ├── api/                # API 调用封装
│   │       ├── components/         # AdminLayout + AuthGuard
│   │       └── utils/              # axios 封装 (JWT 自动注入)
│   └── integration/                # 主站集成模块 (直连 admin 数据库)
├── cloudbuild.app.yaml             # 主站 Cloud Build 配置
├── cloudbuild.admin.yaml           # 管理后台 Cloud Build 配置
├── cloudbuild.backend.yaml         # 后端单独构建配置
├── cloudbuild.frontend.yaml        # 前端单独构建配置
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py                 # FastAPI 入口，路由注册，中间件
│       ├── database.py             # ORM 模型 (Product)，数据库初始化，种子逻辑
│       ├── recommendation.py       # 推荐引擎核心 (Gemini AI + 多维评分)
│       ├── catalog_seed.py         # 数据导入、品牌识别、特征提取
│       ├── history.py              # 历史记录管理 (本地磁盘 + GCS 双写)
│       ├── gcs_storage.py          # GCS 持久化层 (best-effort, 不阻塞主流程)
│       └── errors.py               # 统一错误处理框架 + 错误码目录
├── frontend/
│   ├── package.json                # React 19, ECharts 6, Framer Motion, Lucide Icons
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx                 # 主应用 (hash 路由: #recommend / #style-lab)
│       ├── api.ts                  # API 调用封装 (Axios)
│       ├── types.ts                # TypeScript 类型定义
│       └── components/
│           ├── RadarChart.tsx       # ECharts 雷达图组件
│           ├── DebugDrawer.tsx      # 调试抽屉组件
│           └── HistoryDrawer.tsx    # 历史记录抽屉
└── downloaded_jd_images/
    ├── 羽绒服/                      # 原始下载图片
    └── 羽绒服_png/                  # PNG 格式商品图
```

### 3.3 环境变量清单

| 变量名 | 用途 | 示例值 |
|--------|------|--------|
| `DATABASE_URL` | 数据库连接串 | `postgresql+psycopg://...` (生产) / `sqlite:///local.db` (开发) |
| `PUBLIC_IMAGE_BASE_URL` | 商品图片公开访问前缀 | `https://storage.googleapis.com/<your-gcs-bucket>/<your-image-prefix>"运动", "户外", "品牌:安踏"]` |
| `function_features` | JSON | 功能属性：`["连帽", "防泼水", "保暖"]` |
| `size_tags` | JSON | 尺码标签：`["M", "L", "XL"]` |
| `size_notes` | String(255) | 尺码备注（体重建议等） |

**尺码标准化**：支持 XS ~ 7XL，可从身高推断尺码（如 175cm → L）。

**数据库初始化**：应用启动时通过 `lifespan` 事件自动执行 `ensure_database(seed_if_empty=True)`，从 `database.json` 导入种子数据。

### 4.2 推荐引擎 (`recommendation.py`)

推荐引擎是系统的核心，采用 **AI 分析 + 规则评分** 混合策略，支持 **Gemini / Deepseek 双引擎**：

#### 用户画像解析流程

```
用户输入 (颜色偏好/照片/MBTI/尺码/风格偏好)
    │
    ├─ 用户选择引擎: auto / gemini / deepseek
    │
    ├─ [auto/gemini] 有照片且尺码/风格未填 → 调用 Gemini AI 分析体型（图片+文本）
    │   └─ Gemini 返回: recommended_size, body_shape, suggested_style, reasoning
    │
    ├─ [auto/deepseek] Gemini 不可用或用户选 Deepseek → 调用 Deepseek（纯文本推断）
    │   └─ Deepseek 返回: 同结构 JSON（不含图片分析）
    │
    ├─ 两者均失败 → 规则回退 (heuristic)
    │
    └─ 用户直接填写 → 直接使用
```

#### Deepseek API 集成

- **API 端点**: `https://api.deepseek.com/chat/completions`（OpenAI 兼容格式）
- **认证**: `Authorization: Bearer <API_KEY>`
- **可用模型**: `deepseek-v4-flash`（默认）、`deepseek-v4-pro`、`deepseek-chat`、`deepseek-reasoner`
- **JSON 输出**: 通过 `response_format: { type: 'json_object' }` 确保结构化输出
- **限制**: 不支持图片输入，仅基于文本信息（性别/MBTI/尺码/颜色偏好）进行推断

#### 多维评分体系

每件商品从以下维度打分（0-100），加权汇总为总分：

| 维度 | 权重 | 评分逻辑 |
|------|------|----------|
| 颜色适配度 | 高 | 用户偏好颜色与商品颜色色系匹配（完全匹配/同色系/互补色） |
| 身材适配度 | 高 | AI 推断体型与商品版型适配（修身 vs 宽松 vs 标准） |
| 款式适配度 | 中 | 用户偏好款式与商品款式类型匹配 |
| 性格适配度 | 中 | MBTI 性格与风格特征的关联匹配 |
| 品牌适配度 | 可选 | 品牌偏好匹配（精确匹配/模糊匹配/别名映射） |

#### 商品颜色分组

```python
COLOR_GROUPS = {
    "black": ["黑", "曜石黑", "极夜黑", "幻影黑", "静谧黑", ...],
    "white": ["白", "米白", "极晶白", "月光白", ...],
    "gray":  ["灰", "浅灰", "深灰", "钛灰", ...],
    "blue":  ["蓝", "雾蓝", "光影蓝", "藏青", ...],
    "green": ["绿", "豆绿", "潜水绿", "橄榄"],
    "red":   ["红", "骐骥红"],
    "orange":["橘", "落日橘"],
    "brown": ["棕", "咖", "卡其", "米色", ...],
}
```

#### 款式类型分类

```
常规短外套 | 短款 | 轻薄款 | 绗缝款（排骨款）| 面包服 | 中长款大衣 | 长款 | 巴恩风/工装风
```

#### 性别识别

从商品标题中通过关键词识别：男款 / 女款 / 中性(男女同款/情侣款) / 童装（自动过滤）。

#### 品牌识别

支持 50+ 品牌别名映射（如"安德玛" ↔ "Under Armour"），从标题和 `style_features` 中提取。

### 4.3 数据导入 (`catalog_seed.py`)

- 从 `database.json` 读取 4721 条预处理好的商品记录
- 提取品牌标签并注入 `style_features`
- 从标题中提取尺码标签和尺码备注
- 支持京东和淘宝两种数据来源（通过图片路径前缀区分平台）
- 通过视觉分析（PIL）提取图片主色调作为颜色色系备选

### 4.4 历史记录 (`history.py`)

- **双写策略**：本地磁盘（`/tmp/history`）为主 + GCS 为持久备份
- 保存完整推荐结果、评分明细、用户偏好参数
- 自动生成缩略图（PIL 裁剪，120×160px）
- 最多保留 200 条历史记录

### 4.5 GCS 存储 (`gcs_storage.py`)

- Best-effort 模式：GCS 不可用时静默降级为本地存储
- 存储内容：推荐结果 JSON + 缩略图 PNG
- 路径规则：`{GCS_RESULT_PREFIX}/results/{id}.json` 和 `{GCS_RESULT_PREFIX}/thumbnails/{id}.png`

### 4.6 错误处理框架 (`errors.py`)

**统一错误码体系**：

| 错误码 | HTTP 状态 | 含义 |
|--------|-----------|------|
| `SYS-000` | 500 | 未捕获的服务端异常 |
| `SYS-001` | 422 | 请求参数校验失败 |
| `SYS-002` | 400 | 通用 HTTP 异常 |
| `REC-001` | 400 | 价格区间非法 (price_min > price_max) |
| `REC-002` | 502 | Gemini 请求失败（自动回退规则推断） |
| `DBG-001` | 403 | 调试页被禁用 |
| `LAB-001` | 404 | Style Lab 商品不存在 |

错误事件使用 `deque(maxlen=200)` 在内存中缓存，通过调试接口暴露。

---

## 五、API 接口清单

### 5.1 核心业务接口

| 方法 | 路径 | 功能 | 请求格式 |
|------|------|------|----------|
| `GET` | `/health` | 健康检查 | - |
| `POST` | `/api/recommend` | AI 智能推荐 | `multipart/form-data` |
| `GET` | `/api/products` | 商品目录（分页、筛选） | Query Params |
| `POST` | `/api/style-lab/analyze` | 单品搭配分析 | `multipart/form-data` |

### 5.2 历史与调试接口

| 方法 | 路径 | 功能 |
|------|------|------|
| `GET` | `/api/history` | 历史记录列表 |
| `GET` | `/api/history/{id}` | 历史详情 |
| `GET` | `/api/history/{id}/thumbnail` | 历史缩略图 |
| `GET` | `/api/debug/error-codes` | 错误码目录 |
| `GET` | `/api/debug/errors/recent` | 最近错误事件 |

### 5.3 推荐接口详解

**请求字段** (`multipart/form-data`)：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `photo` | File | 否 | 用户全身照 |
| `color_preference` | string | 是 | 颜色偏好（如"黑色"、"蓝色系"） |
| `brand_preference` | string | 否 | 品牌偏好（如"波司登,安踏"） |
| `gender` | string | 否 | 性别（male/female） |
| `price_min` | number | 否 | 价格下限 |
| `price_max` | number | 否 | 价格上限 |
| `mbti` | string | 否 | MBTI 类型 |
| `size` | string | 否 | 尺码（XS~7XL 或身高如"175"） |
| `style_preference` | string | 否 | 款式偏好 |
| `gemini_api_key` | string | 否 | 用户自带 Gemini API Key |
| `gemini_model` | string | 否 | 指定 Gemini 模型 |
| `deepseek_api_key` | string | 否 | 用户自带 Deepseek API Key |
| `deepseek_model` | string | 否 | 指定 Deepseek 模型（deepseek-v4-flash/deepseek-v4-pro/deepseek-chat/deepseek-reasoner） |
| `ai_provider` | string | 否 | AI 引擎选择：auto（默认）/ gemini / deepseek |

**响应结构**：

```json
{
  "filters": {
    "price_min": 100,
    "price_max": 800,
    "catalog_total": 4721,
    "matched_after_price_filter": 3200,
    "matched_after_gender_filter": 2100,
    "user_gender": "male",
    "brand_preference": "波司登"
  },
  "inference": {
    "resolved_size": "L",
    "resolved_style": "面包服",
    "body_shape": "标准偏壮",
    "size_source": "gemini",
    "style_source": "gemini",
    "reasoning": "根据照片分析，身高约175cm...",
    "gemini_model": "gemini-2.5-flash-lite",
    "gemini_used": true
  },
  "items": [
    {
      "id": 42,
      "title": "安踏面包羽绒服...",
      "price": 329.0,
      "image_url": "/static/products/xxx.png",
      "brand": "安踏",
      "platform": "京东",
      "style_type": "面包服",
      "color_family": "黑色",
      "body_fit": "蓬松宽松版...",
      "style_features": ["运动", "户外"],
      "function_features": ["连帽", "防泼水", "保暖"],
      "size_tags": ["M", "L", "XL"],
      "total_score": 91.2,
      "brand_score": 96,
      "score_breakdown": {
        "颜色适配度": 88,
        "身材适配度": 93,
        "款式适配度": 90,
        "性格适配度": 86
      },
      "radar_chart": [
        {"dimension": "颜色适配度", "score": 88},
        {"dimension": "身材适配度", "score": 93},
        {"dimension": "款式适配度", "score": 90},
        {"dimension": "性格适配度", "score": 86}
      ],
      "reason": "推荐理由..."
    }
  ]
}
```

---

## 六、前端架构

### 6.1 技术栈

- **React 19** + TypeScript 6 + Vite 8
- **ECharts 6** (echarts-for-react)：雷达图
- **Framer Motion 12**：页面动效
- **Lucide React**：图标库
- **Axios**：HTTP 客户端

### 6.2 页面模式

通过 URL Hash 路由切换两个主要视图：

- **`#recommend`（智能推荐模式）**：左侧 Bento Grid 用户输入区 + 右侧推荐结果展示区
- **`#style-lab`（搭配实验室模式）**：浏览商品目录，选择单品进行个性化分析

### 6.3 用户输入区

- 全身照上传（拖拽/点击，支持预览）
- 颜色偏好选择（必填）
- 品牌偏好（选填，预设推荐：阿迪达斯/骆驼/波司登/李宁）
- 性别选择（男/女）
- 价格区间双端滑块
- MBTI 下拉框（16 种类型）
- 尺码输入（可留空，AI 自动识别）
- 款式偏好（可留空，AI 智能帮选）
- AI 引擎选择（自动/Gemini/Deepseek）
- Gemini API Key（选填，选择自动或 Gemini 时显示）
- Deepseek API Key（选填，选择自动或 Deepseek 时显示）
- Deepseek 模型选择（选择自动或 Deepseek 时显示，当前可选 deepseek-v4-flash/v4-pro/chat/reasoner）

### 6.4 推荐结果展示

- **AI 推断总结区**：AI 推断的尺码、款式、体型、推理说明
- **商品卡片列表**：每张卡片含商品图、标题、价格、总分、推荐理由、标签
- **ECharts 雷达图**：四维评分可视化（颜色/身材/款式/性格）
- **虚拟试穿按钮**：`✨ 尝试这件衣服` → 通过 `window.postMessage` 将用户照片 + 商品图传递给试穿工作台

### 6.5 试穿桥接机制

```javascript
// 消息类型
const TRYON_BRIDGE_TYPE = 'DOWN_JACKET_TRYON_INIT';

// 打开试穿工作台窗口
const tryonWindow = window.open(tryonBaseUrl);

// 通过 postMessage 传递数据 (多次重试以等待目标页面加载)
const delays = [250, 700, 1400, 2400]; // ms
delays.forEach(delay => {
  setTimeout(() => {
    tryonWindow.postMessage({
      type: TRYON_BRIDGE_TYPE,
      payload: { userPhoto, garmentImage }
    }, targetOrigin);
  }, delay);
});
```

---

## 七、虚拟试穿工作台（PJ111ForGemini/Cloud）

### 7.1 概述

独立部署的 FastAPI 服务，专注于 AI 虚拟试穿效果图生成。

### 7.2 AI 模型配置

| 模型别名 | 模型 ID | 用途 |
|----------|---------|------|
| `flash` | `gemini-3.1-flash-image-preview` / `gemini-2.5-flash-image` | 快速生成（默认） |
| `pro` | `gemini-3-pro-image-preview` / `gemini-3-pro-image` | 高质量生成 |

### 7.3 接入方式

- **Vertex AI**：通过 GCP 项目凭证 + 服务账号
- **API Key**：直接传入 Gemini API Key
- **AI Studio**：配置独立的 AI Studio API Key 和模型
- **本地代理**：支持本地反向代理（`http://127.0.0.1:8045`）

### 7.4 Prompt 核心要点

试穿 Prompt 长约 60 行，核心要求：

1. **身份保持**：保持原始人物的面部、发型、肤色、体型、姿势不变
2. **服装保真**：完全保留参考服装的所有细节（领口、袖型、面料、颜色、图案）
3. **自然穿着**：服装必须自然贴合身体，有合理的褶皱、垂坠、遮挡
4. **严格禁止**：不美化面部、不改变体型、不添加多余配饰、不暴露超出设计的皮肤

### 7.5 内置商品浏览面板

工作台内置了完整的商品浏览与选择功能（`app/products.py`），加载 `database.json` 作为本地商品目录：

- **API**：`GET /api/products`（分页、筛选）、`GET /api/products/filters`（筛选选项）
- **图片 URL 构建**：`_build_image_url()` 从 `PUBLIC_IMAGE_BASE_URL` 环境变量 + 文件名拼接，对非 ASCII 字符自动 URL 编码
- **前端**：`static/js/script.js` 中的商品卡片面板，支持点击选择商品图作为试穿素材

> **关键配置**：`PUBLIC_IMAGE_BASE_URL` 必须正确设置（含 `/%E7%BE%BD%E7%BB%92%E6%9C%8D_png` 子目录），否则所有商品缩略图 URL 为空。

### 7.6 存储架构

- **Firestore**：任务状态持久化（可选，降级为内存存储）
- **GCS**：试穿结果图片存储
- **本地磁盘**：uploads/、assets/、history/ 目录

### 7.7 环境变量

| 变量名 | 用途 | 示例值 |
|--------|------|--------|
| `GCP_PROJECT_ID` | GCP 项目 ID | `<your-gcp-project-id>` |
| `GCP_LOCATION` | GCP 区域 | `asia-east1` |
| `VITE_RECOMMEND_APP_URL` | 主站 URL（返回按钮） | Cloud Run URL |
| `VITE_TRYON_EMBED_MODE` | 嵌入模式 | `standalone` / `embed` |
| `PUBLIC_IMAGE_BASE_URL` | 商品图片公开 URL 前缀 | `https://storage.googleapis.com/.../羽绒服_png` |

---

## 八、数据处理管道

### 8.1 商品数据结构 (`database.json`)

每条商品记录包含以下字段：

```json
{
  "商品标题": "安踏面包羽绒丨短款连帽羽绒服男冬季新款...",
  "价格": 329.0,
  "图片路径": "downloaded_jd_images/羽绒服_png/00004_安踏....png",
  "款式类型": "面包服",
  "精准颜色色系": "浅灰色系",
  "版型与身材适配度": "蓬松宽松版，适合标准到微胖身材，包裹感更强",
  "风格特征": ["品牌:安踏", "运动", "户外"],
  "功能属性": ["连帽", "防泼水", "保暖"]
}
```

### 8.2 颜色提取策略

1. **文本优先**：从标题中匹配 60+ 颜色关键词（如"岩脊深灰"、"极晶白"、"雾霾蓝"等）
2. **视觉兜底**：若标题无颜色信息，通过 PIL 分析图片主色调（排除背景色，聚焦中心区域）
3. **RGB 映射**：将主色调 RGB 值映射为中文色系名（"深炭黑"、"米白色系"、"灰蓝色系"等）

### 8.3 品牌识别

从标题提取品牌，支持多种格式：
- 中文品牌名：波司登、安踏、鸭鸭、李宁...
- 英文品牌名：Under Armour、The North Face...
- 别名映射：安德玛 ↔ Under Armour

---

## 九、部署架构

### 9.1 Docker 多阶段构建

```
Stage 1: node:22-alpine (前端构建)
  → npm install → npm run build → /app/frontend/dist

Stage 2: python:3.11-slim (后端运行)
  → pip install → 复制后端代码 + 种子数据 + 前端产物
  → uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### 9.2 Cloud Run 部署参数

- **区域**：asia-east1
- **CPU**：1 vCPU
- **内存**：512Mi
- **并发**：40
- **超时**：120s
- **最小实例**：0（冷启动）
- **最大实例**：3

### 9.3 Cloud Build 流水线

```yaml
# cloudbuild.app.yaml
步骤:
  1. Docker Build (传入构建参数 VITE_API_BASE_URL, VITE_TRYON_BASE_URL)
  2. Docker Push (推送到 Artifact Registry)
  3. gcloud run deploy (部署到 Cloud Run + 设置环境变量)
```

---

## 十、设计系统

### 10.1 Apple 风格 (`DESIGN.md`)

主站前端采用 Apple 官网风格设计系统：

- **色彩**：黑色 (`#000000`) 与浅灰 (`#f5f5f7`) 交替，Apple Blue (`#0071e3`) 作为唯一交互强调色
- **字体**：SF Pro Display (≥20px) / SF Pro Text (<20px)，全尺寸负字间距
- **组件**：无边框卡片 (5-8px 圆角)、药丸形 CTA、磨砂玻璃导航栏
- **留白**：电影感呼吸空间，8px 基础间距单位

### 10.2 前端提示词 (`frontend_build_prompt.md`)

用于指导 AI 构建前端的完整提示词，包含：
- 左右双栏布局要求（Bento Grid 风格）
- 每个输入组件的交互规范
- 推荐结果卡片的视觉标准
- ECharts 雷达图集成要求
- 虚拟试穿按钮的打通方案
- 响应式布局要求

### 10.3 管理后台提示词 (`admin-dashboard-prompt.md`)

管理后台的原始设计提示词文档（已全部实现），详见下方 **§十一、站长管理后台** 的完整说明。

---

## 十一、站长管理后台（admin/）

### 11.1 概述

独立部署的 **站长管理后台** 服务，提供完整的商品管理、数据监控、AI 标注、Prompt 配置等运营管理能力。

- **服务名**：`ai-tryon-admin`
- **部署**：Google Cloud Run（`asia-east1`），独立容器
- **Cloud Build**：`cloudbuild.admin.yaml`
- **代码位置**：`Project4.15-AI-Try-on-with-frontend/admin/`
- **架构**：前后端一体（FastAPI 托管 React SPA 静态文件）

### 11.2 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| **后端** | FastAPI + SQLAlchemy 2.0 + Uvicorn | Python 3.11 |
| **前端** | React 19 + TypeScript + Ant Design + ECharts | Vite 8 构建 |
| **代码编辑器** | Monaco Editor | Prompt 在线编辑 |
| **认证** | JWT (python-jose + bcrypt) | Bearer Token，24h 过期 |
| **数据库** | SQLite (开发) / PostgreSQL (生产) | 10 张 ORM 表 |
| **存储** | Google Cloud Storage | 图片管理、试穿结果 |
| **HTTP 客户端** | httpx | 主站健康检查、异步数据上报 |

### 11.3 数据库模型（10 张表）

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `products` | 商品数据 | title, price, image_path, style_type, color_family, annotation_status, annotation_confidence |
| `admin_users` | 管理员账户 | username, password_hash, role, last_login |
| `request_logs` | 请求日志（主站上报） | endpoint, method, status_code, duration_ms, user_ip, request_params |
| `user_profiles` | 用户画像（主站上报） | gender, mbti, color_preference, ai_recommended_size, ai_body_shape, ai_reasoning |
| `tryon_tasks` | 试穿任务 | status, user_photo_url, product_id (FK→products), result_image_url, model_used |
| `prompt_configs` | Prompt 配置 | name, content, variables, model_name, temperature, is_active, version |
| `prompt_versions` | Prompt 版本历史 | prompt_config_id (FK), version, content |
| `annotation_tasks` | 标注任务 | product_id (FK, unique), status, priority, assigned_to |
| `annotation_records` | 标注记录 | product_id (FK), field_name, old_value, new_value, confidence_before/after |
| `sample_models` | 示例模特 | name, gender, image_filename, gcs_url, display_order, is_active |

### 11.4 功能模块与 API

管理后台包含 **12 个功能路由模块**，所有 `/api/admin/*` 路由均需 JWT 认证：

| 模块 | 路由前缀 | 认证 | 核心能力 |
|------|----------|------|----------|
| 认证 | `/api/auth` | 无/JWT | 登录、改密 |
| 仪表盘 | `/api/admin/dashboard` | JWT | 概览统计、请求趋势图（按日聚合）、偏好分布 TOP 10 |
| 商品管理 | `/api/admin/products` | JWT | CRUD、批量删除(`POST /batch-delete`)、JSON 导入(`POST /import-json`)、文件导入(`POST /import`)、图片上传(`POST /upload-image`)、商品链接管理与验证 |
| 历史记录 | `/api/admin/history` | JWT | 分页查看/删除推荐和试穿历史（数据存 GCS） |
| 系统监控 | `/api/admin/system` | JWT | 主站/工作台健康检查、错误日志、环境配置、数据库统计 |
| 图片管理 | `/api/admin/images` | JWT | GCS 图片分页浏览、上传、删除、孤儿图片检测 |
| 试穿任务 | `/api/admin/tryon-tasks` | JWT | 任务列表（分页+状态过滤）、状态统计、任务详情、失败重试 |
| Prompt 管理 | `/api/admin/prompts` | JWT | 在线编辑、版本历史、版本 diff 对比、测试执行 |
| 数据标注 | `/api/admin/annotations` | JWT | 审核/驳回、批量审批、品牌修正、置信度重算、导出、质量报告 |
| 用户画像 | `/api/admin/profiles` | JWT | 分页查看（按性别/体型/回退状态过滤）、统计、关联试穿结果 |
| 示例模特 | `/api/admin/sample-models` | JWT | 上传/编辑/删除/批量操作、排序、启停管理 |
| 数据上报 | `/api/ingest` | `X-Ingest-Key` | 主站数据上报专用（请求日志、用户画像） |

### 11.5 前端页面（13 页）

| 页面 | 路由 | 功能 |
|------|------|------|
| 登录页 | `/login` | 用户名密码登录，Token 存 localStorage |
| 仪表盘 | `/` | 统计卡片 + ECharts 请求趋势 + 偏好分布 |
| 商品管理 | `/products` | 商品列表搜索、CRUD、批量操作 |
| 商品编辑 | `/products/:id` | 商品新增/编辑表单（含图片上传） |
| 推荐历史 | `/history` | 试穿历史记录查看与删除 |
| 系统监控 | `/system` | 健康检查、错误日志、配置信息 |
| 图片管理 | `/images` | GCS 图片浏览器、上传/删除、孤儿检测 |
| AI 试穿 | `/tryon-tasks` | 试穿任务状态统计 + 列表 + 重试 |
| Prompt 管理 | `/prompts` | Monaco 编辑器、版本历史、diff 对比 |
| 标注中心 | `/annotations` | 标注统计 + 审核/驳回 + 批量操作 |
| 用户画像 | `/profiles` | 用户画像统计 + 列表 + 详情 |
| 示例模特 | `/sample-models` | 模特图片管理、排序、启停 |
| 设置 | `/settings` | 管理员密码修改 |

### 11.6 环境变量

| 变量名 | 说明 | 默认值 / 示例 |
|--------|------|---------------|
| `DATABASE_URL` | 数据库连接 | `sqlite:///./admin_local.db` (开发) |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 至少 32 字符 |
| `JWT_EXPIRE_HOURS` | Token 过期时间 | `24` |
| `ADMIN_INIT_USERNAME` | 初始管理员用户名 | `admin` |
| `ADMIN_INIT_PASSWORD` | 初始管理员密码 | (安全密码) |
| `MAIN_SITE_URL` | 主站 URL | Cloud Run URL |
| `TRYON_WORKBENCH_URL` | 试穿工作台 URL | Cloud Run URL |
| `GCS_BUCKET_NAME` | GCS 存储桶名 | `<your-gcs-bucket>` |
| `PUBLIC_IMAGE_BASE_URL` | 商品图片公开 URL 前缀 | GCS 公开地址 |
| `GEMINI_API_KEY` | Gemini API 密钥 | (用于 AI 标注) |
| `INGEST_SECRET_KEY` | 数据上报共享密钥 | 主站与管理后台共享 |
| `CORS_ALLOW_ORIGINS` | CORS 允许来源 | `*` |

### 11.7 主站数据上报机制

主站通过 HTTP POST 将请求日志和用户画像上报至管理后台的 `/api/ingest` 端点：

```
主站 (/api/recommend, /api/style-lab/analyze)
    │
    └─ 后台任务 (httpx, best-effort) ──→ 管理后台 /api/ingest/request-log
                                       ──→ 管理后台 /api/ingest/user-profile
```

- **认证方式**：`X-Ingest-Key` HTTP Header（共享密钥 `INGEST_SECRET_KEY`）
- **容错策略**：best-effort 模式，上报失败仅记录日志，不阻塞主站请求
- **超时**：5 秒

### 11.8 标注引擎 (`annotation_engine.py`)

基于规则的自动标注置信度计算引擎，6 条核心规则：

1. 默认风格类型（如"常规短外套"无差异性）→ 置信度降至 0.40
2. 风格/功能字段含矛盾关键词 → 降至 0.30
3. 多品牌冲突 → 降至 0.55
4. 颜色色系缺失 → 降至 0.45
5. 品牌信息不一致 → 降至 0.50
6. 功能特征过少 → 降至 0.60

**优先级派生**：置信度 < 0.5 → 高优先(2)，0.5~0.7 → 中优先(1)，> 0.7 → 低优先(0)

### 11.9 主站集成模块 (`integration/`)

供**主站后端**直接引入的 Python 模块，通过 `DATABASE_URL` 环境变量直连 admin 数据库：

| 文件 | 用途 |
|------|------|
| `annotation_feedback.py` | 记录用户对标注的隐式反馈（正面/负面） |
| `middleware_snippet.py` | `RequestLoggingMiddleware` — 主站请求日志中间件 |
| `migrate_sample_models.py` | 迁移脚本：将 GCS 中已有模特图片导入 `sample_models` 表 |
| `profile_logger.py` | `log_profile()` — AI 体型分析后记录用户画像 |
| `prompt_loader.py` | `load_prompt(name, variables)` — 从 admin 数据库加载 prompt 模板并替换变量 |
| `tryon_task_logger.py` | `log_tryon_task()` / `update_tryon_task()` — 记录试穿任务状态 |

### 11.10 Docker 构建

```
Stage 1: node:22-alpine (前端构建)
  → npm install → npm run build → /app/frontend/dist
  → 构建参数: VITE_ADMIN_API_BASE_URL=/

Stage 2: python:3.11-slim (后端运行)
  → pip install → 复制后端代码 + database.json + 前端 dist
  → uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
```

---

## 十二、关键设计决策与约束

### 12.1 AI 引擎降级策略（双引擎）

用户可在前端自行选择 AI 引擎（自动/Gemini/Deepseek），降级链路如下：

- **自动模式（默认）**: Gemini（图片+文本）→ Deepseek（纯文本）→ 规则推断
- **Gemini 模式**: 仅 Gemini → 规则推断
- **Deepseek 模式**: 仅 Deepseek（跳过图片分析）→ 规则推断
- Deepseek 不支持图片输入，选择 Deepseek 时图片分析自动跳过
- 规则推断基于身高推尺码、标题关键词推款式
- 错误码 `REC-002` 表示 AI 引擎失败但已回退

### 12.2 图片服务策略

- **生产环境**：通过 `PUBLIC_IMAGE_BASE_URL` 指向 GCS 公开 URL（必须含 `/%E7%BE%BD%E7%BB%92%E6%9C%8D_png` 子目录）
- **开发环境**：FastAPI 直接 serve 本地 `downloaded_jd_images/` 目录
- **URL 构建**：三站均通过 `_build_image_url()` 提取文件名 + URL 编码 + 拼接 `PUBLIC_IMAGE_BASE_URL`，对中文文件名自动 `urllib.parse.quote()`
- 路径优先级：GCS URL > 本地路径映射

### 12.3 数据一致性

- `database.json` 是唯一的数据源头（truth）
- 应用启动时自动 seed 到数据库
- `FORCE_RESEED=true` 可强制重新导入

### 12.4 安全考量

- Gemini API Key 支持用户自带（前端传入），不存储到后端
- 调试接口通过 `ENABLE_DEBUG_PAGES` 环境变量控制
- Cloud Run 部署时 `--allow-unauthenticated`（公开访问）
- **管理后台**：独立 Cloud Run 服务，JWT 认证保护所有管理 API；数据上报接口使用共享密钥（`X-Ingest-Key`）认证

---

## 十三、开发指南

### 13.1 本地开发启动

```bash
# 后端
cd Project4.15-AI-Try-on-with-frontend/backend
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# 前端
cd Project4.15-AI-Try-on-with-frontend/frontend
npm install
npm run dev  # → http://localhost:5173
```

**管理后台**：

```bash
# 后端
cd Project4.15-AI-Try-on-with-frontend/admin/backend
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --port 8001

# 前端
cd Project4.15-AI-Try-on-with-frontend/admin/frontend
npm install
npm run dev  # → http://localhost:5174
```

### 13.2 AI 协作准则（CLAUDE.md 摘要）

1. **先想再写**：明确假设，有歧义先问
2. **简单优先**：最小代码解决问题，不做投机性设计
3. **精准修改**：只改必须改的，不"顺便优化"
4. **目标驱动**：定义验证标准，循环直到验证通过

---

## 十四、相关服务 URL

| 服务 | 服务名 | URL | 说明 |
|------|--------|-----|------|
| 主站（推荐平台） | `ai-tryon-app` | `<your-main-app-url>` | 前后端一体部署 |
| 试穿工作台 | `ai-tryon-workbench-20260417` | `<your-tryon-workbench-url>` | 独立 Cloud Run 服务 |
| 站长管理后台 | `ai-tryon-admin` | `<your-admin-url>` | 独立 Cloud Run 服务，JWT 认证 |
| GCS 图片桶 | — | `https://storage.googleapis.com/<your-gcs-bucket>/<your-image-prefix>