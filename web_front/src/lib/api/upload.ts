/** 上传模块API客户端，对接后端 /api/v1/cos 端点。 */

import request from '@/lib/request';
import type {
  StsTokenRequest,
  StsTokenResponse,
  UploadCallbackRequest,
  UploadCallbackResponse,
  UploadRecordListResponse,
} from '@/types/upload';

/**
 * 获取 STS 临时密钥 + COS 上传路径。
 * @param params 文件名/用途/大小/MIME类型
 */
export async function getStsToken(params: StsTokenRequest): Promise<StsTokenResponse> {
  const { data } = await request.get<StsTokenResponse>('/cos/sts-token', { params });
  return data;
}

/**
 * 上传完成回调（后端三重校验并落库）。
 * @param body 直传结果（cos_key/元信息/etag/location）
 */
export async function uploadCallback(body: UploadCallbackRequest): Promise<UploadCallbackResponse> {
  const { data } = await request.post<UploadCallbackResponse>('/cos/callback', body);
  return data;
}

/**
 * 查询当前用户上传记录列表（分页）。
 * @param fileType 按用途过滤（resume/avatar），不传查全部
 * @param page 页码（从1开始）
 * @param pageSize 页大小
 */
export async function getUploadRecords(
  fileType?: string,
  page = 1,
  pageSize = 20,
): Promise<UploadRecordListResponse> {
  const { data } = await request.get<UploadRecordListResponse>('/cos/records', {
    params: { file_type: fileType, page, page_size: pageSize },
  });
  return data;
}

/**
 * 删除上传记录（同时删除 COS 文件）。
 * @param recordId 上传记录ID
 */
export async function deleteUploadRecord(recordId: number): Promise<void> {
  await request.delete(`/cos/records/${recordId}`);
}
