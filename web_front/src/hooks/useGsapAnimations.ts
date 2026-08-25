import { useRef } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

/** 全局注册 GSAP 插件（仅执行一次） */
gsap.registerPlugin(useGSAP, ScrollTrigger);

/** 设置全局默认动画参数 */
gsap.defaults({
  duration: 0.6,
  ease: 'power2.out',
});

/**
 * 通用入场动画 Hook —— 子元素从下方淡入上移（使用 fromTo 确保动画终点明确）
 * @param stagger 每个子元素之间的延迟（秒）
 * @param y 初始 Y 偏移量（px）
 * @param duration 动画时长（秒）
 */
export function useFadeInUp(stagger = 0.1, y = 30, duration = 0.6) {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const children = containerRef.current?.children;
      if (!children || children.length === 0) return;

      gsap.fromTo(
        children,
        { y, opacity: 0 },
        { y: 0, opacity: 1, duration, stagger, ease: 'power3.out', clearProps: 'transform,opacity' },
      );
    },
    { scope: containerRef },
  );

  return containerRef;
}

/**
 * 滚动触发入场动画 Hook —— 元素滚动到视口时淡入上移
 * @param stagger 每个子元素之间的延迟（秒）
 * @param y 初始 Y 偏移量（px）
 * @param start 触发位置（如 "top 85%"）
 */
export function useScrollReveal(stagger = 0.1, y = 40, start = 'top 85%') {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const children = containerRef.current?.children;
      if (!children || children.length === 0) return;

      gsap.fromTo(
        children,
        { y, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.7,
          stagger,
          ease: 'power3.out',
          clearProps: 'transform,opacity',
          scrollTrigger: {
            trigger: containerRef.current,
            start,
            toggleActions: 'play none none none',
          },
        },
      );
    },
    { scope: containerRef },
  );

  return containerRef;
}

/**
 * 单个元素滚动触发动画 Hook
 * @param y 初始 Y 偏移量（px）
 * @param start 触发位置
 */
export function useScrollRevealSingle(y = 40, start = 'top 85%') {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!ref.current) return;
    gsap.fromTo(
      ref.current,
      { y, opacity: 0 },
      {
        y: 0,
        opacity: 1,
        duration: 0.7,
        ease: 'power3.out',
        clearProps: 'transform,opacity',
        scrollTrigger: {
          trigger: ref.current,
          start,
          toggleActions: 'play none none none',
        },
      },
    );
  });

  return ref;
}

/**
 * 英雄区入场动画 Hook —— 标题、描述、按钮、统计依次出现
 */
export function useHeroEntrance() {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!containerRef.current) return;
    const children = containerRef.current.children;
    if (children.length === 0) return;

    const tl = gsap.timeline({ defaults: { ease: 'power3.out', clearProps: 'transform,opacity' } });

    const targets = Array.from(children).filter((_, i) => i < 5);
    if (targets.length >= 1) {
      tl.fromTo(targets[0], { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7 });
    }
    if (targets.length >= 2) {
      tl.fromTo(targets[1], { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 }, '-=0.4');
    }
    if (targets.length >= 3) {
      tl.fromTo(targets[2], { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 }, '-=0.4');
    }
    if (targets.length >= 4) {
      tl.fromTo(targets[3], { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5 }, '-=0.3');
    }
    if (targets.length >= 5) {
      tl.fromTo(targets[4], { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5 }, '-=0.3');
    }
  }, { scope: containerRef });

  return containerRef;
}

/**
 * 数字递增动画 Hook
 * @param targetValue 目标值
 * @param duration 动画时长（秒）
 * @param suffix 后缀文本
 */
export function useCountUp(targetValue: number, duration = 2, suffix = '') {
  const ref = useRef<HTMLDivElement>(null);
  const animatedRef = useRef(false);

  useGSAP(() => {
    if (!ref.current || animatedRef.current) return;
    animatedRef.current = true;

    const obj = { val: 0 };
    gsap.to(obj, {
      val: targetValue,
      duration,
      ease: 'power2.out',
      onUpdate: () => {
        if (ref.current) {
          ref.current.textContent = `${Math.floor(obj.val).toLocaleString()}${suffix}`;
        }
      },
    });
  });

  return ref;
}

/**
 * 页面切换动画 Hook —— 容器从下方淡入上移
 */
export function usePageTransition() {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!containerRef.current) return;
    gsap.fromTo(
      containerRef.current,
      { y: 20, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.5, ease: 'power3.out', clearProps: 'transform,opacity' },
    );
  }, { scope: containerRef });

  return containerRef;
}

/**
 * 弹性缩放弹出动画 Hook
 */
export function useScaleIn(delay = 0) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!ref.current) return;
    gsap.fromTo(
      ref.current,
      { scale: 0.9, opacity: 0 },
      { scale: 1, opacity: 1, duration: 0.5, delay, ease: 'back.out(1.4)', clearProps: 'transform,opacity' },
    );
  });

  return ref;
}

/**
 * 交错入场 Hook —— 子元素依次淡入上移
 */
export function useStaggerEntrance(stagger = 0.08, y = 30, duration = 0.5, delay = 0) {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const children = containerRef.current?.children;
      if (!children || children.length === 0) return;

      gsap.fromTo(
        children,
        { y, opacity: 0 },
        { y: 0, opacity: 1, duration, stagger, delay, ease: 'power3.out', clearProps: 'transform,opacity' },
      );
    },
    { scope: containerRef },
  );

  return containerRef;
}

/**
 * 从左侧滑入动画 Hook
 */
export function useSlideInLeft(delay = 0) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!ref.current) return;
    gsap.fromTo(
      ref.current,
      { x: -60, opacity: 0 },
      { x: 0, opacity: 1, duration: 0.7, delay, ease: 'power3.out', clearProps: 'transform,opacity' },
    );
  });

  return ref;
}

/**
 * 从右侧滑入动画 Hook
 */
export function useSlideInRight(delay = 0) {
  const ref = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!ref.current) return;
    gsap.fromTo(
      ref.current,
      { x: 60, opacity: 0 },
      { x: 0, opacity: 1, duration: 0.7, delay, ease: 'power3.out', clearProps: 'transform,opacity' },
    );
  });

  return ref;
}