import { getJson } from './client'

export interface DownloadFile { name: string; platform: 'windows' | 'linux' | string; kind: string; label: string; size: number; sha256: string; url: string }
export interface DownloadManifest {
  available: boolean; engine_commit: string | null; built_at: string | null
  files: DownloadFile[]; checksums_url: string | null; note: string | null
}
export const listDownloads = () => getJson<DownloadManifest>('/downloads')
