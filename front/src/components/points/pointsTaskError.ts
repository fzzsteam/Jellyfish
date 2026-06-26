import { ApiError } from '../../services/generated'

/**
 * 积分感知错误处理工具。
 *
 * 背景：文本/图片/视频生成走 executeAsyncTaskCreate，其内部会捕获 request 抛出的错误，
 * 调用 getErrorMessage(error, fallback) 取提示文案后统一 message.error 展示，且不会 rethrow。
 *
 * 本工具提供一个工厂 makePointsAwareGetErrorMessage(refresh)，返回一个 getErrorMessage，
 * 在内部识别后端返回的积分业务错误码并做相应处理：
 * - POINTS_QUOTE_CHANGED (HTTP 409)：积分价格在试算后发生变化 → 调用 refresh 重新试算，
 *   返回“积分价格已更新，请重新确认”，不自动重试。由 executeAsyncTaskCreate 统一展示。
 * - INSUFFICIENT_POINTS (HTTP 402)：可用积分不足 → 调用 refresh 刷新，返回“可用积分不足，请充值后再试”。
 * - 其余错误回退到调用方传入的 fallbackErrorMessage（与 executeAsyncTaskCreate 默认行为一致）。
 *
 * 设计取舍：因 executeAsyncTaskCreate 强制 message.error 展示返回串，这里直接返回语义文案，
 * 避免重复通知；refresh 始终触发以更新 quote_token / 可用额度。
 */

/** 解析 error 是否为积分相关的业务错误码；命中返回错误码，否则返回 null。 */
function extractPointsErrorCode(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null
  const data = error.body?.data as { error_code?: unknown } | undefined
  const code = data?.error_code
  return typeof code === 'string' ? code : null
}

/**
 * 构造一个积分感知的 getErrorMessage。
 *
 * @param refresh usePointsQuote 返回的 refresh，用于在报价失效/积分不足时立即重新试算。
 * @returns 供 executeAsyncTaskCreate 的 getErrorMessage 形参使用。
 */
export function makePointsAwareGetErrorMessage(
  refresh: () => void,
): (error: unknown, fallbackErrorMessage: string) => string {
  return (error, fallbackErrorMessage) => {
    if (error instanceof ApiError) {
      const code = extractPointsErrorCode(error)
      if (code === 'POINTS_QUOTE_CHANGED') {
        refresh()
        return '积分价格已更新，请重新确认'
      }
      if (code === 'INSUFFICIENT_POINTS') {
        refresh()
        return '可用积分不足，请充值后再试'
      }
      // 非积分业务错误：提取后端统一 ApiResponse 的 message 字段。
      // http_exception_handler 把所有 HTTPException 包成 { code, message, data: null }，
      // 因此用户可读的错误文案在 body.message 而非原始 FastAPI 的 body.detail。
      const msg = (error.body as { message?: unknown } | undefined)?.message
      if (typeof msg === 'string' && msg) {
        return msg
      }
    }
    return fallbackErrorMessage
  }
}
