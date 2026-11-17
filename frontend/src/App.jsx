import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout.jsx'
import AdminLayout from './layouts/AdminLayout.jsx'

// 工作台页面
import ProjectList from './pages/workbench/ProjectList.jsx'
import ProjectCreate from './pages/workbench/ProjectCreate.jsx'
import ScriptWorkshop from './pages/workbench/ScriptWorkshop.jsx'
import AssetGeneration from './pages/workbench/AssetGeneration.jsx'
import Storyboard from './pages/workbench/Storyboard.jsx'
import FinalRender from './pages/workbench/FinalRender.jsx'

// 管理中心页面
import PromptManager from './pages/admin/PromptManager.jsx'
import RAGKnowledge from './pages/admin/RAGKnowledge.jsx'
import ModelConfig from './pages/admin/ModelConfig.jsx'
import SystemSettings from './pages/admin/SystemSettings.jsx'

// 监控面板页面
import MonitorDashboard from './pages/monitor/MonitorDashboard.jsx'

// 应用根组件
// 配置所有路由，使用 MainLayout 作为全局布局
function App() {
  return (
    <Routes>
      {/* 主布局路由，包含顶部导航栏 */}
      <Route path="/" element={<MainLayout />}>
        {/* 默认重定向到工作台项目列表 */}
        <Route index element={<Navigate to="/workbench" replace />} />

        {/* ===== 工作台模块 ===== */}
        <Route path="workbench" element={<ProjectList />} />
        <Route path="workbench/create" element={<ProjectCreate />} />
        <Route path="workbench/:projectId/script" element={<ScriptWorkshop />} />
        <Route path="workbench/:projectId/assets" element={<AssetGeneration />} />
        <Route path="workbench/:projectId/storyboard" element={<Storyboard />} />
        <Route path="workbench/:projectId/render" element={<FinalRender />} />

        {/* ===== 管理中心模块 ===== */}
        <Route path="admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="/admin/prompts" replace />} />
          <Route path="prompts" element={<PromptManager />} />
          <Route path="rag" element={<RAGKnowledge />} />
          <Route path="models" element={<ModelConfig />} />
          <Route path="settings" element={<SystemSettings />} />
        </Route>

        {/* ===== 监控面板 ===== */}
        <Route path="monitor" element={<MonitorDashboard />} />

        {/* 兜底路由：错误地址统一跳回工作台，避免白屏 */}
        <Route path="*" element={<Navigate to="/workbench" replace />} />
      </Route>
    </Routes>
  )
}

export default App
