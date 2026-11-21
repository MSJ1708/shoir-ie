export type ShoirIEJsonValue =
  | string | number | boolean | null | ShoirIEJsonValue[]
  | { [key: string]: ShoirIEJsonValue };
export interface ShoirIEClientOptions {
  edgeUrl: string; publishableKey: string; username: string; sessionToken: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}
export interface PlatformRecordPageOptions {
  recordType?: string; entityKey?: string; limit?: number; offset?: number;
  organizationId?: string; organizationWorkspaceId?: string;
}
export interface SavePlatformRecordOptions {
  recordType: string; entityKey: string; payload: Record<string, ShoirIEJsonValue>;
  organizationId?: string; organizationWorkspaceId?: string;
}
export interface WorkspaceLoadOptions {
  workspace?: string; organizationId?: string; organizationWorkspaceId?: string;
}
export class ShoirIEApiError extends Error { status: number; code: string; }
export class ShoirIEClient {
  constructor(options: ShoirIEClientOptions);
  listPlatformRecords(options?: PlatformRecordPageOptions): Promise<{
    ok: true; records: Array<Record<string, ShoirIEJsonValue>>;
    has_more: boolean; next_offset: number;
  }>;
  savePlatformRecord(options: SavePlatformRecordOptions): Promise<{
    ok: true; record: Record<string, ShoirIEJsonValue>;
  }>;
  loadWorkspace(options?: WorkspaceLoadOptions): Promise<{
    ok: true; state_json: string | null; updated_at?: string | null; revision?: number;
  }>;
}
export const SHOIR_IE_API_VERSION: "v1";
