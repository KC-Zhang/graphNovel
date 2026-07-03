# 自行部署 BookMiro

这个仓库就是**完整、可自行部署的应用**——所有功能（随阅读展开图谱、语言锁定抽取、跳转原文、关系走查、已读追踪、正文反向链接）在你自己部署运行时都是完整可用的。没有"试用版"或"阉割版"：自行部署与未来的托管产品（见 [STRATEGY.md](./STRATEGY.md)）运行的是完全相同的应用代码。托管版本额外增加的，只是面向多用户的部分（账号体系、计费、共享公共书库、下架处理）——见下方[自行部署不包含什么](#自行部署不包含什么)。

你只需要提供一个 LLM API Key。你的书籍、抽取出的图谱、阅读进度都保存在你自己的机器/服务器上——除了逐章抽取图谱所需的 LLM 调用外，不会向任何地方发送数据。

## 你需要什么

| 需求 | 用途 |
|---|---|
| 一个 LLM API Key（任意兼容 OpenAI SDK 的接口） | 图谱抽取会逐章调用 LLM。任意服务商都可以——OpenAI、阿里百炼/DashScope（Qwen）等 |
| 以下之一：你自己的电脑、一台服务器，或免费/低成本的云主机 | 用于运行 Flask 后端 + 静态前端 |

不需要其他任何东西——没有数据库，没有对象存储，没有第三方图谱服务。数据以纯文件形式存储在磁盘上（见[数据与存储](#数据与存储)）。

## 选择一种部署方式

| 方式 | 适合场景 | 复杂度 |
|---|---|---|
| [本地源码运行](#1-本地源码运行---用于开发或在自己电脑上个人使用) | 体验功能、在自己电脑上个人使用 | 低 |
| [Docker Compose](#2-docker-compose---在-nas家庭服务器或任何装有-docker-的机器上个人使用) | 在 NAS/家庭服务器或任何装有 Docker 的机器上个人使用 | 低 |
| [Render Blueprint](#3-render-blueprint---在云端部署你自己的实例) | 想要一个随处可访问的个人实例，运维成本最低 | 低-中 |
| 其他任意主机（Fly.io、Railway、自己的服务器等） | 思路与 Render 相同，见[部署到其他平台](#部署到其他平台) | 中 |

四种方式运行的是完全相同的代码，按你想把它部署在哪里来选择即可。

### 1. 本地源码运行 - 用于开发或在自己电脑上个人使用

环境要求：

| 工具 | 版本 | 检查 |
|---|---|---|
| Node.js | 18+ | `node -v` |
| Python | ≥3.11, ≤3.12 | `python --version` |
| uv | 最新 | `uv --version` |

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY（若不直接用 OpenAI，也设置 LLM_BASE_URL / LLM_MODEL_NAME）

npm run setup:all   # 安装根目录 + 前端（npm）与后端（uv）依赖
npm run dev         # 启动后端 (:5001) 与前端 (:3000)
```

打开 `http://localhost:3000`。完整说明见 [README-ZH.md](./README-ZH.md)。

### 2. Docker Compose - 在 NAS、家庭服务器或任何装有 Docker 的机器上个人使用

使用本仓库 [GitHub Action](.github/workflows/docker-image.yml) 发布到 `ghcr.io/666ghj/mirofish` 的镜像（由 [Dockerfile](./Dockerfile) 构建，通过 `npm run dev` 同时启动前后端）。

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY

docker compose up -d
```

使用 [docker-compose.yml](./docker-compose.yml)：从项目根目录读取 `.env`，映射端口 `3000`（前端）/`5001`（后端），并将上传的书籍持久化到宿主机的 `./backend/uploads`，容器重启/升级后数据不丢失。

如果想自己构建镜像而不是拉取：`docker build -t bookmiro .`

### 3. Render Blueprint - 在云端部署你自己的实例

[render.yaml](./render.yaml) 部署的是**你自己的单租户实例**到 [Render](https://render.com)——同样的应用，只是可以随处访问而不仅限于 `localhost`。这不是多租户托管产品，只是个人部署的一种方式。

1. Fork 本仓库（这样 Render 才能在你推送后自动部署）。
2. 在 Render 控制台：**New > Blueprint**，指向你 fork 的仓库。
3. Render 会根据 `render.yaml` 创建两个服务：
   - `bookmiro-backend` - Flask + gunicorn，挂载一块小型持久磁盘到 `/var/data/uploads` 用于保存你的书库（重新部署后数据不丢失）。
   - `bookmiro-frontend` - 静态 Vue 构建产物。
4. 按提示填入密钥类环境变量（`render.yaml` 中标记 `sync: false` 的项）：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_NAME`。
5. 部署。前端的 `VITE_API_BASE_URL` 在 `render.yaml` 中被写死为后端的公网地址 `https://bookmiro-backend.onrender.com`——**如果你重命名了任一服务**，需要相应更新这个值（该配置项上方的注释解释了为什么它必须是公网地址，而不能用 `fromService`/私有网络引用）。

费用说明：后端计划设为 `starter`（付费），因为 Render 的免费 Web 服务在空闲后会休眠（会中断正在进行的图谱抽取），且免费实例无法挂载持久磁盘。如果你不需要这两项保证，可自行降级，但风险自负。

### 部署到其他平台

本应用就是一个普通的 Flask 后端 + 静态 Vue 前端，因此任何能运行 Python Web 服务（带持久磁盘/卷）并托管静态站点的平台都可以用同样的方式部署：

- **后端**：在 `backend/` 目录用 `uv sync --frozen` 安装依赖，用
  `gunicorn -w 1 --threads 8 -t 600 -b 0.0.0.0:$PORT "app:create_app()"` 启动。**`-w 1`（单进程）是必须的**——`ExtractionManager` 在内存中追踪抽取进度，多个 worker/进程之间不会共享该状态。将 `UPLOAD_FOLDER` 指向一个持久化路径。
- **前端**：在 `frontend/` 目录执行 `npm run build` 生成静态 `dist/` 目录；用支持 SPA 回退（未知路由 -> `index.html`，用于 Vue Router 的 history 模式）的方式托管，并在构建时将 `VITE_API_BASE_URL` 设为后端的公网地址。

## 环境变量参考

| 变量 | 是否必需 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_API_KEY` | 是 | - | 任意兼容 OpenAI SDK 的服务商 |
| `LLM_BASE_URL` | 否 | `https://api.openai.com/v1` | 使用非 OpenAI 服务商时设置（DashScope 等） |
| `LLM_MODEL_NAME` | 否 | `gpt-4o-mini` | 每章都会调用一次，建议选择性价比较高的模型 |
| `SECRET_KEY` | 超出本地使用范围时建议设置 | `bookmiro-secret-key` | 一旦不再仅在 localhost 运行，请设置自己的随机值 |
| `FLASK_DEBUG` | 否 | `True` | 任何非本地部署都应设为 `false` |
| `FLASK_HOST` / `FLASK_PORT` | 否 | `0.0.0.0` / `5001` | 仅在通过 `python run.py` 启动时生效；通过 gunicorn 启动时会被忽略（gunicorn 直接绑定 `$PORT`，例如在 Render 上） |
| `UPLOAD_FOLDER` | 否 | `backend/uploads` | 任何非本地部署都应指向持久化卷/磁盘 |
| `VITE_API_BASE_URL`（前端，构建期） | 否 | `http://localhost:5001` | 一旦前后端不在同一台 localhost 上，必须是后端完整的公网地址（含协议） |

## 数据与存储

所有数据都存放在 `UPLOAD_FOLDER` 下（默认 `backend/uploads/projects/<project_id>/`），全部是纯文件——不需要数据库：

- `project.json` - 书籍元数据（书名、语言、章节列表、抽取进度）
- `episodes.json` - 完整章节正文及字符偏移
- `graph.json` - 抽取出的节点/边（每个都带 `first_episode` 与原文引用）
- `extracted_text.txt`、`files/` - 原始上传文件及其抽取出的文本

已读/已查看状态（你已经复习过哪些章节/节点/关系）保存在浏览器的 `localStorage` 中，按书籍区分——仅限本设备，不会离开你的浏览器。

**备份**：直接复制 `UPLOAD_FOLDER` 目录即可。**多本书**：直接持续上传/阅读即可——每本书都是独立的项目目录，没有人为数量限制。

## 自行部署不包含什么

以上就是全部的阅读/图谱功能，100%。[STRATEGY.md](./STRATEGY.md) 中描述的未来**托管**产品，是在此之上叠加的一层，用于将 BookMiro 作为*共享的、多用户的、付费*服务运行——而不是更多的阅读功能：

- 用户账号与 Stripe 计费（按书付费解锁一次）
- 共享的公共书库（用 Postgres + 对象存储替代本地文件）
- 版权归属确认 + 公开的 DMCA 下架流程
- 管理后台

对于你自己的个人使用而言，以上这些都不是必需的，也不存在缺失。
