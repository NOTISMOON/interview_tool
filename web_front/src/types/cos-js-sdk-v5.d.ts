/**
 * cos-js-sdk-v5 最小类型声明。
 * 官方包未随附 TypeScript 类型，此处仅声明本项目用到的 API。
 */

declare module 'cos-js-sdk-v5' {
  /** COS 临时密钥凭证（由后端 STS 接口下发） */
  interface CosAuthorization {
    TmpSecretId: string;
    TmpSecretKey: string;
    SecurityToken: string;
    ExpiredTime: number;
  }

  /** getAuthorization 回调参数（SDK 内部请求信息） */
  interface CosAuthOptions {
    Method?: string;
    Pathname?: string;
    [key: string]: unknown;
  }

  /** putObject 参数 */
  interface CosPutObjectParams {
    Bucket: string;
    Region: string;
    Key: string;
    Body: File | Blob | string;
    ContentType?: string;
    onProgress?: (info: { percent: number; speed: number; loaded: number; total: number }) => void;
    onTaskReady?: (taskId: string) => void;
  }

  /** putObject 成功结果 */
  interface CosPutObjectResult {
    statusCode: number;
    ETag: string;
    Location: string;
    headers: Record<string, string>;
  }

  /** COS 客户端实例 */
  interface CosInstance {
    putObject(
      params: CosPutObjectParams,
      callback: (err: { statusCode?: number; message?: string } | null, data?: CosPutObjectResult) => void,
    ): void;
    cancelTask(taskId: string): void;
  }

  /** COS 构造配置 */
  interface CosOptions {
    getAuthorization: (
      options: CosAuthOptions,
      callback: (credentials: CosAuthorization) => void,
    ) => void;
  }

  /** COS SDK 默认导出构造函数 */
  export default class COS implements CosInstance {
    constructor(options: CosOptions);
    putObject(
      params: CosPutObjectParams,
      callback: (err: { statusCode?: number; message?: string } | null, data?: CosPutObjectResult) => void,
    ): void;
    cancelTask(taskId: string): void;
  }
}
