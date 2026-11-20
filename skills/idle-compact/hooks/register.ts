import type { EngineInterface, Register, Timer } from 'claude-code'

// The session's prompt cache lives 1 hour; compact at 90% of it (54 minutes).
const CACHE_TTL_MS = 60 * 60 * 1000
const DELAY_MS = CACHE_TTL_MS * 0.9
// A compacted conversation is about 20k-30k tokens, so smaller ones gain nothing.
const MIN_TOKENS = 100_000

async function compactIfLarge($: EngineInterface): Promise<void> {
  try {
    const { tokens } = (await $.session.usage()).context
    if (tokens === undefined) {
      $.ui.log('idle-compact: skipped: the context size is unknown')
      return
    }
    if (tokens < MIN_TOKENS) return
    const result = await $.session.compact()
    if (result.skip !== undefined) $.ui.log(`idle-compact: skipped: ${result.skip}`)
  } catch (error) {
    $.ui.log(`idle-compact: failed: ${String(error)}`)
  }
}

export const register: Register = on => {
  let timer: Timer | undefined

  on('turn.start', ($, e, next) => {
    if (e.agentId === undefined) timer?.cancel()
    return next(e)
  })

  on('turn.complete', ($, e, next) => {
    if (e.agentId === undefined) {
      timer?.cancel()
      timer = $.clock.after(DELAY_MS, () => void compactIfLarge($))
    }
    return next(e)
  })
}
