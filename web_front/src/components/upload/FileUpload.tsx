/**
 * FileUpload 文件上传组件：点击/拖拽选择文件，直传腾讯云 COS。
 *
 * 完整链路: 前置校验（类型/大小）→ 后端STS临时密钥 → SDK直传（进度）→
 *          后端回调校验落库 → onUploaded 回调通知业务层。
 */

import { useRef, useState } from 'react';
import type { DragEvent, ChangeEvent } from 'react';
import { InboxOutlined } from '@ant-design/icons';
import { useUpload } from '@/hooks/useUpload';
import { ACCEPT_EXTENSIONS, formatFileSize, validateFile } from '@/types/upload';
import type { FileType, UploadCallbackResponse } from '@/types/upload';
import { UploadError, UploadProgress } from './UploadProgress';

/** FileUpload 组件属性 */
interface FileUploadProps {
  /** 文件用途：resume（简历）/ avatar（头像） */
  fileType: FileType;
  /** 上传成功回调（返回后端落库的记录） */
  onUploaded?: (record: UploadCallbackResponse) => void;
  /** 上传失败回调（已提取的用户可读错误信息） */
  onError?: (message: string) => void;
}

/**
 * 文件上传组件（点击 + 拖拽，COS前端直传）。
 * @param props 文件用途与结果回调
 */
export function FileUpload({ fileType, onUploaded, onError }: FileUploadProps) {
  const { progress, uploading, error, upload, cancel } = useUpload(fileType);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  /** 待上传文件（选择后暂存，点击"确认上传"触发直传） */
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  /** 选择/拖入文件后的统一处理：校验并暂存 */
  const handleFile = (file: File | undefined | null) => {
    if (!file || uploading) return;
    const invalidReason = validateFile(file);
    if (invalidReason) {
      onError?.(invalidReason);
      return;
    }
    setPendingFile(file);
  };

  /** input change 事件处理 */
  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFile(e.target.files?.[0]);
    // 重置value允许重复选择同一文件
    e.target.value = '';
  };

  /** 拖拽事件处理（阻止默认行为避免浏览器打开文件） */
  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    handleFile(e.dataTransfer.files?.[0]);
  };

  /** 确认上传：触发直传流程 */
  const handleConfirmUpload = async () => {
    if (!pendingFile || uploading) return;
    try {
      const record = await upload(pendingFile);
      setPendingFile(null);
      onUploaded?.(record);
    } catch (err) {
      // 错误已由hook记录并透传onError
      onError?.(err instanceof Error ? err.message : '上传失败，请重试');
    }
  };

  return (
    <div>
      {/* 拖拽/点击选择区 */}
      <div
        role="button"
        tabIndex={0}
        aria-label="选择或拖拽文件到此处上传"
        onClick={() => !uploading && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B35]/50 ${
          dragOver ? 'border-[#FF6B35] bg-[#FFF3ED]' : 'border-[#E1E4E8] hover:border-[#FF6B35] hover:bg-[#FFF3ED]/50'
        } ${uploading ? 'pointer-events-none opacity-60' : ''}`}
      >
        <InboxOutlined className={`text-2xl mb-2 ${dragOver ? 'text-[#FF6B35]' : 'text-[#8B949E]'}`} />
        <p className="text-sm text-[#5F6B7A]">{dragOver ? '松开鼠标开始上传' : '点击选择或拖拽文件到此处'}</p>
        <p className="text-xs text-[#8B949E] mt-1">支持 PDF、Word、图片格式，不超过 10MB</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_EXTENSIONS}
          className="hidden"
          onChange={handleInputChange}
          aria-hidden="true"
        />
      </div>

      {/* 待上传文件预览 + 确认按钮 */}
      {pendingFile && !uploading && (
        <div className="mt-3 flex items-center gap-3 bg-[#F6F8FA] rounded-xl p-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[#0D1117] truncate">{pendingFile.name}</p>
            <p className="text-xs text-[#8B949E]">{formatFileSize(pendingFile.size)}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPendingFile(null)}
              className="text-xs text-[#5F6B7A] hover:text-[#0D1117] px-2 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B35]/40 rounded"
            >
              移除
            </button>
            <button
              type="button"
              onClick={handleConfirmUpload}
              className="bg-[#FF6B35] hover:bg-[#E85D26] text-white text-xs font-medium px-4 py-1.5 rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B35]/50"
            >
              确认上传
            </button>
          </div>
        </div>
      )}

      {/* 上传进度 + 错误提示 */}
      <UploadProgress percent={progress} uploading={uploading} onCancel={cancel} />
      <UploadError message={error ?? ''} />
    </div>
  );
}

export default FileUpload;
