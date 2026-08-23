/**
 * 面试模块标签页唯一标识（客户端租约 tab_id，后端 §5.6 epoch 机制）。
 *
 * 必须在每次页面加载时无条件生成新 tab_id，不能用 Navigation Timing
 * 区分刷新/复制——实测 Chrome「复制标签页」的 navigation type 是
 * reload 且 sessionStorage 被原样复制到新标签页，若 reload 保留旧值，
 * 两个标签页将持有相同 tab_id：后端视为同一客户端（同 tab_id 幂等
 * 返回、epoch 不增长、不广播接管），双开互斥完全失效，两边可同时
 * 答题导致状态错乱。
 *
 * 无条件生成的行为推演（后端 Lua：同 tab_id 幂等返回，新 tab_id 接管
 * epoch+1 并广播 taken_over）：
 *   - 复制标签页：新页新 tab_id → epoch+1 → 旧页收 taken_over 降级只读 ✓
 *   - F5 刷新：同页新 tab_id → epoch+1（接管自己，无害）→ 其他标签页
 *     若存在则正确降级；自己的 SSE 事件被 tab_id 过滤不吃掉 ✓
 *   - SPA 路由切换：不触发页面加载，模块常量在标签页生命周期内稳定 ✓
 */

const STORAGE_KEY = 'interview_tab_id';

/** 生成一个随机标签页标识。 */
function generateTabId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `tab-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function resolveTabId(): string {
  const id = generateTabId();
  if (typeof sessionStorage !== 'undefined') {
    try {
      sessionStorage.setItem(STORAGE_KEY, id);
    } catch {
      // 隐私模式等写入失败不影响（内存常量仍有效）
    }
  }
  return id;
}

/** 当前标签页唯一标识（页面加载时生成，标签页生命周期内不变）。 */
export const TAB_ID = resolveTabId();
