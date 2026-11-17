# 身份参考净化与一致性预警设计

## 背景

现有 Flux Kontext 分镜链路已把永久身份与场景 Look State 分开编译，但 worker 仍把完整定妆图原样作为视觉参考上传。完整定妆图同时包含脸、旧服装、旧道具和旧背景，导致视觉条件压过文字条件：保脸时难以换装，换装或改场景时又容易换脸。

本设计增加一层独立的身份参考净化能力。系统从选定定妆图中提取只承担身份约束的参考图，Kontext 不再直接使用完整定妆图；生成完成后，本地模型为候选图提供身份相似度预警，但最终接受或拒绝仍由用户决定。

## 已确认的产品原则

1. 同一个人的脸优先级最高。允许改善妆容、皮肤质感、表情、光影和气质，但不能为了“更漂亮”改变脸型、五官比例或年龄感。
2. 身份参考采用双轨来源：默认自动提取；效果不好时允许手动裁切、上传标准身份照，或生成标准身份照候选并人工确认。
3. 自动相似度仅用于风险预警。系统不得依据分数自动接受、自动拒绝或绕过人工审核。
4. 人脸模型完全本地运行。模型不可用时降级为手动裁切和人工审核，不阻断现有分镜生成。
5. 不在本阶段引入 FaceID、InstantID 或新的强身份 ComfyUI 节点；数据结构为以后增强预留版本字段。

## 范围

### 本阶段包含

- 角色身份参考的自动提取、手动裁切、上传和人工确认。
- 标准身份照候选的生成与确认入口。
- Kontext 请求快照绑定身份参考版本和内容哈希。
- 单人和双人候选的人脸检测、特征比较与风险分级。
- 角色面板和分镜候选审核界面的身份信息展示。
- 本地模型缺失、检测失败和低质量输入的显式降级。
- 单元、接口、worker、前端构建与真实三图 A/B 验收。

### 本阶段不包含

- 自动替用户接受或拒绝候选。
- FaceID、InstantID、LoRA 训练或角色微调。
- 云端人脸识别服务。
- 修改 H3 提示词编译规则。
- 删除旧定妆图、旧候选图或历史请求。

## 架构

新增两个边界清晰的后端组件：

1. `IdentityReferenceService`：负责身份参考生命周期，包括检测、裁切、标准化、哈希和确认。它只依赖资产仓库、本地媒体目录与可选人脸后端。
2. `IdentityEvaluationService`：负责候选图人脸检测、单人/双人匹配、相似度计算和风险分级。它不改变渲染状态，只返回可审计的评估结果。

人脸后端定义为可替换接口。首个实现使用 OpenCV YuNet 检测人脸、SFace 生成特征；不可用实现返回结构化的 `unavailable` 状态。裁切和标准化使用本地图像处理库，不调用远端服务。

分镜编译器继续只负责编译不可变请求，不执行图像处理。worker 只使用请求快照中已经确认的身份参考 URL；候选图片下载成功后调用评估服务，并把结果写入渲染尝试。

## 数据模型

角色资产继续使用现有 `identity_json`，新增嵌套字段：

```json
{
  "identity_anchor": "stable textual facial identity",
  "stable_traits": ["facial_geometry", "age_impression", "stable_hairstyle", "body_build"],
  "reference": {
    "status": "ready",
    "source_type": "auto_crop",
    "source_image_url": "/media/assets/project/selected.png",
    "image_url": "/media/assets/project/identity/asset-id-v1.png",
    "image_hash": "sha256:...",
    "crop": {"x": 0.23, "y": 0.08, "width": 0.54, "height": 0.54},
    "face_count": 1,
    "quality": "good",
    "detector": "opencv-yunet-2023mar",
    "embedding_model": "opencv-sface-2021dec",
    "version": 1,
    "confirmed_at": "2026-08-28 23:00:00"
  },
  "reference_candidates": [
    {
      "id": "idref_abc123",
      "status": "pending",
      "source_type": "manual_crop",
      "image_url": "/media/assets/project/identity/idref_abc123.png",
      "image_hash": "sha256:...",
      "crop": {"x": 0.20, "y": 0.06, "width": 0.58, "height": 0.58},
      "face_count": 1,
      "quality": "good",
      "created_at": "2026-08-28 23:05:00"
    }
  ]
}
```

`source_type` 允许 `auto_crop`、`manual_crop`、`upload` 和 `generated`。裁切坐标均为相对原图的 0–1 数值，避免绑定具体分辨率。净化图固定输出为 768×768 无损 PNG。

`reference` 只表示当前已确认版本；`reference_candidates` 只保存尚未确认的候选。确认操作按候选 ID 原子地复制为新的 `reference`、递增版本并移除该候选，其他候选仍可供比较。候选图片文件不会因放弃或确认而自动删除，避免破坏审计记录。

`storyboard_render_attempts` 新增 `identity_evaluation_json TEXT NOT NULL DEFAULT '{}'`，结构如下：

```json
{
  "status": "scored",
  "model_fingerprint": "opencv-sface-2021dec",
  "characters": [
    {
      "character_asset_id": "asset_x",
      "character_name": "苏晚",
      "similarity": 0.57,
      "risk": "stable",
      "candidate_face": {"x": 0.12, "y": 0.10, "width": 0.31, "height": 0.46}
    }
  ],
  "warnings": []
}
```

请求快照中的 `CharacterIdentity` 新增 `reference_source_type`、`reference_version` 和净化图哈希。请求源哈希包含这些字段；身份参考更新后，旧请求自然变为过期，但历史记录保持原样。

不把人脸特征向量写入数据库或日志。特征只存在于单次本机计算的内存中，用后释放。

## 身份参考生成

### 自动提取

1. 读取选定角色资产的原始图片。
2. YuNet 检测所有人脸。
3. 没有人脸时返回 `manual_required`，不覆盖现有身份参考。
4. 多个人脸时优先选择面积最大且最接近画面中心的人脸，同时返回 `multiple_faces` 警告。
5. 根据检测框生成正方形裁切：左右扩展到脸宽的 1.6 倍；垂直扩展到脸高的 1.8 倍并向上偏移，保留完整头发、少量颈肩，最大限度减少服装和背景。
6. 裁切框超出图像时向内平移，不使用人工填充像素。
7. 输出 768×768 PNG，计算 SHA-256，保存为版本化文件。
8. 自动结果先成为待确认候选；用户确认后才替换当前身份参考。

### 手动裁切

前端提供可拖动、缩放的正方形裁切框，提交相对坐标。后端验证坐标范围、最小像素尺寸和图片归属，再使用与自动提取相同的标准化与哈希逻辑生成候选。手动候选也必须确认。

### 上传与标准身份照候选

上传图片必须是当前项目的本地媒体文件。后端检测人脸并显示质量信息，但不因低分自动拒绝。标准身份照生成通过现有 ComfyUI 客户端提交一个独立的角色资产任务，复用 Kontext 模型与身份参考上传能力，但不创建分镜帧或分镜渲染尝试。它使用“正脸、中性表情、无帽、简洁背景、肩部以上、保持相同脸部几何”的固定摄影指令；输出写入 `reference_candidates`，不会自动成为身份参考，必须经过并排对照和人工确认。

## Kontext 输入规则

- 有已确认且文件有效的净化身份图：只上传净化身份图。
- 没有净化身份图：继续使用旧完整定妆图，并在请求和界面标记 `legacy_full_reference`；这保证升级不阻断已有项目。
- 文本提示明确说明参考图只约束脸部身份、年龄感和稳定发型，不约束服装、背景、姿势或光线。
- Look State 明确列出本镜允许的服装、妆容、发态、伤势、湿润、污渍和疲劳变化。
- 双人场景最多上传两个强身份参考，继续使用当前 ReferenceLatent 链路。

## 身份评估

### 单人

检测候选图全部人脸，选择与参考特征相似度最高的一张作为匹配结果。若没有检测到脸，返回 `unscored` 和 `candidate_face_missing`。

### 双人

分别提取两个身份参考特征和候选图所有人脸特征。枚举不同候选脸的一对一分配，选择总相似度最高的组合；禁止两个身份绑定同一张候选脸。若候选脸不足两个，缺失角色返回 `unscored`。同时保存匹配框，便于界面验证左右位置和人物错配。

### 风险分级

- `similarity >= 0.50`：`stable`
- `0.35 <= similarity < 0.50`：`review`
- `similarity < 0.35`：`high_risk`
- 模型不可用或未检测到脸：`unscored`

阈值是首版经验值，随评估记录保存模型指纹，避免不同模型分数被错误横向比较。任何等级都不改变候选状态。

## API

在角色资产 API 下增加：

- `POST /api/assets/{project_id}/{asset_id}/identity-reference/auto`：生成自动裁切候选。
- `POST /api/assets/{project_id}/{asset_id}/identity-reference/crop`：按相对坐标生成手动裁切候选。
- `POST /api/assets/{project_id}/{asset_id}/identity-reference/upload`：登记并检测已上传的标准身份照候选。
- `POST /api/assets/{project_id}/{asset_id}/identity-reference/generate`：提交标准身份照渲染候选。
- `POST /api/assets/{project_id}/{asset_id}/identity-reference/confirm`：确认指定候选并递增版本。
- `GET /api/assets/{project_id}/{asset_id}/identity-reference`：返回当前参考、待确认候选、模型状态和警告。

分镜渲染状态接口在每个 attempt 中返回 `identity_evaluation`。现有接受、拒绝和重试接口保持兼容。

## 前端交互

角色面板新增“身份参考”区域：

- 左侧显示原定妆图，右侧显示当前身份参考或待确认候选。
- 提供自动提取、调整裁切、上传标准照和生成标准照操作。
- 待确认候选只能“设为身份参考”或“放弃”，不能静默替换。
- 明确显示来源、版本、检测质量、模型状态和 legacy 警告。

分镜候选审核区域新增：

- 每个角色的相似度、`stable`/`review`/`high_risk`/`unscored` 标签。
- 身份参考和候选脸裁切并排预览。
- 身份参考版本已变化时显示历史提示。
- 保留现有结构化拒绝原因，并突出 `identity_drift`、`wrong_look_state` 和 `wrong_composition`。

## 错误处理与兼容性

- 人脸依赖未安装：返回 `face_model_unavailable`，保留 legacy 完整参考路径。
- 模型文件缺失或哈希不符：返回 `face_model_unavailable`，不尝试联网静默下载。
- 原图不存在、越出媒体目录或格式错误：返回 `identity_reference_invalid`。
- 无人脸或裁切太小：返回 `identity_face_missing` 或 `identity_crop_invalid`，不覆盖当前参考。
- 评估异常只把评估标记为 `unscored`；已经成功生成的候选仍保持 `candidate`。
- 旧数据库通过增量迁移增加评估列；旧资产没有 `identity.reference` 时按 legacy 行为运行。

## 模型与部署

依赖使用 `opencv-contrib-python-headless`，模型采用 OpenCV Zoo 的 YuNet 与 SFace ONNX 文件。模型必须由显式安装步骤放入项目配置的本地模型目录，并记录文件哈希；运行时只检查，不自动下载。Pillow 用于确定性的裁切、颜色转换和 PNG 输出。

模型状态加入现有 readiness 接口，分别报告依赖、检测模型和识别模型是否可用。

## 测试与验收

### 自动测试

- 裁切数学：中心、边缘、超界平移、最小尺寸和 768×768 输出。
- 服务降级：依赖或模型缺失时返回稳定错误码且不覆盖参考。
- 身份参考确认：候选、版本递增、哈希变化和历史保留。
- 编译器：优先净化图、legacy 回退、参考版本进入请求源哈希。
- worker：上传净化图；评估失败不把候选改为 failed。
- 单人评分与双人一对一最优匹配。
- 仓库、迁移和 API 往返测试。
- 前端身份面板和候选风险展示的生产构建。

### 真实 A/B 验收

使用上一轮相同角色、场景与 Look State，对比完整定妆图路径和净化身份图路径：

1. 室内近景：眼型、鼻部、下颌和年龄感保持同一人，同时允许更自然精致的皮肤、妆容和光影。
2. 雨夜中景：保持同一人，并真实执行深色剪裁羊毛大衣，不复制旧连帽夹克。
3. 双人中远景：两个人物分别正确匹配，无换脸；前后景位置符合分镜要求。

三张图都保留请求快照、种子、模型指纹、身份参考版本、相似度与人工裁决。真实结果不因自动分数被强行判定通过。

## 完成条件

- 所有新增与现有后端测试通过。
- 前端生产构建通过。
- 人脸模型存在与缺失两种环境均验证。
- 真实 A/B 三图生成完成并留下结构化验收记录。
- 代码合并前不存在静默完整参考回退、静默模型下载或自动接受候选。
