# ============================================
# 幻帧工坊 VisionForge Studio - FastAPI 后端入口
# ============================================
# 这个文件是后端应用的入口点
# 运行方式：uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# ============================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# 导入各个 API 路由模块
# 这些模块在 app/api/ 目录下，每个模块负责一类 API
from app.api import projects, scripts, assets, identity_references, storyboard, storyboard_render, render, prompts, prompt_architecture, rag, models, monitor, settings_llm, jobs, tts, videos
from app.core.settings import settings
from app.db.connection import connect
from app.db.schema import migrate
from app.services.runtime import (
    fail_generating_entities,
    job_queue,
    queue,
    storyboard_render_worker,
)

# ============================================
# 创建 FastAPI 应用实例
# ============================================
# title: 应用名称（会显示在自动生成的 API 文档里）
# description: 应用描述
# version: 版本号
# docs_url: Swagger UI 文档地址（默认 /docs）
# redoc_url: ReDoc 文档地址（默认 /redoc）
app = FastAPI(
    title="幻帧工坊 VisionForge Studio API",
    description="AIGC 视频全流程生产平台 - 后端 API 服务",
    version="1.0.0",
    docs_url="/api/docs",      # Swagger UI 文档地址
    redoc_url="/api/redoc",    # ReDoc 文档地址
    openapi_url="/api/openapi.json",  # OpenAPI 规范 JSON 地址
)

# ============================================
# 配置 CORS（跨域资源共享）
# ============================================
# 前端运行在 3000 端口，后端运行在 8000 端口
# 不同端口属于不同源，需要配置 CORS 才能正常通信
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",   # Vite 默认端口
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,           # 允许携带 cookie
    allow_methods=["*"],              # 允许所有 HTTP 方法（GET/POST/PUT/DELETE 等）
    allow_headers=["*"],              # 允许所有请求头
)

# ============================================
# 注册 API 路由
# ============================================
# 每个路由模块都有自己的前缀，方便管理
# 例如：项目相关的 API 都在 /api/projects 下

# 项目管理 API
app.include_router(projects.router, prefix="/api/projects", tags=["项目管理"])

# 剧本工坊 API
app.include_router(scripts.router, prefix="/api/scripts", tags=["剧本工坊"])

# 资产生成 API
app.include_router(assets.router, prefix="/api/assets", tags=["资产生成"])
app.include_router(
    identity_references.router,
    prefix="/api/assets",
    tags=["人物身份引用"],
)

# 分镜故事板 API
app.include_router(storyboard.router, prefix="/api/storyboard", tags=["分镜故事板"])
app.include_router(
    storyboard_render.router,
    prefix="/api/storyboard",
    tags=["分镜候选审核"],
)

# 成片合成 API
app.include_router(render.router, prefix="/api/render", tags=["成片合成"])

# MiniMax 视频生成 API
app.include_router(videos.router, prefix="/api/videos", tags=["视频生成"])

# 提示词模板 API
app.include_router(prompts.router, prefix="/api/prompts", tags=["提示词模板"])
app.include_router(prompt_architecture.router, prefix="/api/prompts", tags=["提示词架构"])

# 系统设置 API（LLM 等）
app.include_router(settings_llm.router, prefix="/api/settings", tags=["系统设置"])

# 后台任务 API
app.include_router(jobs.router, prefix="/api/jobs", tags=["后台任务"])

# TTS API
app.include_router(tts.router, prefix="/api/tts", tags=["TTS 配音"])

# RAG 知识库 API
app.include_router(rag.router, prefix="/api/rag", tags=["RAG 知识库"])

# 模型配置 API
app.include_router(models.router, prefix="/api/models", tags=["模型配置"])

# 监控面板 API
app.include_router(monitor.router, prefix="/api/monitor", tags=["监控面板"])


# ============================================
# 静态资源挂载（生成图片）
# ============================================
settings.assets_output_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/media",
    StaticFiles(directory=str(settings.media_mount_dir)),
    name="media",
)


# ============================================
# 根路径 - 健康检查
# ============================================
# 访问 http://localhost:8000/ 可以确认服务是否正常运行
@app.get("/", summary="健康检查")
async def root():
    """
    健康检查接口
    
    返回服务状态信息，用于确认后端是否正常运行
    """
    return {
        "status": "ok",
        "service": "幻帧工坊 VisionForge Studio API",
        "version": "1.0.0",
        "docs": "访问 /api/docs 查看 API 文档",
    }


# ============================================
# 应用启动事件
# ============================================
# 应用启动时会执行这里的代码
# 可以用来初始化数据库连接、加载模型等
@app.on_event("startup")
async def startup_event():
    migrate(connect())
    n_jobs = job_queue.bootstrap_fail_stale()
    n_ents = fail_generating_entities()
    queue.start()
    job_queue.start()
    storyboard_render_worker.start()
    print("asset worker started")
    print("job worker started")
    print("storyboard render worker started")
    if n_jobs or n_ents:
        print(f"reconcile: failed stale jobs={n_jobs} entities={n_ents}")
    print("=" * 50)
    print("幻帧工坊 VisionForge Studio API 启动成功！")
    print("=" * 50)
    print(f"API 文档地址: http://localhost:8000/api/docs")
    print(f"健康检查地址: http://localhost:8000/")
    print("=" * 50)


# ============================================
# 应用关闭事件
# ============================================
# 应用关闭时会执行这里的代码
# 可以用来关闭数据库连接、清理资源等
@app.on_event("shutdown")
async def shutdown_event():
    storyboard_render_worker.stop()
    job_queue.stop()
    queue.stop()
    print("storyboard render worker stopped")
    print("job worker stopped")
    print("asset worker stopped")
    print("幻帧工坊 VisionForge Studio API 已关闭")
