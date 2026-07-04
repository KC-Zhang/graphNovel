# 自行部署 BookMiro

本仓库就是完整的应用。自行部署 = 100% 的功能，不涉及账号或计费。你只需要一个 LLM API Key；其余数据都以文件形式保存在本地。

## 需要什么

- 一个 LLM API Key（任意兼容 OpenAI SDK 的接口：OpenAI、DashScope/Qwen 等）
- 一台可以运行 Flask 后端 + 静态前端的机器（自己的电脑、服务器，或任意主机）

不需要数据库，不需要对象存储，不需要第三方图谱服务。

## 1. 本地源码运行

| 工具 | 版本 | 检查 |
|---|---|---|
| Node.js | 18+ | `node -v` |
| Python | ≥3.11, ≤3.12 | `python --version` |
| uv | 最新 | `uv --version` |

```bash
cp .env.example .env
# 填入 LLM_API_KEY（若不直接用 OpenAI，也设置 LLM_BASE_URL / LLM_MODEL_NAME）

npm run setup:all   # 安装根目录 + 前端（npm）与后端（uv）依赖
npm run dev         # 后端 :5001，前端 :3000
```

## 2. Docker Compose

```bash
cp .env.example .env
docker compose up -d
```

拉取由 [.github/workflows/docker-image.yml](.github/workflows/docker-image.yml) 发布到
`ghcr.io/666ghj/mirofish` 的镜像（由 [Dockerfile](./Dockerfile) 构建）。
[docker-compose.yml](./docker-compose.yml) 映射端口 `3000`/`5001`，并将 `./backend/uploads`
挂载到宿主机，重启/升级后数据不丢失。自己构建镜像：`docker build -t bookmiro .`

## 3. Render Blueprint

[render.yaml](./render.yaml) 部署你自己的单租户实例到 Render。

1. Fork 本仓库。
2. Render 控制台 -> **New > Blueprint** -> 指向你 fork 的仓库。
3. 会创建 `bookmiro-backend`（Flask + gunicorn，持久磁盘挂载到 `/var/data/uploads`）和
   `bookmiro-frontend`（静态构建产物）。
4. 按提示填入标记 `sync: false` 的环境变量：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_NAME`。
5. `VITE_API_BASE_URL` 在 `render.yaml` 中写死为 `https://bookmiro-backend.onrender.com`。
   如果重命名了任一服务，需要更新它（`render.yaml` 中该配置项上方的注释解释了为什么必须是公网地址，
   而不能用 `fromService`/私有网络引用）。

后端计划为 `starter`（付费）：免费的 Render Web 服务会休眠（中断正在进行的抽取），且无法挂载磁盘。

## 4. 其他任意主机

- **后端**：在 `backend/` 执行 `uv sync --frozen`，然后运行
  `gunicorn -w 1 --threads 8 -t 600 -b 0.0.0.0:$PORT "app:create_app()"`。`-w 1` 是必须的——
  `ExtractionManager` 在内存中追踪抽取进度，不会在多个 worker/进程间共享。将 `UPLOAD_FOLDER`
  指向持久化路径。
- **前端**：在 `frontend/` 执行 `npm run build` 生成 `dist/`；以支持 SPA 回退（未知路由 ->
  `index.html`）的方式托管，构建时设置 `VITE_API_BASE_URL` 为后端公网地址。

## 环境变量

| 变量 | 是否必需 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_API_KEY` | 是 | - | 任意兼容 OpenAI SDK 的服务商 |
| `LLM_BASE_URL` | 否 | `https://api.openai.com/v1` | 使用非 OpenAI 服务商时设置 |
| `LLM_MODEL_NAME` | 否 | `gpt-4o-mini` | 抽取时每章调用一次 |
| `OPENROUTER_API_KEY` | 否 | - | 可选 fallback key；主 LLM 抽取失败后会通过 OpenRouter DeepSeek V3.2 重试 |
| `SECRET_KEY` | 否 | `bookmiro-secret-key` | 一旦不再仅在 localhost 运行，设置真实值 |
| `FLASK_DEBUG` | 否 | `True` | 任何非本地部署设为 `false` |
| `FLASK_HOST` / `FLASK_PORT` | 否 | `0.0.0.0` / `5001` | 仅 `python run.py` 启动时生效；gunicorn 下忽略（直接绑定 `$PORT`） |
| `UPLOAD_FOLDER` | 否 | `backend/uploads` | 生产环境指向持久化卷/磁盘 |
| `VITE_API_BASE_URL`（前端，构建期） | 否 | `http://localhost:5001` | 前后端不在同一 localhost 时，需为完整后端地址（含协议） |

## 数据

全部存放在 `UPLOAD_FOLDER/projects/<project_id>/` 下，无数据库：

- `project.json` — 书籍元数据（书名、语言、章节、抽取进度）
- `episodes.json` — 章节正文及字符偏移
- `graph.json` — 抽取出的节点/边（`first_episode` + 原文引用）
- `extracted_text.txt`、`files/` — 原始上传文件与抽取出的文本

已读/已查看状态仅存于浏览器 `localStorage`，按书籍区分。

备份 = 复制 `UPLOAD_FOLDER`。多本书 = 多个项目目录，无数量限制。

## 代码分区（供后续拆分仓库时参考，见 STRATEGY.md）

目前仓库中的所有代码都是自托管应用代码，尚不存在任何托管专属代码。

**应用本体（自托管所需，未来托管版本也原样复用）：**
- `frontend/src/{views,components,composables,api,router,store,i18n}` — Vue 应用
- `backend/app/{api,services,models,utils}` — Flask 后端、LLM 抽取、基于文件的持久化
- `locales/` — 多语言文案
- `render.yaml`、`docker-compose.yml`、`Dockerfile`、`.env.example` — 部署配置，均为单租户

**不属于运行时应用的部分（判断"自托管需要什么"时可忽略）：**
- `tools/selfheal/` — 本地运维 CLI，用于读取 Render 日志并提交修复 PR；不会分发给或被最终用户使用
- `.github/workflows/` — CI（发布 Docker 镜像）；从源码或已发布镜像自托管都不需要它
- `STRATEGY.md`、`SELF_HOSTING*.md` — 文档，非代码

**托管专属（见 STRATEGY.md，本仓库中尚未实现任何部分）：** 账号/鉴权、Stripe 计费、Postgres
书库 + 对象存储、版权确认/DMCA 下架、管理后台。按 STRATEGY.md 第 1 节的规划，这部分建成后会放在
独立的私有仓库 `bookmiro-cloud` 中（依赖本仓库），而不会混入上面的 `backend/app/` 或
`frontend/src/`。
