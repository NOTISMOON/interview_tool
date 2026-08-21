import axios from 'axios';

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
  // 跨域请求自动携带HttpOnly Cookie（token存Cookie，JS不可读）
  withCredentials: true,
});

// 刷新会话单例：并发多个401时只触发一次刷新，其余等待复用结果
let refreshPromise: Promise<void> | null = null;

/** 调用刷新端点续期Cookie会话（无请求体，refresh_token由浏览器自动携带）。 */
function refreshSession(): Promise<void> {
  if (!refreshPromise) {
    // 使用独立的axios实例，避免经过下方响应拦截器造成递归刷新
    refreshPromise = axios
      .post('/auth/refresh', null, {
        baseURL: request.defaults.baseURL,
        withCredentials: true,
        timeout: 5000,
      })
      .then(() => undefined)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

request.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalConfig = error.config;
    // access_token过期（401）时自动刷新会话并重试原请求，仅重试一次防死循环
    if (error.response?.status === 401 && originalConfig && !originalConfig._retry) {
      originalConfig._retry = true;
      try {
        await refreshSession();
        return request(originalConfig);
      } catch {
        // 刷新也失败（会话彻底过期），清除本地用户信息并跳转登录页
        // 注意：/callback 是 GitHub OAuth 回调页，不能在此处跳转登录，否则会打断 OAuth 流程
        localStorage.removeItem('auth_user');
        const pathname = window.location.pathname;
        if (!pathname.includes('/login') && !pathname.includes('/callback')) {
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  },
);

export default request;