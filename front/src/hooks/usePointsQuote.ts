import { useCallback, useEffect, useRef, useState } from 'react'
import { PointsService } from '../services/generated'
import type { PointsQuoteResponse } from '../services/generated'

/**
 * usePointsQuote 入参。
 *
 * - businessType: 业务类型标签（如 script_simplify），仅用于流水归因与 quote_token 绑定。
 * - category: 模型类别，决定计价规则。
 * - modelId: 显式模型 ID；文本/图片场景通常传 null 由后端按用户默认模型解析。
 * - durationSeconds / resolution: 仅视频类别使用。
 * - enabled: 是否参与试算（例如资产智能检测在描述为空时不试算）。
 */
export type UsePointsQuoteParams = {
  businessType: string
  category: 'text' | 'image' | 'video'
  modelId?: string | null
  durationSeconds?: number | null
  resolution?: '720p' | '1080p' | null
  enabled?: boolean
}

/**
 * usePointsQuote 返回值。
 *
 * - quote: 最近一次成功的试算结果（含 quote_token）；未试算或失败时为 null。
 * - quoteToken: 透传给生成接口 requestBody 的 quote_token，取自 quote。
 * - loading: 是否有试算请求在途。
 * - error: 试算失败时的用户可见文案（成功时为 null）。
 * - canSubmit: 综合判定当前是否允许提交（enabled 且非 loading 且无错误且积分充足）。
 * - refresh: 强制立即重新试算；用于提交失败且后端返回积分价格已变更/积分不足时刷新凭证。
 */
export type UsePointsQuoteResult = {
  quote: PointsQuoteResponse | null
  quoteToken: string | null
  loading: boolean
  error: string | null
  canSubmit: boolean
  refresh: () => void
}

/** 防抖等待时长（毫秒）：文本试算便宜且稳定，取较短值避免感知卡顿。 */
const DEBOUNCE_MS = 400

/**
 * 防抖积分试算 Hook。
 *
 * 监听业务类型/模型/视频参数变化，在 DEBOUNCE_MS 延迟后向后端 POST /points/quote 获取
 * 本次生成的积分消耗与 quote_token，并以竞态安全的方式落盘最新结果。
 *
 * 竞态安全：每次发起请求自增 reqIdRef；响应返回时若其 reqId 已过期（组件已卸载或
 * 更新参数触发了新请求），则直接丢弃，避免慢响应覆盖新报价。
 */
export function usePointsQuote(params: UsePointsQuoteParams): UsePointsQuoteResult {
  const { businessType, category, modelId, durationSeconds, resolution, enabled = true } = params
  const [quote, setQuote] = useState<PointsQuoteResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 最新请求序号；响应比对自身序号决定是否落盘，防止过期响应覆盖新结果。
  const reqIdRef = useRef(0)
  // 防抖定时器句柄。
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // 手动触发计数；递增后会让 effect 立即重排一次试算（用于 refresh）。
  const [manualTick, setManualTick] = useState(0)

  const refresh = useCallback(() => {
    setManualTick((n) => n + 1)
  }, [])

  useEffect(() => {
    if (!enabled) {
      // 关闭试算：清空已缓存结果，canSubmit 必为 false。
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      reqIdRef.current += 1
      setQuote(null)
      setLoading(false)
      setError(null)
      return
    }

    const currentReqId = (reqIdRef.current += 1)
    setLoading(true)
    setError(null)

    timerRef.current = setTimeout(() => {
      timerRef.current = null
      PointsService.quoteMyPointsApiV1PointsQuotePost({
        requestBody: {
          business_type: businessType,
          category,
          model_id: modelId ?? null,
          duration_seconds: durationSeconds ?? null,
          resolution: resolution ?? null,
          generation_count: 1,
        },
      })
        .then((res) => {
          // 过期响应：直接丢弃。
          if (currentReqId !== reqIdRef.current) return
          const data = res.data ?? null
          if (data) {
            setQuote(data)
            setError(null)
          } else {
            // ApiResponse 壳异常（无 data 字段），按失败处理。
            setQuote(null)
            setError('暂时无法计算积分')
          }
        })
        .catch(() => {
          if (currentReqId !== reqIdRef.current) return
          setQuote(null)
          // 试算失败：canSubmit 会因 error 非空而为 false，阻断本次提交。
          setError('暂时无法计算积分')
        })
        .finally(() => {
          if (currentReqId === reqIdRef.current) {
            setLoading(false)
          }
        })
    }, DEBOUNCE_MS)

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
    // manualTick 用于 refresh 触发重排；不直接读取其值。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessType, category, modelId, durationSeconds, resolution, enabled, manualTick])

  // 组件卸载时废弃所有在途响应。
  useEffect(() => {
    return () => {
      reqIdRef.current += 1
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [])

  const canSubmit = !!enabled && !loading && !error && !!quote && quote.sufficient
  const quoteToken = quote?.quote_token ?? null

  return { quote, quoteToken, loading, error, canSubmit, refresh }
}
