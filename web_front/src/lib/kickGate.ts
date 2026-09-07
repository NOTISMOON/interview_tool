/**
 * 顶号（session_kicked）弹窗状态门闩。
 *
 * 作用：当账号被其他设备顶下、已弹出"账号已在其他设备登录"提示框时，
 * 置位此标志，通知 axios 的 401 拦截器不要再硬跳转 /login——否则页面会在
 * 用户点击弹窗"确定"之前就被强制重定向，打断弹窗交互。
 *
 * 跳转动作统一由弹窗的"确定"按钮触发（见 DashboardLayout 中
 * session_kicked 处理），保证用户先看到提示、点确定后才离开当前页面。
 */

/** 顶号弹窗是否处于打开状态。 */
let kickDialogOpen = false;

/** 查询顶号弹窗是否已打开（供 401 拦截器判断是否跳过硬跳转）。 */
export function isKickDialogOpen(): boolean {
  return kickDialogOpen;
}

/** 设置顶号弹窗打开/关闭状态。 */
export function setKickDialogOpen(open: boolean): void {
  kickDialogOpen = open;
}