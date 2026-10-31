import type { components } from './types'

export type Station = components['schemas']['Station']
export type StationPage = components['schemas']['StationPage']
export type ModelSeries = components['schemas']['ModelSeries']
export type Bracket = components['schemas']['Bracket']
export type Settlement = components['schemas']['Settlement']
export type Profile = components['schemas']['Profile']
export type PredictionRow = components['schemas']['PredictionRow']
export type JournalEntry = components['schemas']['JournalEntry']
export type JournalNew = components['schemas']['JournalNew']
export type Health = components['schemas']['Health']

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { signal, headers: { accept: 'application/json' } })
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(r.status, detail)
  }
  return (await r.json()) as T
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new ApiError(r.status, r.statusText)
  return (await r.json()) as T
}

export const api = {
  stations: (signal?: AbortSignal) => get<Station[]>('/api/stations', signal),
  station: (id: string, signal?: AbortSignal) =>
    get<StationPage>(`/api/station/${encodeURIComponent(id)}`, signal),
  journal: (id: string, signal?: AbortSignal) =>
    get<JournalEntry[]>(`/api/journal/${encodeURIComponent(id)}`, signal),
  addJournal: (entry: JournalNew) => post<JournalEntry>('/api/journal', entry),
  health: (signal?: AbortSignal) => get<Health>('/healthz', signal),
}
