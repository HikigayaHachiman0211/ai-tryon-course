# 项目架构概览

## 一次推荐如何变成试穿

1. 用户在 Web 主站或微信小程序选择偏好、照片或演示人台，也可请 AI 导购把自然语言需求填进表单。
2. 主站 FastAPI 读取商品目录并计算匹配分。客户端显示推荐、雷达评分和解释，也可在 Style Lab 分析一件指定商品。
3. Web 主站或小程序把商品和选中的图片交给工作台。工作台调用已配置的图片模型，保存任务回执并展示生成结果。
4. 用户可把试穿图用作 01Router 视频任务的参考。Web 工作台另提供由摄像头和实时模型驱动的实时试穿。

## 服务与数据

| 服务 | 入口与职责 |
| --- | --- |
| 推荐服务 | `main-app/backend/app/main.py` 负责目录、推荐、评分、历史、导购和语音接口。React 前端在 `main-app/frontend/`。 |
| 管理服务 | `main-app/admin/backend/app/main.py` 维护商品、提示词、模型路由、视频和实时试穿配置。React 后台在 `main-app/admin/frontend/`。 |
| 试穿工作台 | `tryon-workbench/main.py` 提供静态工作台、目录、图像任务与媒体访问，视频和实时串流由 `tryon-workbench/app/` 中的相关路由处理。 |
| 小程序 | `miniprogram/miniprogram/app.json` 声明页面，`services/` 调用推荐和试穿服务，`store/` 保存页面之间的偏好和交接信息。 |

两个应用服务在本地可使用 SQLite。后台保存模型配置，工作台与主站通过配置数据库和服务端密钥读取各自的运行配置。Azure Container Apps 模板提供 PostgreSQL 和独立的图片任务 Worker。

## 三语目录

推荐规则读取同样的商品属性和评分字段。简体中文、English 和日本語共用商品标识，各自有展示文案。在主站生成目录读取文件后，`scripts/i18n/sync_workbench_catalog.py` 将商品和翻译组装为工作台的目录文件。公开版从 `main-app/database.json` 的 8 件合成商品生成这套文件。

## 本地和云端入口

本地端口、环境变量和各供应商设置见 [README](README.md)。云端可参考 [Azure](deploy/azure/README.md)和 [阿里云](deploy/aliyun/README.md)模板。完整商品资源打包脚本要求部署者准备对应的完整目录和图片。代码版的功能与使用条件见 [更新日志](CHANGELOG.md)。
