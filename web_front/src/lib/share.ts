/**
 * 分享工具：优先 Web Share API（需 secure context），否则复制到剪贴板。
 *
 * 背景：Web Share API（navigator.share）与 Clipboard API（navigator.clipboard）
 * 都要求 secure context（HTTPS 或 localhost）。部署环境为 http:// 时两者可能
 * 不可用，需做降级处理，避免分享静默失败。
 */

/** 分享结果：shared=系统分享面板，copied=已复制链接，failed=全部失败 */
export type ShareResult = 'shared' | 'copied' | 'failed';

/** 复制文本到剪贴板（Clipboard API → execCommand 兜底） */
async function copyToClipboard(text: string): Promise<boolean> {
  // 优先 Clipboard API（仅 secure context）
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 降级到 execCommand */
  }
  // 兜底：execCommand('copy')（http 下也可用）
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    ta.style.pointerEvents = 'none';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/**
 * 分享链接：返回 'shared'（系统分享面板已打开）/'copied'（已复制）/'failed'。
 *
 * @param opts 分享内容（url 必填，title/text 供系统分享面板展示）。
 */
export async function shareUrl(opts: { url: string; title?: string; text?: string }): Promise<ShareResult> {
  const { url, title, text } = opts;
  // Web Share API 仅 secure context 可用；http 下跳过直接走剪贴板
  if (navigator.share && window.isSecureContext) {
    try {
      await navigator.share({ title, text, url });
      return 'shared';
    } catch (err) {
      // 用户主动取消分享：视为成功（不打扰）
      if ((err as Error).name === 'AbortError') return 'shared';
      // 其他错误（NotAllowedError 等）降级到剪贴板
    }
  }
  const ok = await copyToClipboard(url);
  return ok ? 'copied' : 'failed';
}
