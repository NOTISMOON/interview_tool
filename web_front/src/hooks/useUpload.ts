/**
 * useUpload Hook：封装"前端直传腾讯云 COS"完整流程。
 *
 * 流程: 前置校验 → 请求后端STS临时密钥 → cos-js-sdk-v5直传（进度回调）→
 *       回调后端校验落库 → 返回上传记录。
 * 支持: 上传进度、取消上传、错误分类提示。
 */

import { useCallback, useRef, useState } from 'react';
import axios from 'axios';
import COS from 'cos-js-sdk-v5';
import { getStsToken, uploadCallback } from '@/lib/api/upload';
import { validateFile } from '@/types/upload';
import type { FileType, UploadCallbackResponse } from '@/types/upload';

/** useUpload 返回值 */
interface UseUploadResult {
  /** 上传进度（0-100） */
  progress: number;
  /** 是否上传中 */
  uploading: boolean;
  /** 错误信息（最近一次） */
  error: string | null;
  /** 执行上传（含前置校验），成功返回后端落库的上传记录 */
  upload: (file: File) => Promise<UploadCallbackResponse>;
  /** 取消当前上传 */
  cancel: () => void;
}

/**
 * 从 axios 错误中提取用户可读提示（优先后端 detail，其次状态码兜底）。
 * @param err 捕获的异常
 */
function extractErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (err.response?.status === 429) return '今日上传次数已用完，请明天再试';
    if (err.response?.status === 401) return '登录已过期，请重新登录后再上传';
    return '上传服务异常，请稍后重试';
  }
  if (err instanceof Error && err.message) return err.message;
  return '上传失败，请重试';
}

/**
 * 文件上传 Hook（COS 前端直传）。
 * @param fileType 文件用途：resume（简历）/ avatar（头像）
 */
export function useUpload(fileType: FileType): UseUploadResult {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 当前上传任务ID（用于取消） */
  const taskRef = useRef<string | null>(null);
  /** 当前COS实例引用（取消任务必须使用发起上传的同一实例） */
  const cosRef = useRef<COS | null>(null);

  /** 取消当前上传任务 */
  const cancel = useCallback(() => {
    if (taskRef.current && cosRef.current) {
      cosRef.current.cancelTask(taskRef.current);
      taskRef.current = null;
    }
    setUploading(false);
    setProgress(0);
  }, []);

  /** 执行上传：校验 → STS → 直传 → 回调 */
  const upload = useCallback(
    async (file: File): Promise<UploadCallbackResponse> => {
      setError(null);
      setProgress(0);

      // 1. 前置校验（类型/大小）
      const invalidReason = validateFile(file);
      if (invalidReason) {
        setError(invalidReason);
        throw new Error(invalidReason);
      }

      setUploading(true);
      try {
        // 2. 请求后端获取STS临时密钥 + 上传路径
        const sts = await getStsToken({
          file_name: file.name,
          file_type: fileType,
          file_size: file.size,
          content_type: file.type || 'application/octet-stream',
        });

        // 3. 初始化COS实例（本次上传专用临时密钥）并记录引用供取消
        const cos = new COS({
          getAuthorization: (_options, callback) => {
            callback({
              TmpSecretId: sts.credentials.tmp_secret_id,
              TmpSecretKey: sts.credentials.tmp_secret_key,
              SecurityToken: sts.credentials.session_token,
              ExpiredTime: sts.credentials.expired_time,
            });
          },
        });
        cosRef.current = cos;

        // 4. 直传COS（进度回调 + 任务ID记录用于取消）
        const result = await new Promise<{ etag: string; location: string }>((resolve, reject) => {
          cos.putObject(
            {
              Bucket: sts.bucket,
              Region: sts.region,
              Key: sts.cos_key,
              Body: file,
              ContentType: file.type || 'application/octet-stream',
              onTaskReady: (taskId) => {
                taskRef.current = taskId;
              },
              onProgress: (info) => {
                setProgress(Math.round(info.percent * 100));
              },
            },
            (err, data) => {
              taskRef.current = null;
              if (err) {
                reject(new Error('文件上传到云存储失败，请重试'));
                return;
              }
              resolve({ etag: data?.ETag ?? '', location: data?.Location ?? '' });
            },
          );
        });

        // 5. 回调后端：三重校验 + 落库上传记录
        const record = await uploadCallback({
          cos_key: sts.cos_key,
          file_name: file.name,
          file_size: file.size,
          content_type: file.type || 'application/octet-stream',
          etag: result.etag,
          location: result.location,
        });
        setProgress(100);
        return record;
      } catch (err) {
        setError(extractErrorMessage(err));
        throw err;
      } finally {
        setUploading(false);
      }
    },
    [fileType],
  );

  return { progress, uploading, error, upload, cancel };
}
