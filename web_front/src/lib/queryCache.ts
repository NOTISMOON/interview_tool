/**
 * 轻量级请求结果缓存（模块级 TTL 缓存）。
 *
 * 用途：对"每次进入页面都会发起但数据变化不频繁"的请求做去重，
 * TTL 内直接返回缓存，避免重复网络请求；TTL 过期后重新拉取。
 */

/** 缓存项：数据 + 过期时间戳 */
interface CacheEntry {
  data: unknown;
  expireAt: number;
}

/** 模块级缓存 Map（key 为请求标识） */
const cache = new Map<string, CacheEntry>();

/**
 * 带缓存的请求执行器：TTL 内命中缓存返回，否则执行请求并写入缓存。
 *
 * @param key 缓存标识（建议用接口名+参数）。
 * @param ttlMs 缓存有效期（毫秒）。
 * @param fetcher 实际发起请求的函数。
 * @returns 请求结果（命中缓存时为缓存值）。
 */
export async function cachedFetch<T>(key: string, ttlMs: number, fetcher: () => Promise<T>): Promise<T> {
  const now = Date.now();
  const hit = cache.get(key);
  if (hit && hit.expireAt > now) {
    return hit.data as T;
  }
  const data = await fetcher();
  cache.set(key, { data, expireAt: now + ttlMs });
  return data;
}

/** 清除指定 key 的缓存（数据变更后调用，保证下次读取最新） */
export function invalidateCache(key: string): void {
  cache.delete(key);
}
