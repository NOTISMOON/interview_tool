/**
 * 全局消息版本号 Context。
 *
 * 架构（按需求）：SSE / 私信 WS 收到任何新消息时，更新全局信息版本号，
 * 通过 React Context 下发给各页面；页面将版本号作为数据刷新依赖（useEffect），
 * 从而在"有新消息到来"时自动重新拉取对应用户数据，无需手动刷新。
 *
 * 用法：
 *   1. 在 main.tsx 用 <MessageVersionProvider> 包裹应用。
 *   2. 页面内 const { revision } = useMessageVersion();
 *      把 revision 加入刷新 useEffect 的依赖数组即可。
 *   3. 需要主动触发（如 ChatPage 收到 WS 新消息时）调用 bump()，
 *      让消息中心等共享同一版本域的页面同步刷新。
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { subscribeSSE } from '@/lib/sseBus';

/** 版本号 Context 值 */
interface MessageVersionContextValue {
  /** 全局递增版本号：任何消息事件到来即 +1 */
  revision: number;
  /** 主动触发版本号递增（供非 SSE 场景，如私信 WS 新消息） */
  bump: (kind?: string) => void;
  /** 最近一次消息事件类型（message / unread_count / system_broadcast 等） */
  lastKind: string | null;
}

const MessageVersionContext = createContext<MessageVersionContextValue>({
  revision: 0,
  bump: () => undefined,
  lastKind: null,
});

/**
 * 全局消息版本号 Provider。
 *
 * 内置订阅 sseBus 单例：任何 SSE 事件（通知 message、未读 unread_count、
 * 系统广播 system_broadcast 等）都会递增 revision 并记录 lastKind。
 *
 * @param children 子组件树。
 */
export const MessageVersionProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [revision, setRevision] = useState(0);
  const [lastKind, setLastKind] = useState<string | null>(null);
  // 用 ref 保存 lastKind 最新值，避免 bump 异步读取到陈旧值
  const lastKindRef = useRef<string | null>(null);

  /** 递增版本号并记录事件类型 */
  const bump = useCallback((kind?: string) => {
    setRevision((r) => r + 1);
    if (kind) {
      lastKindRef.current = kind;
      setLastKind(kind);
    }
  }, []);

  // 订阅全局 SSE：任何事件到达即 bump
  useEffect(() => {
    const unsubscribe = subscribeSSE((data) => {
      const kind = (data.kind as string) || 'message';
      bump(kind);
    });
    return unsubscribe;
  }, [bump]);

  const value = useMemo<MessageVersionContextValue>(
    () => ({ revision, bump, lastKind }),
    [revision, bump, lastKind],
  );

  return (
    <MessageVersionContext.Provider value={value}>{children}</MessageVersionContext.Provider>
  );
};

/**
 * 读取全局消息版本号。
 *
 * @returns { revision, bump, lastKind }。
 */
export function useMessageVersion(): MessageVersionContextValue {
  return useContext(MessageVersionContext);
}

export default MessageVersionProvider;