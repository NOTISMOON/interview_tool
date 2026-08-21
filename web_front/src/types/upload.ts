/** 文件上传相关类型定义（与后端 schemas/upload.py 字段对齐）。 */

/** 文件用途类型 */
export type FileType = 'resume' | 'avatar' | 'post_image';

/** 上传状态 */
export type UploadStatus = 'pending' | 'uploading' | 'completed' | 'failed';

/** STS 临时密钥请求参数 */
export interface StsTokenRequest {
  file_name: string;
  file_type: FileType;
  file_size: number;
  content_type: string;
}

/** STS 临时密钥响应 */
export interface StsTokenResponse {
  credentials: {
    tmp_secret_id: string;
    tmp_secret_key: string;
    session_token: string;
    expired_time: number;
  };
  cos_key: string;
  bucket: string;
  region: string;
  upload_url: string;
  expire_time: number;
}

/** 上传回调请求参数 */
export interface UploadCallbackRequest {
  cos_key: string;
  file_name: string;
  file_size: number;
  content_type: string;
  etag: string;
  location: string;
}

/** 上传回调响应 */
export interface UploadCallbackResponse {
  upload_id: number;
  cos_key: string;
  file_url: string;
  status: string;
  created_at: string;
}

/** 上传记录 */
export interface UploadRecord {
  upload_id: number;
  file_type: FileType;
  file_name: string;
  file_size: number;
  content_type: string;
  file_url: string;
  status: string;
  created_at: string;
}

/** 上传记录列表响应（分页） */
export interface UploadRecordListResponse {
  items: UploadRecord[];
  total: number;
  page: number;
  page_size: number;
}

/** 允许的文件类型（MIME → 扩展名映射） */
export const ALLOWED_FILE_TYPES: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'application/msword': ['.doc'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
};

/** 允许的文件扩展名列表（用于 accept 属性） */
export const ACCEPT_EXTENSIONS = '.pdf,.doc,.docx,.png,.jpg,.jpeg';

/** 最大文件大小（字节） */
export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

/**
 * 校验文件是否可上传（类型 + 大小）。
 * @param file 待校验的文件对象
 * @returns 错误提示文案，校验通过返回 null
 */
export function validateFile(file: File): string | null {
  const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  const allowedExts = ['.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg', '.gif', '.webp'];
  if (!allowedExts.includes(ext)) {
    return '仅支持 PDF、Word、图片格式（PNG/JPG/GIF/WebP）';
  }
  if (file.size > MAX_FILE_SIZE) {
    return '文件大小不能超过 10MB';
  }
  return null;
}

/** 格式化文件大小展示。 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
