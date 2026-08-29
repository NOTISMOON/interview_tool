/** 签到模块API客户端，对接后端 /api/v1/checkin 端点。 */

import request from '@/lib/request';

export interface CheckinStatusResponse {
  signedIn: boolean;
  streak: number;
  totalDays: number;
}

/** 获取当前签到状态（今天是否已签、连续天数、总天数） */
export async function getCheckinStatus(): Promise<CheckinStatusResponse> {
  const { data } = await request.get<CheckinStatusResponse>('/checkin/status');
  return data;
}

/** 执行签到，返回更新后的签到状态 */
export async function doCheckin(): Promise<CheckinStatusResponse> {
  const { data } = await request.post<CheckinStatusResponse>('/checkin');
  return data;
}