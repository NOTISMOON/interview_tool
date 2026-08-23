/**
 * 面试记录页（真实后端对接：GET /interviews 分页列表）。
 *
 * 展示当前用户全部面试记录：进行中可继续、已完成看报告、已中断只读。
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Pagination } from 'antd';
import {
  CalendarOutlined,
  RightOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  ReloadOutlined,
  PauseCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { getInterviewList, INTERVIEW_TYPE_LABEL } from '@/lib/api/interview';
import type { ApiInterviewListItem } from '@/lib/api/interview';

/** 状态标签样式（0-进行中 1-已完成 2-已中断） */
const STATUS_META: Record<number, { label: string; cls: string }> = {
  0: { label: '进行中', cls: 'bg-[#FFF8E6] text-[#BF8700]' },
  1: { label: '已完成', cls: 'bg-[#ECFDF3] text-[#2DA44E]' },
  2: { label: '已中断', cls: 'bg-[#F6F8FA] text-[#5F6B7A]' },
};

const PAGE_SIZE = 20;

const HistoryPage = () => {
  const navigate = useNavigate();
  const { message } = App.useApp();

  const [items, setItems] = useState<ApiInterviewListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  /** 拉取面试记录列表 */
  const loadList = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await getInterviewList(p, PAGE_SIZE);
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error('加载面试记录失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    loadList(page);
  }, [page, loadList]);

  /** 点击记录：进行中/已中断 → 会话页（恢复或展示中断态）；已完成 → 报告页 */
  const handleOpen = (item: ApiInterviewListItem) => {
    if (item.status === 0 || item.status === 2) {
      navigate(`/dashboard/interview/session/${item.interview_id}`);
      return;
    }
    navigate(`/dashboard/report/${item.interview_id}`);
  };

  const formatDate = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleString('zh-CN', {
          year: 'numeric', month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit',
        })
      : '';

  const formatDuration = (sec: number | null) => {
    if (!sec) return '—';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m} 分 ${s} 秒` : `${s} 秒`;
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0 flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-[#0D1117]">面试记录</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => loadList(page)}
            className="text-sm text-[#5F6B7A] font-medium hover:text-[#0D1117] transition-colors inline-flex items-center gap-1"
          >
            <ReloadOutlined /> 刷新
          </button>
          <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">
            <PlayCircleOutlined /> 开始面试
          </button>
        </div>
      </div>

      {loading && items.length === 0 ? (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 flex justify-center">
          <LoadingOutlined className="text-2xl text-[#D0D7DE]" />
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white border border-[#E1E4E8] rounded-2xl p-16 text-center">
          <FileTextOutlined className="text-5xl text-[#E1E4E8] mb-4" />
          <h3 className="text-base font-semibold text-[#0D1117] mb-2">暂无面试记录</h3>
          <p className="text-sm text-[#5F6B7A] mb-6">完成一次 AI 模拟面试后，记录将显示在这里</p>
          <button onClick={() => navigate('/dashboard/interview')} className="btn-flame">开始首次面试</button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-3">
          {items.map((item) => {
            const meta = STATUS_META[item.status] ?? STATUS_META[2];
            const score = item.total_score;
            const scoreColor = score === null ? '#8B949E' : score >= 85 ? '#2DA44E' : score >= 70 ? '#FF6B35' : score >= 60 ? '#BF8700' : '#CF222E';
            return (
              <div
                key={item.interview_id}
                onClick={() => handleOpen(item)}
                className="bg-white border border-[#E1E4E8] rounded-xl p-4 flex items-center hover:border-[#FF6B35]/30 hover:shadow-sm transition-all cursor-pointer"
              >
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold flex-shrink-0"
                  style={{ backgroundColor: `${scoreColor}15`, color: scoreColor }}
                >
                  {item.status === 0 ? (
                    <PauseCircleOutlined />
                  ) : score !== null ? (
                    Math.round(score)
                  ) : (
                    '—'
                  )}
                </div>
                <div className="flex-1 ml-4 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-[#0D1117] truncate">
                      {INTERVIEW_TYPE_LABEL[item.type] ?? '模拟面试'}
                    </h4>
                    <span className="tag tag-flame">{INTERVIEW_TYPE_LABEL[item.type] ?? '面试'}</span>
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${meta.cls}`}>
                      {meta.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mt-1 flex-wrap">
                    <span className="text-xs text-[#8B949E] inline-flex items-center gap-1">
                      <CalendarOutlined /> {formatDate(item.interview_time || item.created_at)}
                    </span>
                    <span className="text-xs text-[#8B949E] inline-flex items-center gap-1">
                      <CheckCircleOutlined /> {item.question_count} 题
                      {item.answered_count > 0 && item.status === 0 ? `（已答 ${item.answered_count}）` : ''}
                    </span>
                    {item.follow_up_count > 0 && (
                      <span className="text-xs text-[#8B949E] inline-flex items-center gap-1">
                        <ClockCircleOutlined /> 追问 {item.follow_up_count} 次
                      </span>
                    )}
                    {item.total_duration !== null && (
                      <span className="text-xs text-[#8B949E]">{formatDuration(item.total_duration)}</span>
                    )}
                    {item.status === 1 && !item.report_ready && (
                      <span className="text-xs text-[#BF8700]">报告生成中…</span>
                    )}
                  </div>
                </div>
                <RightOutlined className="text-[#E1E4E8] text-xs ml-4" />
              </div>
            );
          })}
          {total > PAGE_SIZE && (
            <div className="flex justify-center pt-2 pb-4">
              <Pagination
                current={page}
                pageSize={PAGE_SIZE}
                total={total}
                showSizeChanger={false}
                onChange={(p) => setPage(p)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default HistoryPage;
