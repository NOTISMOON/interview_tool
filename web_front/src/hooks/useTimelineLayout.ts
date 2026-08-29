/**
 * 时间线布局共享 Hook（社区 / 动态共用）。
 *
 * - useTimelineLayout：管理交错(alt)/单侧(single)布局，localStorage 记忆偏好。
 * - useTimelineReveal：时间线条目滚动浮现动画（IntersectionObserver + .tl-visible）。
 */
import { useCallback, useEffect, useState } from 'react';

/** 布局模式偏好存储 key */
const STORAGE_KEY = 'timeline_layout';

/**
 * 时间线布局模式（交错/单侧），切换后持久化到 localStorage。
 *
 * @param defaultLayout 默认布局（首次访问无存储时生效）。
 * @returns { layout, setLayout, layoutClass }。
 */
export function useTimelineLayout(defaultLayout: 'alt' | 'single' = 'alt') {
  const [layout, setLayoutState] = useState<'alt' | 'single'>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'single' || saved === 'alt') return saved;
    } catch {
      /* localStorage 不可用时忽略 */
    }
    return defaultLayout;
  });

  /** 切换布局并持久化偏好 */
  const setLayout = useCallback((v: 'alt' | 'single') => {
    setLayoutState(v);
    try {
      localStorage.setItem(STORAGE_KEY, v);
    } catch {
      /* 忽略存储失败 */
    }
  }, []);

  // 单侧模式时给 .timeline 追加 tl-single 类
  const layoutClass = layout === 'single' ? 'tl-single' : '';

  return { layout, setLayout, layoutClass };
}

/**
 * 时间线浮现动画：观察 .timeline 下的 .tl-item，进入视口时加 .tl-visible。
 *
 * 传入依赖数组（如 [posts.length]），数据变化（新增条目）时重新观察。
 *
 * @param deps 触发重新观察的依赖数组。
 */
export function useTimelineReveal(deps: unknown[] = []) {
  useEffect(() => {
    const items = document.querySelectorAll('.timeline .tl-item');
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('tl-visible');
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.05 },
    );
    items.forEach((el, i) => {
      // 前 2 条立即显示，避免首屏空白
      if (i < 2) {
        el.classList.add('tl-visible');
      } else {
        io.observe(el);
      }
    });
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
