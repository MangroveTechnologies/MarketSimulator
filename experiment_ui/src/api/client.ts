import axios from 'axios'
import type { Dataset, Signal, ExperimentSummary, ResultsResponse, VisualizeResponse } from '../types'

const api = axios.create({ baseURL: '/api/v1' })

// Datasets
export const getDatasets = () => api.get<Dataset[]>('/datasets').then(r => r.data)

// Signals
export const getSignals = (type?: string) =>
  api.get<Signal[]>('/signals', { params: type ? { type } : {} }).then(r => r.data)

// Exec config defaults
export const getExecDefaults = () =>
  api.get<Record<string, any>>('/exec-config/defaults').then(r => r.data)

// Experiments
export const listExperiments = () =>
  api.get<ExperimentSummary[]>('/experiments').then(r => r.data)

export const createExperiment = (config: any) =>
  api.post('/experiments', config).then(r => r.data)

export const getExperiment = (id: string) =>
  api.get(`/experiments/${id}`).then(r => r.data)

export const validateExperiment = (id: string) =>
  api.post(`/experiments/${id}/validate`).then(r => r.data)

export const launchExperiment = (id: string) =>
  api.post(`/experiments/${id}/launch`).then(r => r.data)

export const pauseExperiment = (id: string) =>
  api.post(`/experiments/${id}/pause`).then(r => r.data)

// Results
export const queryResults = (id: string, params: Record<string, any> = {}) =>
  api.get<ResultsResponse>(`/experiments/${id}/results`, { params }).then(r => r.data)

export const getOhlcv = (expId: string, runIndex: number) =>
  api.get<{ ohlcv: import('../types').OHLCVCandle[] }>(`/experiments/${expId}/results/${runIndex}/ohlcv`).then(r => r.data)

export const visualizeResult = (expId: string, runIndex: number) =>
  api.get<VisualizeResponse>(`/experiments/${expId}/results/${runIndex}/visualize`).then(r => r.data)

// Templates
export const listTemplates = () =>
  api.get<{ name: string; description: string; search_mode: string; datasets_count: number }[]>('/templates').then(r => r.data)

export const getTemplate = (name: string) =>
  api.get<Record<string, any>>(`/templates/${name}`).then(r => r.data)

export const saveTemplate = (name: string, config: any) =>
  api.post('/templates', { name, config }).then(r => r.data)
