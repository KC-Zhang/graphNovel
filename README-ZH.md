<div align="center">

<img src="./static/image/BookMiro_logo.png" alt="BookMiro Logo" width="50%"/>

# BookMiro

**把一本书读成会生长的知识图谱。**
</br>
<em>上传一本书、一篇论文或一本教材，BookMiro 会把它变成一张会生长的知识图谱，同时保留原始文档的样子。</em>

[English](./README.md) | [中文文档](./README-ZH.md)

</div>

## 概述

**BookMiro** 将书籍和学术文档转化为知识图谱，并与你的阅读进度同步。它不会一次性把整张图谱抛给你，而是只展示你已经读过的部分——因此永远不会剧透后文。

你只需上传一本书、论文或教材（PDF / EPUB / TXT / Markdown），BookMiro 会：

- 将其切分为有序章节（识别章节标题，无标题时按固定长度兜底）。
- 抽取实体（人物、地点、组织、物品、概念）及其关系，并**与原书使用同一种语言**。
- 随你阅读逐章展开图谱，边读边把新的节点/关系流式补入。

## 更新日志

- **2026-07-18** — [学术页面保留原貌，大图也终于看得清。](./release-notes/2026-07-18-big-books-update.zh.md)

## 功能特性

- **学术阅读模式**：论文和教材会以原始 PDF 页面呈现，保留文档结构、公式、图表、表格与排版，同时继续支持搜索高亮和从图谱跳回原文。
- **随阅读展开**：图谱随进度生长，仅显示已读章节；当前章节新出现的节点会闪烁，方便识别"本章新增"。
- **语言锁定抽取**：中文书生成中文的节点、关系标签与类型，绝不出现中英混杂。
- **一键回到原文**：每个节点与关系都保存了原文引用，点击即可跳转到书中对应位置阅读上下文，并高亮该段落。
- **轻松浏览关系（关系走查）**：选中一个人物后，可滚动 / 方向键 / 自动播放依次浏览其全部关系，每条都会在图谱中自动高亮——无需逐条点击。
- **后台 + 流式**：阅读器会立即打开，抽取则在后台按章节继续跑完整本书；后续只增量传输新图谱数据，不会反复下载整张图。

## 快速开始

### 方式一：源码部署（推荐）

#### 环境要求

| 工具 | 版本 | 说明 | 检查 |
|------|------|------|------|
| **Node.js** | 18+ | 前端运行时（含 npm） | `node -v` |
| **Python** | ≥3.11, ≤3.12 | 后端运行时 | `python --version` |
| **uv** | 最新 | Python 包管理器 | `uv --version` |

#### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key
```

**必需的环境变量：**

```env
# LLM API（任意兼容 OpenAI SDK 的接口）
# 图谱抽取会逐章调用 LLM，建议选择性价比较高的模型。
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

> BookMiro 通过直接调用 LLM 在本地完成图谱抽取，无需第三方图谱服务。

#### 2. 安装依赖

```bash
# 一键安装（根目录 + 前端 + 后端）
npm run setup:all
```

或分步安装：

```bash
npm run setup          # Node 依赖（根目录 + 前端）
npm run setup:backend  # Python 依赖（后端，自动创建虚拟环境）
```

#### 3. 启动

```bash
npm run dev            # 同时启动前端 + 后端
```

- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:5001`

单独启动：

```bash
npm run backend
npm run frontend
```

### 方式二：Docker 部署

```bash
cp .env.example .env
docker compose up -d
```

默认读取项目根目录的 `.env`，映射端口 `3000`（前端）/ `5001`（后端）。

### 其他部署方式

Render 部署说明、完整环境变量参考、数据备份说明见 [SELF_HOSTING-ZH.md](./SELF_HOSTING-ZH.md)。

## 工作原理

```
上传（PDF/EPUB/TXT）-> 切分章节 -> 逐章 LLM 抽取（语言锁定）
   -> graph.json（节点/边带 first_episode 与原文引用）
   -> 阅读器按当前章节逐步展开图谱
```

## 致谢

BookMiro 的灵感来自 **[MiroFish](https://github.com/666ghj/MiroFish)** 的**《红楼梦》demo**——MiroFish 是一款多智能体预测引擎，它曾基于《红楼梦》前 80 回构建的知识图谱推演其失传结局。正是那个 demo 启发了"通过不断演化的人物图谱来阅读一本书"的想法。衷心感谢 MiroFish 团队带来的灵感。

## 许可协议

AGPL-3.0，详见 [LICENSE](./LICENSE)。
