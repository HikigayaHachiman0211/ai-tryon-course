# 阿里云 ECS／轻量服务器部署准备

本目录与 `deploy/azure/` 使用同一套主站、管理后台和试穿代码。阿里云方案使用一台 AMD64 Linux 服务器、Docker Compose、PostgreSQL、Caddy 和 OSS；`compose.yaml` 从同一个项目目录构建三个应用。此方案不适用于函数计算 FC。这里是部署准备，尚不代表云端资源已创建或实机验收通过。

## 配置

1. 在阿里云准备服务器、域名及商品和媒体 OSS Bucket；Bucket 名称需要全局唯一，`OSS_REGION` 必须与 Bucket 的地域一致。服务器需要 Docker Compose 和 `jq`。设置服务器安全组和系统防火墙，允许 80、443、8443、9443 端口；数据库不直接暴露公网。
2. 将 `.env.aliyun.example` 复制到服务器的 `/opt/ai-tryon-course/shared/aliyun.env`，填写域名、Bucket、数据库及应用密钥，设置文件权限为 `600`。环境文件不要放进代码仓库或发布包。
3. ECS 推荐绑定具有对应 Bucket 最小权限的 RAM 角色，设置 `OSS_CREDENTIAL_MODE=ecs_role` 和角色名；SDK 会刷新临时凭据。也可用 `OSS_CREDENTIAL_MODE=env` 并提供 RAM 用户 AccessKey，使用 STS 时还要提供 `OSS_SESSION_TOKEN`。OSS 连接需要访问所选地域端点；可选 `OSS_ENDPOINT` 是服务端连接地址，公开图片域名由 `PUBLIC_IMAGE_BASE_URL`、`PUBLIC_MEDIA_BASE_URL` 分别指定。
4. 商品图片与用户媒体分别使用 `OSS_PRODUCT_BUCKET` 和 `OSS_MEDIA_BUCKET`。应用目前直接向浏览器返回媒体 URL，历史记录和试穿结果可能包含用户照片；正式公开前必须确定这些 URL 的访问控制与用户数据保护方案。此配置不会自动修改 Bucket 的访问权限。

## 商品资源准备

在包含原始商品图片和完整目录数据的项目检出中，先运行现有清单工具，确认其检查通过：

```bash
python scripts/release/catalog_assets.py --root . \
  --stage-dir deploy/aliyun/product-assets-staging \
  --manifest deploy/aliyun/product-assets-staging/manifest.json
```

在已配置 OSS 凭据的环境中安装 `alibabacloud-oss-v2==1.4.1` 和 `alibabacloud-credentials==1.0.12`，再执行：

```bash
python deploy/aliyun/scripts/upload_product_assets.py \
  --stage-dir deploy/aliyun/product-assets-staging \
  --manifest deploy/aliyun/product-assets-staging/manifest.json \
  --bucket <product-bucket> --region <bucket-region>
```

上传器会同时准备 `frontend/public/sample-models` 中的默认模特图片，并按后台使用的路径写入商品 Bucket。它先核对本地文件及远端已有对象的 SHA-256；匹配的对象会跳过，缺少或不匹配的远端哈希会停止执行，不覆盖已有对象。可通过 `--sample-models-dir` 指定模特图片目录，或用 `--skip-sample-models` 单独上传商品。首次验证时还应检查商品和模特图片实际能从浏览器访问。

## 发布与验证

将完整、校验过的发布目录放在服务器的 `/opt/ai-tryon-course/releases/<release-id>`，让 `/opt/ai-tryon-course/current` 指向该目录。备份与恢复脚本使用此目录约定。进入 `current` 后运行：

```bash
docker compose --env-file /opt/ai-tryon-course/shared/aliyun.env -f deploy/aliyun/compose.yaml config --quiet
docker compose --env-file /opt/ai-tryon-course/shared/aliyun.env -f deploy/aliyun/compose.yaml build main admin workbench
docker compose --env-file /opt/ai-tryon-course/shared/aliyun.env -f deploy/aliyun/compose.yaml up -d
docker compose --env-file /opt/ai-tryon-course/shared/aliyun.env -f deploy/aliyun/compose.yaml ps
```

验证主站 `https://<域名>/health`、后台 `https://<域名>:8443/health`、工作台 `https://<域名>:9443/health`，以及后台存储健康检查、商品图片、图片上传、试穿和历史记录。端口 80 用于证书验证，公网 DNS 必须先指向服务器。真实 OSS 凭据、域名、图片访问策略和三个服务的端到端联调均需在目标环境中完成。

PostgreSQL 和应用数据保存在 Compose 命名卷中。现有 `deploy/azure/scripts/backup.ps1` 和 `restore.ps1` 也支持 `-DeploymentTarget aliyun`，可以通过 SSH 备份数据库与命名卷，并默认将数据库恢复到临时库进行验证；正式覆盖恢复仍需显式指定脚本的两个确认开关。例如，从已配置 SSH 的管理电脑执行：

```powershell
pwsh -File deploy/azure/scripts/backup.ps1 -DeploymentTarget aliyun `
  -SshHost <server-host> -SshUsername <ssh-user> -SshPrivateKeyPath <private-key-path>
```

使用前应验证备份、转移及恢复流程；不要通过删除卷来更新应用。既有云端对象和数据库中的旧媒体 URL 不会自动迁移，需要另行复制并校验。试穿任务当前在单实例内运行，服务器重启会中断进行中的任务。
