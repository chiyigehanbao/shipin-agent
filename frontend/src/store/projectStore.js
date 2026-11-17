import { create } from 'zustand'
import { projectsApi } from '../services/api.js'

const TYPE_LABELS = {
  short_drama: '短剧',
  comic_drama: '漫剧',
  video: '视频',
  drama: '短剧',
  comic: '漫剧',
}

function mapProject(p) {
  return {
    id: p.id,
    name: p.name,
    type: p.type,
    typeLabel: TYPE_LABELS[p.type] || p.type,
    style: p.style || '未设置',
    status: p.status,
    progress: p.progress ?? 0,
    cover: null,
    updatedAt: (p.updated_at || '').split(' ')[0] || '',
    episodes: p.episode_count ?? 1,
    description: p.description || '',
    currentStep: p.current_step ?? 1,
  }
}

const useProjectStore = create((set, get) => ({
  currentProject: null,
  currentStep: 1,
  projects: [],
  projectsLoading: false,

  setCurrentProject: (project) => set({ currentProject: project }),

  setCurrentStep: (step) => set({ currentStep: step }),

  fetchProjects: async () => {
    set({ projectsLoading: true })
    try {
      const list = await projectsApi.list()
      const projects = list.map(mapProject)
      set({ projects, projectsLoading: false })
      return projects
    } catch (e) {
      set({ projectsLoading: false })
      throw e
    }
  },

  createProject: async (name, type) => {
    const created = await projectsApi.create({
      name,
      type,
      description: '',
      style: '未设置',
    })
    const newProject = mapProject(created)
    set((state) => ({
      projects: [newProject, ...state.projects],
      currentProject: newProject,
      currentStep: 1,
    }))
    return newProject
  },
}))

export default useProjectStore
