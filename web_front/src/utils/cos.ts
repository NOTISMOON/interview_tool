/**
 * 构造 COS 对象的完整公网访问 URL。
 * 如果 URL 已是完整格式（以 https:// 开头），则原样返回；
 * 否则拼接待定 COS 存储桶域名前缀。
 *
 * 存储桶域名从 COS STS 接口返回的 upload_url 中提取，
 * 作为 fallback 保留在函数中，确保即使未传入 upload_url 也能正确拼接。
 *
 * @param urlOrKey  COS 对象 Key（如 images/1/xxx.png）或完整 URL
 * @param uploadUrl COS 存储桶基础域名，可选，不传时使用默认值
 * @returns 完整的 COS 对象公网访问 URL
 */
export function buildCosUrl(urlOrKey: string, uploadUrl?: string): string {
  if (!urlOrKey) return '';
  // 已经是完整 URL，直接返回
  if (urlOrKey.startsWith('https://') || urlOrKey.startsWith('http://')) {
    return urlOrKey;
  }
  const base = uploadUrl || 'https://test-1381433578.cos.ap-chengdu.myqcloud.com';
  const key = urlOrKey.startsWith('/') ? urlOrKey.slice(1) : urlOrKey;
  return `${base}/${key}`;
}