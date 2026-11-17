# 幻帧工坊 VisionForge Studio

> AIGC 视频全流程生产平台 - React + FastAPI 全栈项目

从文本 → 剧本 → 资产图 → 分镜图 → 合成成片的一站式 AI 视频制作工作台。

---

## 📁 项目结构

```
visionforge/
├── frontend/                  # 前端项目（React + Vite）
│   ├── package.json           # 前端依赖
│   ├── vite.config.js         # Vite 配置
│   ├── index.html             # HTML 入口
│   └── src/
│       ├── main.jsx           # 应用入口
│       ├── App.jsx            # 路由配置
│       ├── styles/
│       │   └── global.css     # 全局样式（深色科技风）
│       ├── store/
│       │   └── projectStore.js # Zustand 状态管理
│       ├── layouts/
│       │   ├── MainLayout.jsx  # 主布局（顶部导航栏）
│       │   └── AdminLayout.jsx # 管理中心布局（左侧菜单）
│       ├── components/
│       │   └── StepProgress.jsx # 四步流程进度条组件
│       └── pages/
│           ├── workbench/      # 工作台模块（6个页面）
│           │   ├── ProjectList.jsx     # 项目列表
│           │   ├── ProjectCreate.jsx   # 项目创建
│           │   ├── ScriptWorkshop.jsx  # 剧本工坊（第一步）
│           │   ├── AssetGeneration.jsx # 资产生成（第二步）
│           │   ├── Storyboard.jsx      # 分镜故事板（第三步）
│           │   └── FinalRender.jsx     # 成片合成（第四步）
│           ├── admin/          # 管理中心模块（4个页面）
│           │   ├── PromptManager.jsx   # 提示词模板管理
│           │   ├── RAGKnowledge.jsx    # RAG 知识库
│           │   ├── ModelConfig.jsx     # 模型参数配置
│           │   └── SystemSettings.jsx  # 系统设置
│           └── monitor/        # 监控面板模块（1个页面）
│               └── MonitorDashboard.jsx # 监控面板
│
└── backend/                   # 后端项目（FastAPI）
    ├── requirements.txt       # Python 依赖
    └── app/
        ├── main.py            # FastAPI 应用入口
        └── api/               # API 路由（9个模块）
            ├── projects.py    # 项目管理
            ├── scripts.py     # 剧本工坊
            ├── assets.py      # 资产生成
            ├── storyboard.py  # 分镜故事板
            ├── render.py      # 成片合成
            ├── prompts.py     # 提示词模板
            ├── rag.py         # RAG 知识库
            ├── models.py      # 模型配置
            └── monitor.py     # 监控面板
```

---

## 🚀 快速开始

### 前置要求

- **Node.js** >= 16.0（推荐 18+）
- **Python** >= 3.9（推荐 3.10+）
- **npm** 或 **pnpm** / **yarn**

---

### 一、启动前端

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器（默认端口 3000）
npm run dev
```

启动后访问：http://localhost:3000

> 前端通过 Vite 代理将 `/api` 请求转发到后端 **8010** 端口（避开本机 Comfy Desktop 常用的 8000），无需手动配置跨域。

---

### 二、启动后端

```bash
# 进入后端目录
cd backend

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器（默认端口 8010，避免与 Comfy Desktop:8000 冲突）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

启动后访问：
- API 文档（Swagger UI）：http://localhost:8010/api/docs
- 健康检查：http://localhost:8010/

---

## 🎨 技术栈

### 前端
| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18.x | UI 框架 |
| Vite | 5.x | 构建工具 |
| React Router | 6.x | 路由管理 |
| Ant Design | 5.x | UI 组件库 |
| Zustand | 4.x | 状态管理 |
| Axios | 1.x | HTTP 请求 |

### 后端
| 技术 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.115.x | Web 框架 |
| Uvicorn | 0.30.x | ASGI 服务器 |
| Pydantic | 2.x | 数据验证 |
| httpx | 0.27.x | HTTP 客户端（调用 AI API） |

---

## 📱 页面清单

### 工作台模块（6页）
1. **项目列表** - 卡片网格 + 筛选 + 搜索
2. **项目创建** - 三种类型选择（短剧/漫剧/视频）
3. **剧本工坊** - 文本/文件双模式 + 场景解析 + 风格选择
4. **资产生成** - 角色/场景/道具三 Tab。用法：资产页点「从剧本同步」（会从已扩写场景抽出角色/场景草稿）→「重新生成」。Comfy 地址会自动探测 `8000–8020` 与 `8188` 等端口（**8010 是幻帧后端，不是 Comfy**）。
5. **分镜故事板** - 顶部时间轴 + 左右分栏 + 一致性检测
6. **成片合成** - 三栏布局 + 音轨/字幕/高级选项

### 管理中心模块（4页）
7. **提示词模板管理** - 左侧分类树 + 右侧编辑区
8. **RAG 知识库** - 统计卡片 + 案例卡片 + 检索测试
9. **模型参数配置** - 四 Tab（SD/Flux、LTX/Wan2.2、LLM、TTS）
10. **系统设置** - LLM 配置 + 存储路径 + 并发控制 + 界面设置

### 监控面板模块（1页）
11. **监控面板** - 系统概览 + 模型服务状态 + 实时任务队列

---

## ✨ 核心特性

- **🎬 全流程生产**：从文本到成片的一站式 AI 视频制作
- **🧠 LLM 大脑编排**：智能拆解任务、生成提示词、质量校验
- **📚 RAG 经验积累**：每次完成项目自动入库，越用越聪明
- **🌐 中英双语双显**：中文给人看，英文给模型用，两边都能编辑
- **🎭 角色一致性**：提示词层 + 参考图层 + LoRA 层三重保障
- **🎭 四版 AI 选角**：同机位生成四种长相与气质，明确选定后才允许进入分镜
- **🎞 MiniMax H3 编译**：把项目视觉规范、角色锁、分镜与对白编译成可校验、可编辑、可锁定的 H3 提示词
- **🎨 深色科技风**：深蓝黑背景 + 品牌红 + 科技蓝，专业感拉满
- **📊 实时监控**：GPU/CPU/内存状态一目了然，任务队列实时更新

---

## 🔧 配置说明

### Prompt IR 与 MiniMax H3

项目现在把创作意图和具体模型提示词分成两层：

1. **项目视觉圣经（Prompt IR）**保存选角审美、写实策略、身份与临时状态边界、摄影规则和默认负面约束，是跨模型的上游事实来源。
2. **模型编译产物**针对 MiniMax H3 生成最终 T2VA/I2VA 文本。产物带来源哈希、指南版本、校验报告、编辑/锁定状态；角色、分镜或视觉圣经变化后会标记为 `stale`，过期或校验失败的文本不能提交视频任务。

角色页的“AI 选角 · 生成 4 版”会使用一致的中性棚拍机位比较永久面部特征，不把淋雨、疲惫、伤痕等剧情状态写进人物身份。四张候选生成完成后必须选择一张，未选择及未选中的版本都不会通过角色定妆门禁。旧项目中已有的“完成图片 + 身份锁”资产仍兼容。

分镜页可查看、手改、保存和锁定 H3 I2VA 最终提示词。默认视频长度为 124 帧、24 fps（约 5.17 秒），使用 960×544；首次编译只展示结果，确认后再次点击才提交生成。H3 编译只依赖 LLM，不要求 ComfyUI 在线；真正提交图片或视频任务时才检查本地模型服务。

当前为第一阶段：身份选择和提示词锚点已经进入分镜上下文，但 **Flux/SDXL 的参考图条件控制（IP-Adapter/InstantID/LoRA 等）尚未接入**。要获得跨镜头更强的像素级人物一致性，仍需第二阶段根据本机 ComfyUI 节点和权重库存实现参考图编译器。

### 前端配置
- **端口**：默认 3000（修改 `vite.config.js`）
- **后端地址**：默认 `http://127.0.0.1:8010`（修改 `vite.config.js` 中的 proxy）

### 后端配置
- **端口**：默认 8010（启动时加 `--port` 参数；勿与 Comfy Desktop 的 8000 冲突）
- **CORS 源**：默认允许 localhost:3000 / 5173（修改 `app/main.py`）

---

## 📝 开发说明

### 当前状态
- ✅ 前端页面可用；项目列表/创建、剧本扩写、电影感润色已接真实后端
- ✅ ComfyUI 资产生成 / 分镜出图（磁盘图片 + SQLite 元数据）
- ✅ LLM：Ollama 优先、云端降级；管理页可配置多云 Profiles 并测试；本机 Ollama 模型列表
- ✅ 监控快照 + 顶栏 GPU 温度·占用 / 任务角标（统一 jobs：扩写/润色/出图）
- ✅ 后台 Job：切页不断；内容区常驻进行中条；完成后应用内提醒
- ✅ SQLite 持久化：项目 / 场景 / 资产 / 分镜帧 / jobs / rag_cases / renders
- ✅ RAG：案例 CRUD/检索/一键入库；扩写与润色自动注入相似案例（需 `{MODELHUB_ROOT}/embed/bge-m3`；无 Chroma 时用 JSON 向量回退）
- ✅ 剧本台词 `lines`（含 emotion）+ 分镜规划分配到帧
- ✅ 成片：分镜静图 + Edge/VoxCPM TTS + ffmpeg 拼片（可选字幕）；逐集/整片可分别合成；需本机 `ffmpeg`
- ✅ BGM：本地 ACE-Step 生成为器乐配乐，ffmpeg 低音量垫入（FinalRender 开关 + 在线状态提示）
- ✅ 提示词模板库：SQLite 持久化（迁移 008），增删改真实落库，种子模板可覆写
- ✅ Prompt IR：项目视觉圣经 + 带来源哈希的模型编译产物（迁移 009）
- ✅ MiniMax H3：官方格式 T2VA/I2VA 编译、一次自动修复、确定性校验、编辑/锁定/过期拦截
- ✅ AI 选角：四候选商业短剧演员方案，选定一版后才开放下游分镜
- ✅ 测试数据隔离：pytest 在导入应用前使用唯一 SQLite 与 ModelHub 路径，不再写生产数据库
- ✅ 失败可读 + 重试：任务错误分类展示；后台任务失败通知带「重试」按钮
- ✅ 任务控制：监控面板已接任务 pause / resume / cancel
- ✅ 项目完成自动沉淀经验：`POST /projects/{id}/complete` 把剧本/资产/分镜 prompt 自动入库 RAG
- ⏳ 真视频（LTX/Wan）仍未做大特性接入
- ⏳ 音效（SFX）未接入
- ⏳ 用户认证（按需；当前单人自用不做）

### 下一步开发建议
1. 第二阶段：盘点本机 ComfyUI 节点/权重并实现 reference-conditioned Flux/SDXL 编译器，把选定演员图真正绑定到所有分镜静图
2. 真视频成片（LTX/Wan）另开规格
3. （可选）无限制本地大模型：`ollama pull hf.co/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF:Q4_K_M` → 系统设置里切默认模型
4. （可选）安装 chromadb 以替换 JSON 向量回退
5. VoxCPM 权重放到 `%MODELHUB_ROOT%\tts\VoxCPM2` 后再选该引擎

---

## 📄 License

MIT License
