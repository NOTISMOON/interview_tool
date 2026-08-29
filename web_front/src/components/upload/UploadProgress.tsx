/**
 * 上传进度条组件：展示上传百分比 + 取消按钮。
 */

import { CloseCircleFilled } from '@/components/icons';

/** UploadProgress 组件属性 */
interface UploadProgressProps {
  /** 上传进度（0-100） */
  percent: number;
  /** 是否上传中 */
  uploading: boolean;
  /** 取消上传回调 */
  onCancel: () => void;
}

/**
 * 上传进度条组件。
 * @param props 进度/上传状态/取消回调
 */
export function UploadProgress({ percent, uploading, onCancel }: UploadProgressProps) {
  if (!uploading) return null;
  return (
    <div className="mt-3" aria-live="polite" role="status">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-[#666666]">正在上传… {percent}%</span>
        <button
          type="button"
          onClick={onCancel}
          className="text-xs text-[#F53535] hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#F53535]/40 rounded"
        >
          取消上传
        </button>
      </div>
      <div
        className="h-2 bg-[#EEEEEE] rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="上传进度"
      >
        <div
          className="h-full bg-[#D9A441] rounded-full transition-[width] duration-200"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

/** 上传错误提示组件。 */
export function UploadError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs text-[#F53535]" role="alert">
      <CloseCircleFilled />
      {message}
    </p>
  );
}
