# 成片拼片 + 双 TTS + 剧本台词结构化设计

**日期**: 2026-08-12  
**状态**: 待用户审阅规格  
**前置**:
- [工作台真实化：LLM + SQLite + 剧本扩写](./2026-08-11-workbench-persistence-llm-design.md)
- [RAG 真实化 + 工作台后台任务](./2026-08-11-rag-and-background-jobs-design.md)
- [管理运维真实化：监控 + 顶栏任务](./2026-08-11-admin-monitor-realtime-design.md)
- [AI 模型安装（含 VoxCPM / 视频模型预留）](./2026-08-09-ai-model-installation-design.md)

**背景问题**:
1. 成片页与 `/api/render` 全程 mock；无法从分镜图得到可下载视频。  
2. TTS 在模型配置页仅为 UI；无真实配音链路。  
3. 剧本扩写只产出 `dialogue_count` / `narration_count` 数字，**没有台词/旁白正文**，成片无从读稿。  
4. 分镜帧与场景台词无绑定；当前分镜以出图为主，缺少「场景 → 分镜规划 + 台词分配」步骤。  
5. 真视频（LTX/Wan）与静态拼片是两条链路；用户确认本轮只做拼片，视频生成另开规格。

**决策（对话确认）**:
- 范围：**仅本规格**做「分镜静图 + TTS 拼片」；真视频生成拆成后续独立规格。  
- TTS：**Edge TTS 与 VoxCPM 都接**，成片/设置可选引擎。  
- 台词结构：**C**——结构化 `lines[]`，含 `type` / `speaker` / `text` / 可选 `emotion`。  
- 音画对齐：**按分镜帧**配音（每帧若干条台词 → 一段音频）。  
- 台词落到帧：**分镜规划/分析时由 LLM** 把场景台词拆到各帧（非均分、非纯手工）。  
- 成片能力：**最小**——图 + TTS；字幕可选烧录；BGM/音效本轮禁用或明确「未接」。  
- 架构：**方案 1**——统一 `render_compose` Job（逐帧 TTS → ffmpeg → mp4）；复用现有 jobs / 常驻条。  
- **不做**用户认证与权限（单人自用）。  
- 提示词模板库真实化不在本规格（另开一轮）。

---

## 1. 目标与边界

### 1.1 目标
1. 剧本扩写/解析产出可编辑的台词与旁白正文（含 emotion），并持久化。  
2. 分镜页可一键「从场景生成/刷新分镜规划」：LLM 创建或更新帧元数据，并把场景 `lines` 分配到 `frame.lines`。  
3. 成片页对已出图分镜提交合成任务：按所选 TTS 引擎生成配音，ffmpeg 拼成 mp4；可预览/下载。  
4. 合成与 TTS 走后台 Job，切页不断；完成有应用内提醒。

### 1.2 本规格做

| Phase | 交付 |
|---|---|
| **0 数据与扩写** | `scenes.lines_json`；扩写 prompt pack 要求输出 `lines[]`；`dialogue_count`/`narration_count` 由 lines 推导；剧本工坊展示/编辑台词 |
| **1 分镜台词分配** | 新 Job `storyboard_breakdown`：按场景生成/更新帧 + 分配 `lines`；帧表增加 `lines_json`、规范化 `scene_id`；分镜页接线 |
| **2 TTS 引擎** | `TTSProvider` 抽象；Edge TTS 实现；VoxCPM 实现（ModelHub / 仓库路径）；设置或成片页可选引擎；单帧试听 API（可选但推荐） |
| **3 成片合成** | 去掉 render mock；`render_compose` Job；ffmpeg 静图+音轨（可选字幕）；成片页接真实 episodes（由场景派生）与进度 |

### 1.3 非目标
- LTX / Wan / MiniMax 等**真视频**片段生成与拼接  
- BGM / 音效混音、音效库  
- 用户认证、多用户、云同步  
- 提示词模板库 DB 化  
- WebSocket / SSE；Celery / Redis  
- 任务暂停/恢复（保持现有 501）  
- 浏览器系统通知  
- 自动批量电影感润色、导演强模式  
- CosyVoice 等第三 TTS 引擎（仅 Edge + VoxCPM）  
- 帧插值 / 降噪 / 调色等成片页「高级选项」真实化（UI 可禁用）

### 1.4 成功标准
1. 扩写后场景详情可见至少若干条 `lines`（dialogue 与/或 narration）；刷新/重启后仍在。  
2. 执行分镜规划后，项目下有帧；帧上 `lines` 覆盖场景台词（允许旁白跨帧，但不丢条；见 §3.2）。  
3. 至少一帧有 `image_url` 且带台词时，提交合成 → Job 完成 → 得到可播放 mp4（`/media/...`）。  
4. 同一项目可切换 Edge / VoxCPM 重新合成（引擎写在 Job payload / 设置默认值）。  
5. 合成进行中离开成片页，常驻条/顶栏仍可见；完成后 toast；回页可播放。  
6. BGM/音效开关不可用或点击提示未实现；不假装混音成功。

### 1.5 进程重启约定
- 与既有 Job 一致：启动时 `queued`/`running` → `failed`，`error=server_restarted`。  
- 合成产生的临时 wav 可清理；已完成 mp4 保留在磁盘，DB/结果字段指向路径。

---

## 2. 架构与数据流

```
剧本工坊
  └─ script_expand / script_analyze Job
        └─ ScriptExpandService → scenes（含 lines_json）

分镜故事板
  ├─ storyboard_breakdown Job（本规格新增）
  │     └─ 读 scenes.lines → LLM → 创建/更新 frames（含 scene_id + lines_json）
  └─ storyboard_generate（已有）→ ComfyUI 出图 → image_url

成片合成
  └─ render_compose Job
        ├─ 选帧（有图；按 scene / 全集）
        ├─ TTSProvider(engine).synth(lines[]) → 每帧 wav（或每条 wav 再拼接）
        ├─ ffmpeg：静图序列 + 音轨 [+ 可选硬字幕]
        └─ 写 output_url；Job result 含路径与时长

配置
  └─ TTS 默认引擎（Edge | VoxCPM）存本地可写配置（与 llm_settings 同类，或 settings 扩展）
```

要点：
- **真相在后端**：台词与成片结果持久化；前端不把合成进度只放在组件 state。  
- **台词先于成片**：无 `lines` 的帧可静音占位（固定时长用 `duration`），或合成前校验「至少一帧有台词或允许纯静图模式」。默认：允许纯静图（按 `duration`），有台词则音频决定该帧最短时长。  
- **Job 统一**：新类型挂现有 `JobQueue` worker；长耗时 TTS+ffmpeg 不阻塞 HTTP。

### 2.1 实现顺序（强制）
1. Phase 0 — schema + expand pack + 剧本 UI  
2. Phase 1 — breakdown Job + 分镜 UI  
3. Phase 2 — TTSProvider（可先 Edge 冒烟，再接 VoxCPM）  
4. Phase 3 — render_compose + 成片页去 mock  

Edge 与 VoxCPM 均须在本规格验收内接通；允许实现顺序上 Edge 先于 VoxCPM，但合并前两者都要可选手动验证。

---

## 3. 数据模型

### 3.1 台词行（Scene / Frame 共用结构）

```json
{
  "id": "line_a1b2",
  "type": "dialogue",
  "speaker": "张三",
  "text": "你终于来了。",
  "emotion": "压抑、低声"
}
```

| 字段 | 约束 |
|---|---|
| `id` | 稳定 id；扩写时生成；分配到帧时**保留同一 id**（便于对账「场景台词是否全部分完」） |
| `type` | `dialogue` \| `narration` |
| `speaker` | dialogue 必填（可「众」等）；narration 可空或固定「旁白」 |
| `text` | 非空 |
| `emotion` | 可选短中文；供 TTS 提示或 VoxCPM 风格；Edge 可拼进 ssml/前置指令或忽略 |

`dialogue_count` / `narration_count`：**派生字段**，写入时由 `lines` 统计，不再作为 LLM 唯一真相。

### 3.2 SQLite

**`scenes` 迁移**  
- 新增 `lines_json TEXT NOT NULL DEFAULT '[]'`  

**`storyboard_frames` 迁移**  
- 新增 `lines_json TEXT NOT NULL DEFAULT '[]'`  
- 新增 `scene_id TEXT`（可空；breakdown 后应填写真实 scene id）  
- 现有 `scene` 字段：保留作展示名缓存或废弃读取；**新逻辑以 `scene_id` 为准**。API 响应可同时返回 `scene_id` 与场景名。

**成片结果（二选一，推荐 A）**  
- **A**：`projects` 或独立表 `renders`：`id, project_id, scene_id NULL, status, engine, output_url, duration_sec, error, created_at`  
- **B**：仅存在 Job `result_json`，成片页只读最近一次 completed `render_compose`  

推荐 **A**：刷新后列表稳定，不依赖翻 Job 历史。本规格采用 **`renders` 表**（轻量）。

### 3.3 Episode 语义（替换 mock 集数）

本轮不引入真实「多集剧集」产品模型：

- 成片左侧列表 = **项目下的场景**（`scenes`），一场景视为一「集/段落」。  
- 另提供「整片」虚拟项：`episode_id = __all__`，合成该项目全部已出图帧（按 `number` 排序）。  
- 单场景合成：仅 `scene_id` 匹配且有 `image_url` 的帧。

---

## 4. 剧本扩写（Phase 0）

### 4.1 Prompt pack
更新 `prompt_packs/script_expand_v1`（或 bump 为 `script_expand_v2` 并改默认路径）：

- 每个 scene 必须包含 `lines` 数组（可空数组，但不省略字段）。  
- 短剧/有对白的风格应尽量产出具体台词，而非只给 count。  
- `emotion` 简短；无则 `""`。  
- 示例 JSON 含 1–2 条 dialogue + 可选 narration。

### 4.2 `ScriptExpandService._normalize_scenes`
- 解析并规范化 `lines`（补 id、校验 type/text）。  
- `dialogue_count` / `narration_count` = 统计值。  
- 旧客户端若只认 count，行为兼容。

### 4.3 API / 前端
- `Scene` 模型增加 `lines`。  
- `PUT` 场景允许更新 `lines`（剧本工坊可改台词）。  
- `ScriptWorkshop`：场景卡片展示台词摘要；详情可展开编辑（不必一次做华丽编辑器，列表 + 简单文本够用）。

### 4.4 旧数据
- 已有场景 `lines_json='[]'`：不强制重跑；UI 提示「重新扩写/解析以生成台词」。  
- 不自动用 `description` 冒充台词（避免脏数据）；用户可手改 `lines`。

---

## 5. 分镜规划与台词分配（Phase 1）

### 5.1 新 Job：`storyboard_breakdown`
**输入 payload（示例）**:
```json
{
  "mode": "replace_empty",
  "scene_ids": null
}
```

| mode | 行为 |
|---|---|
| `replace_empty` | 仅当项目无帧或指定场景下无帧时生成；已有帧不覆盖（默认，防误伤出图） |
| `rebuild_scene` | 删除指定场景下无 `image_url` 的帧后重建；有图的帧保留，仅尝试补 `lines`（见下） |
| `assign_lines_only` | 不改帧结构，只把场景未分配 line id 分配到现有帧 |

**LLM 输出**（概念）: 每场景若干 shots/frames：`description`, `shot_type`, `duration`, `line_ids[]`（引用场景 line id）。  
服务端：校验 line_ids ⊆ 场景 lines；创建/更新帧并写入完整 `lines` 对象副本（含 id）。

### 5.2 分配完整性
- 目标：场景每条 line 至少出现在一帧（允许同一 line 不重复；默认不重复分配）。  
- 若 LLM 漏分：服务端把剩余 lines **追加到该场景最后一帧**（规则兜底），并打日志；不因此整 Job 失败。  
- 若某场景零帧：至少建 1 帧承载全部 lines。

### 5.3 与出图关系
- `storyboard_generate` 不变；只出图。  
- 规划 Job 不调用 ComfyUI。  
- 分镜页入口：「从剧本生成分镜」→ 创建 `storyboard_breakdown`；完成后 refetch frames。

### 5.4 现状缺口说明
当前仓库分镜帧默认可为空，前端仍有本地 SEED 回退。本规格要求：  
- 有后端帧时以 API 为准；  
- 逐步去掉「假 SEED 当作可合成素材」；无帧时空态引导去跑 breakdown。

---

## 6. TTS（Phase 2）

### 6.1 接口

```python
class TTSProvider(Protocol):
    def synthesize(self, *, text: str, emotion: str = "", speaker: str = "") -> bytes:
        """返回 wav/mp3 字节；实现内统一转 wav 供 ffmpeg。"""
```

- `EdgeTTSProvider`：`edge-tts`（或等价）异步封装为同步调用（worker 线程内 `asyncio.run` / 专用 loop）。  
- `VoxCPMProvider`：加载 `{MODELHUB_ROOT}/tts/VoxCPM2` 或仓库文档约定路径；模型单例懒加载；失败返回明确错误（权重缺失 → 503/Job failed 文案）。

### 6.2 引擎选择
- 默认引擎：可写配置（如 `tts_settings.json` 或扩展现有 settings）：`{"engine": "edge"|"voxcpm", "voice": "..."}`。  
- `render_compose` payload 可覆盖 `engine`。  
- 模型配置页 TTS Tab：真实「测试连接」——Edge 合成极短句；VoxCPM 检查权重可加载（或短句合成，注意耗时）。

### 6.3 单帧试听（推荐同规格）
- `POST /api/tts/preview`：`{ text, emotion?, engine? }` → 临时音频 URL 或字节流。  
- 不写 Job（短请求）；超时与错误可读。

### 6.4 情感
- Edge：能则映射语速/音高；不能则忽略 emotion，不失败。  
- VoxCPM：按库能力传入提示或前置文本；不能则忽略。

---

## 7. 成片合成（Phase 3）

### 7.1 Job：`render_compose`

**payload**:
```json
{
  "episode_id": "__all__",
  "scene_id": null,
  "engine": "edge",
  "voice_enabled": true,
  "subtitle_enabled": false,
  "resolution": "1080p",
  "fps": 24
}
```

**步骤**:
1. 解析帧列表（§3.3）；过滤无 `image_url` 的帧（跳过并记入 result 警告；若过滤后为空 → Job failed）。  
2. `voice_enabled=false`：每帧用 `duration`（默认 3s）静音。  
3. `voice_enabled=true`：对每帧 `lines` 顺序 TTS，拼接为帧音轨；若 lines 空则静音 `duration` 秒。  
4. 每帧画面时长 = `max(音轨时长, duration, 最小 0.5s)`。  
5. ffmpeg：图 → 视频片段 → concat；音轨对齐；`subtitle_enabled` 时用 frames 的 lines 生成 srt/ass 硬字幕（位置底部、白字即可，不做字体商店）。  
6. 输出到 ModelHub 或项目 media 目录；写 `renders` 行；Job `completed` + `result.output_url`。

### 7.2 API（替换 mock）

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/render/{project_id}/episodes` | 由 scenes + 可选 `__all__` 组装；status 来自最近 render |
| GET | `/api/render/{project_id}/episodes/{episode_id}` | 详情 |
| POST | `/api/jobs` type=`render_compose` | 推荐主入口（与工作台一致） |
| POST | `/api/render/{project_id}/render` | **薄封装**：创建 `render_compose` Job 并返回 `job_id`（兼容旧前端字段名） |
| GET | `/api/render/{project_id}/renders` | 历史成片列表 |
| GET | 旧 status 路径 | 映射为查 Job 状态，或 410 弃用并改前端只盯 Job |

暂停 BGM/音效相关请求：忽略或 501 文案「本轮未实现」。

### 7.3 前端 `FinalRender.jsx`
- 去掉假进度 `setInterval`；提交 Job + 依赖全局 jobs 条。  
- 集数列表接 episodes API。  
- 预览播放 `output_url`。  
- BGM/音效/高级选项：disabled + tooltip。  
- 字幕开关：仅控制 `subtitle_enabled`。  
- 引擎选择：Select Edge / VoxCPM。

### 7.4 依赖
- 系统需可用 `ffmpeg`（PATH 或配置项 `FFMPEG_PATH`）；缺失时 Job failed，错误明确「未安装 ffmpeg」。  
- Python：`edge-tts`；VoxCPM 按现有 `VoxCPM-main` / ModelHub 安装说明。

---

## 8. 错误处理

| 场景 | 行为 |
|---|---|
| 扩写 JSON 无 lines | 重试一次；仍无则 `lines=[]` 且 counts=0（可完成 Job，UI 提示贫乏） |
| breakdown 漏分台词 | 剩余追加末帧；Job 仍可 completed |
| Edge 网络失败 | Job failed，可改 VoxCPM 重试 |
| VoxCPM 权重缺失 | 测试连接/合成失败，文案含路径提示 |
| 无可用分镜图 | render Job failed |
| ffmpeg 不存在 | render Job failed |
| 仅部分帧有图 | 跳过无图帧并警告；若结果非空则 completed |

---

## 9. 测试要点

**Phase 0**  
- normalize：lines → counts；缺 id 自动补。  
- expand mock LLM 返回含 lines → DB `lines_json` 可读。  

**Phase 1**  
- breakdown：两场景三 lines → 帧上 line id 并集完整。  
- `assign_lines_only` 不删已有 `image_url`。  

**Phase 2**  
- Edge synthesize 返回非空字节（可 mock 子进程）。  
- VoxCPM：无权重时错误信息稳定（不瞎成功）。  

**Phase 3**  
- 两帧有图 + 台词 → ffmpeg 被调用（可 mock）→ render 行有 `output_url`。  
- `voice_enabled=false` 仍产出视频。  
- 前端契约：提交返回 `job_id`，不假装本地 100% 假进度。  

---

## 10. 文档与 README
- 根 README「当前状态」：成片拼片 + Edge/VoxCPM TTS + 场景台词结构化已真实；**真视频 / BGM / 音效 / 提示词库 / 认证**仍非目标或未做。  
- `.env.example`：`FFMPEG_PATH`、`VOXCPM_MODEL_DIR`（或复用 `MODELHUB_ROOT`）。  
- 注明：下一规格「真视频成片」另开。

---

## 11. 非目标回顾（防范围蔓延）
本规格不借机：接 LTX 工作流、重做监控暂停、模板中心、RAG 改造、多集剧集 CMS、完整调音台。

---

## 12. 对话决策摘要

| 项 | 选择 |
|---|---|
| 本轮 vs 真视频 | 只做静图拼片；真视频另规格 |
| TTS | Edge + VoxCPM 都接 |
| 台词结构 | lines[] + emotion |
| 音画 | 按帧配音 |
| 分配 | LLM breakdown 分到帧 |
| 成片附加 | 仅可选字幕；无 BGM/音效 |
| 架构 | 单 Job `render_compose` |
| 认证 | 不做 |
| 提示词库 | 本轮不做 |

---

## 13. 后续规格（预留，不在本文实现）

1. **真视频成片**：LTX/Wan 按帧或按镜头出动态片段 → 再拼接 + 复用本规格 TTS/字幕。  
2. **提示词模板库**真实化。  
3. BGM 上传混音、多集剧集模型、帧级试听工作流增强。  
4. chromadb 替换 JSON 向量回退（与本文无关）。  
