/**
 * HTTP 客户端。
 *
 * 职责：
 *   1. 统一注入 Authorization 头
 *   2. 拆开后端统一包体 {code, message, data, trace_id}，业务代码只拿 data
 *   3. 401 自动尝试刷新 token；刷新失败则跳登录
 *   4. 把后端错误码转成可读的中文提示
 */
import axios, { AxiosError, type AxiosInstance, type AxiosResponse } from 'axios'
import { ApiCode, type ApiResponse, type TokenPair } from './types'

const ACCESS_KEY = 'pile_lcm_access_token'
const REFRESH_KEY = 'pile_lcm_refresh_token'

export const tokenStore = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  save(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token)
    if (pair.refresh_token) localStorage.setItem(REFRESH_KEY, pair.refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/** 业务错误：携带后端错误码，便于调用方按码分支处理 */
export class ApiError extends Error {
  code: number
  traceId?: string | null

  constructor(code: number, message: string, traceId?: string | null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.traceId = traceId
  }
}

export const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// ---- 请求拦截：注入 token ----
http.interceptors.request.use((config) => {
  const token = tokenStore.access
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ---- 401 时的刷新逻辑（同一时刻只发一次刷新请求）----
let refreshing: Promise<string | null> | null = null

async function tryRefresh(): Promise<string | null> {
  const rt = tokenStore.refresh
  if (!rt) return null
  try {
    const resp = await axios.post<ApiResponse<TokenPair>>('/api/v1/auth/refresh', {
      refresh_token: rt,
    })
    const pair = resp.data?.data
    if (pair?.access_token) {
      tokenStore.save(pair)
      return pair.access_token
    }
    return null
  } catch {
    return null
  }
}

function redirectToLogin() {
  tokenStore.clear()
  if (!window.location.hash.includes('/login')) {
    window.location.hash = '#/login'
  }
}

// ---- 响应拦截：拆包 + 错误归一化 ----
http.interceptors.response.use(
  (resp: AxiosResponse<ApiResponse<unknown>>) => {
    const body = resp.data
    // 后端约定：HTTP 200 且 code === 0 才是成功
    if (body && typeof body.code === 'number' && body.code !== ApiCode.OK) {
      return Promise.reject(new ApiError(body.code, body.message || '请求失败', body.trace_id))
    }
    return resp
  },
  async (error: AxiosError<ApiResponse<unknown>>) => {
    const status = error.response?.status
    const body = error.response?.data

    // 401：尝试刷新一次后重放原请求
    if (status === 401 && error.config && !(error.config as any).__retried) {
      if (!refreshing) {
        refreshing = tryRefresh().finally(() => {
          refreshing = null
        })
      }
      const newToken = await refreshing
      if (newToken) {
        ;(error.config as any).__retried = true
        error.config.headers = error.config.headers ?? {}
        error.config.headers.Authorization = `Bearer ${newToken}`
        return http.request(error.config)
      }
      redirectToLogin()
      return Promise.reject(new ApiError(ApiCode.TOKEN_EXPIRED, '登录已过期，请重新登录'))
    }

    if (status === 401) {
      redirectToLogin()
      return Promise.reject(new ApiError(ApiCode.UNAUTHORIZED, '未登录或登录已过期'))
    }

    // 后端统一包体里的 code 优先
    if (body && typeof body.code === 'number') {
      return Promise.reject(new ApiError(body.code, body.message || '请求失败', body.trace_id))
    }

    const fallback =
      status === 403
        ? '没有权限执行此操作'
        : status === 404
          ? '请求的资源不存在'
          : status && status >= 500
            ? '服务器内部错误'
            : error.message || '网络异常'
    return Promise.reject(new ApiError(status ?? ApiCode.SERVER_ERROR, fallback))
  },
)

/** 便捷方法：直接返回 data */
export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const resp = await http.get<ApiResponse<T>>(url, { params })
  return resp.data.data as T
}

/**
 * GET 但返回完整包体（含 message）。
 *
 * 与 postFull 同理：有些 GET 接口的 message 承载了重要信息，
 * 例如交付完整性检查会回带"还有 N 道关卡未通过"，不能丢。
 */
export async function getFull<T>(
  url: string,
  params?: Record<string, unknown>,
): Promise<{ data: T; message: string }> {
  const resp = await http.get<ApiResponse<T>>(url, { params })
  return { data: resp.data.data as T, message: resp.data.message }
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  const resp = await http.post<ApiResponse<T>>(url, body)
  return resp.data.data as T
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  const resp = await http.patch<ApiResponse<T>>(url, body)
  return resp.data.data as T
}

export async function put<T>(url: string, body?: unknown): Promise<T> {
  const resp = await http.put<ApiResponse<T>>(url, body)
  return resp.data.data as T
}

/**
 * 返回完整包体（含 message）。
 *
 * 用于需要把后端提示语透传给用户的场景 ——
 * 例如发布文件时后端会回带"19 项设计输入参数因来源更新需要重新核验"，
 * 这条信息不能在前端被丢掉。
 */
export async function postFull<T>(
  url: string,
  body?: unknown,
): Promise<{ data: T; message: string }> {
  const resp = await http.post<ApiResponse<T>>(url, body)
  return { data: resp.data.data as T, message: resp.data.message }
}

export async function del<T>(url: string): Promise<T> {
  const resp = await http.delete<ApiResponse<T>>(url)
  return resp.data.data as T
}

/**
 * 把权限错误码翻译成人话。
 *
 * 后端刻意区分了"无角色"与"无数据范围"（契约要求），
 * 前端据此给出不同提示 —— 这直接决定用户能不能自己搞明白为什么看不到。
 */
export function explainApiError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case ApiCode.NO_ROLE:
        return '你不是该项目的参与人，请联系项目管理员把你加入项目'
      case ApiCode.NO_DATA_SCOPE:
        return '你的角色没有这项操作权限'
      case ApiCode.STAGE_DENIED:
        return '你的角色不覆盖该阶段'
      case ApiCode.TOKEN_EXPIRED:
      case ApiCode.UNAUTHORIZED:
        return '登录已过期，请重新登录'
      default:
        return err.message
    }
  }
  return err instanceof Error ? err.message : '未知错误'
}
