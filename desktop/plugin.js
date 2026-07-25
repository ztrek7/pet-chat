// Pet Chat — Hermes Desktop plugin.
//
// Two surfaces: a `/pet-chat` configuration route, and asynchronous capture
// that may show one quip bubble beside the in-window pet.
//
// The load-bearing property of this file is that **the normal Hermes send is
// never delayed and never altered**. The composer middleware copies the draft
// text, starts a request it never awaits, and synchronously returns the exact
// original draft object. Everything else — readiness, gating, the bubble — is
// downstream of a send that has already happened.
//
// Contract notes that are easy to get wrong:
//   * This file is loaded UNCOMPILED. JSX syntax will not parse; UI is built
//     with jsx()/jsxs() from react/jsx-runtime.
//   * Only '@hermes/plugin-sdk', 'react', and 'react/jsx-runtime' resolve.
//   * Colors come from theme variables only, so the page reskins with the app.
//   * The backend owns the provider/model pair. Nothing here writes routing to
//     plugin storage, and nothing here accepts a free-text model id.
//   * `ctx.rest` exposes no abort signal, so "abort" here means a bounded
//     timeout plus unconditional suppression of the result. See `invalidate()`.
import {
  Button,
  COMPOSER_AREAS,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  SegmentedControl,
  atom,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

export const PLUGIN_ID = 'pet-chat'
export const ROUTE_PATH = '/pet-chat'

// Bounds the renderer enforces locally even if the backend says otherwise.
const MAX_BUBBLE_CHARS = 200
const DEFAULT_DISMISS_MS = 8000
const DEFAULT_MAX_RESPONSE_AGE_MS = 10000
const REQUEST_TIMEOUT_MS = 12000

const ATTITUDES = [
  { id: 'snarky', label: 'Snarky' },
  { id: 'supportive', label: 'Supportive' },
  { id: 'dramatic', label: 'Dramatic' },
  { id: 'minimal', label: 'Minimal' }
]
const DEFAULT_ATTITUDE = 'snarky'

// Fixed disclosure required beside the model picker. Not a privacy panel, and
// it deliberately does not claim local execution.
const DISCLOSURE =
  'Quips send the submitted text to the selected provider; provider costs and provider-side behavior may apply.'

// Fixed, bounded copy. Raw exception text, prompt text, endpoints, and provider
// response bodies must never reach the UI, so every failure is mapped through
// this table and anything unrecognized falls back to a generic line.
const ERROR_COPY = {
  not_configured: 'No Quip model is selected. Configure Pet Chat first.',
  invalid_routing: 'The selected provider/model is unavailable. Choose another Quip model.',
  generation_unavailable: 'Quips are unavailable on this Hermes version.',
  generation_failed: 'The selected provider/model failed. No fallback was used.',
  invalid_output: 'The selected model returned unusable output.',
  sensitive_input: 'I did not send that prompt because it may contain a secret.',
  busy: 'I am still working on the previous quip.',
  cooldown: 'Quip cooldown is active; try again shortly.',
  backend_unreachable: 'Pet Chat could not reach its backend.',
  settings_conflict: 'Pet Chat settings changed elsewhere. Refresh and try again.',
  cost_check_unavailable: 'I could not verify this model’s cost. Nothing was saved.',
  invalid_attitude: 'That attitude is not available.',
  invalid_body: 'Pet Chat rejected that request.',
  settings_unwritable: 'Pet Chat could not write its settings.'
}
const GENERIC_ERROR = 'Pet Chat hit an unexpected problem.'

const NOTIFIED_KEY = 'configureNotified'

export function errorCopy(code) {
  return ERROR_COPY[code] || GENERIC_ERROR
}

// `ctx` is only handed to register(); the page components need its scoped REST
// door, so it is stashed here rather than threaded through props.
let pluginCtx = null

function rest(path, options) {
  if (!pluginCtx) return Promise.reject(new Error('backend_unreachable'))
  return pluginCtx.rest(path, options)
}

/** Normalize any thrown value into a safe error code. Never surfaces the error. */
export function toErrorCode(error) {
  const code = error && typeof error === 'object' ? error.code || error.error : null
  if (typeof code === 'string' && Object.prototype.hasOwnProperty.call(ERROR_COPY, code)) {
    return code
  }
  return 'backend_unreachable'
}

function useSettings() {
  const [state, setState] = useState({ status: 'loading', data: null, error: null })

  const load = useCallback((refresh) => {
    setState((prev) => ({ ...prev, status: prev.data ? 'refreshing' : 'loading' }))
    return rest(refresh ? '/settings?refresh=true' : '/settings')
      .then((data) => setState({ status: 'ready', data, error: null }))
      .catch((error) => setState({ status: 'error', data: null, error: toErrorCode(error) }))
  }, [])

  useEffect(() => {
    void load(false)
  }, [load])

  return [state, load, setState]
}

function Field(label, hint, children) {
  return jsxs('div', {
    className: 'flex flex-col gap-1.5',
    children: [
      jsx('div', { className: 'text-xs font-medium', children: label }),
      hint
        ? jsx('div', {
            className: 'text-[0.6875rem] text-(--ui-text-tertiary)',
            children: hint
          })
        : null,
      children
    ]
  })
}

function ModelPicker({ catalog, selected, onSelect, disabled }) {
  if (!catalog.length) {
    return jsx('div', {
      className:
        'rounded-[4px] border border-(--ui-stroke-secondary) p-3 text-xs text-(--ui-text-tertiary)',
      children:
        'No authenticated providers were found in this profile. Configure a provider in Hermes, then refresh.'
    })
  }

  return jsx('div', {
    className:
      'flex max-h-72 flex-col gap-3 overflow-y-auto rounded-[4px] border border-(--ui-stroke-secondary) p-2',
    children: catalog.map((group) =>
      jsxs(
        'div',
        {
          className: 'flex flex-col gap-1',
          children: [
            jsx('div', {
              className:
                'px-1 text-[0.625rem] font-medium tracking-wide text-(--ui-text-quaternary) uppercase',
              children: group.label
            }),
            jsx('div', {
              className: 'flex flex-col',
              children: group.models.map((model) => {
                const active =
                  selected &&
                  selected.provider === group.provider &&
                  selected.model === model.id
                return jsxs(
                  'button',
                  {
                    type: 'button',
                    disabled,
                    onClick: () => onSelect({ provider: group.provider, model: model.id }),
                    className: [
                      'flex items-center justify-between gap-2 rounded-[3px] px-2 py-1 text-left text-xs',
                      'disabled:cursor-default disabled:opacity-50',
                      active
                        ? 'bg-(--ui-accent)/15 text-(--ui-accent)'
                        : 'text-(--ui-text-secondary) hover:bg-(--ui-stroke-secondary)/40'
                    ].join(' '),
                    children: [
                      jsx('span', { className: 'truncate', children: model.label }),
                      active ? jsx('span', { children: 'selected' }) : null
                    ]
                  },
                  `${group.provider}/${model.id}`
                )
              })
            })
          ]
        },
        group.provider
      )
    )
  })
}

function PetChatPage() {
  const [state, load, setState] = useSettings()
  const [selected, setSelected] = useState(null)
  const [attitude, setAttitude] = useState(DEFAULT_ATTITUDE)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [pendingWarning, setPendingWarning] = useState(null)

  const data = state.data

  // Adopt saved values once they arrive. The picker starts unset and never
  // preselects a default, `auto`, or the primary model.
  useEffect(() => {
    if (!data) return
    setSelected(data.pair ? { provider: data.pair.provider, model: data.pair.model } : null)
    setAttitude(data.attitude || DEFAULT_ATTITUDE)
  }, [data])

  const save = useCallback(
    (confirmation) => {
      if (!selected || !data) return
      setSaving(true)
      setNotice(null)
      rest('/settings', {
        method: 'PUT',
        body: {
          provider: selected.provider,
          model: selected.model,
          attitude,
          base_revision: data.settings_revision,
          ...(confirmation ? { confirmation } : {})
        }
      })
        .then((next) => {
          setPendingWarning(null)
          setState({ status: 'ready', data: next, error: null })
          setNotice({ tone: 'ok', message: 'Saved.' })
          // Configuration changed, so the capture path's cached readiness is
          // now stale — refresh it rather than waiting for the next activation.
          void refreshReadiness()
        })
        .catch((error) => {
          const payload = error && typeof error === 'object' ? error : {}
          if (payload.error === 'confirmation_required' && payload.cost_warning) {
            setPendingWarning(payload.cost_warning)
            setNotice(null)
            return
          }
          setPendingWarning(null)
          setNotice({ tone: 'error', message: errorCopy(toErrorCode(error)) })
        })
        .finally(() => setSaving(false))
    },
    [attitude, data, selected, setState]
  )

  if (state.status === 'loading') {
    return jsx('div', {
      className: 'p-4 text-xs text-(--ui-text-tertiary)',
      children: 'Loading Pet Chat settings…'
    })
  }

  if (state.status === 'error') {
    return jsxs('div', {
      className: 'flex flex-col items-start gap-3 p-4',
      children: [
        jsx('div', { className: 'text-xs', children: errorCopy(state.error) }),
        jsx(Button, {
          size: 'xs',
          variant: 'secondary',
          onClick: () => void load(false),
          children: 'Retry'
        })
      ]
    })
  }

  const catalog = (data && data.catalog) || []
  const savedPairMissing = Boolean(data && data.pair && !data.pair_in_catalog)
  const unavailable = Boolean(data && data.generation_available === false)

  return jsxs('div', {
    className: 'flex h-full flex-col gap-5 overflow-y-auto p-4',
    children: [
      jsxs('div', {
        className: 'flex items-baseline justify-between gap-3',
        children: [
          jsx('h1', { className: 'text-sm font-medium', children: 'Pet Chat' }),
          jsx(Button, {
            size: 'xs',
            variant: 'ghost',
            disabled: state.status === 'refreshing',
            onClick: () => void load(true),
            children: state.status === 'refreshing' ? 'Refreshing…' : 'Refresh models'
          })
        ]
      }),

      unavailable
        ? jsx('div', {
            className:
              'rounded-[4px] border border-(--ui-stroke-secondary) px-3 py-2 text-xs text-(--ui-text-secondary)',
            children: errorCopy('generation_unavailable')
          })
        : null,

      savedPairMissing
        ? jsx('div', {
            className:
              'rounded-[4px] border border-(--ui-stroke-secondary) px-3 py-2 text-xs text-(--ui-text-secondary)',
            children: errorCopy('invalid_routing')
          })
        : null,

      Field(
        'Quip model',
        DISCLOSURE,
        jsx(ModelPicker, {
          catalog,
          selected,
          disabled: saving,
          onSelect: (pair) => {
            setPendingWarning(null)
            setNotice(null)
            setSelected(pair)
          }
        })
      ),

      Field(
        'Attitude',
        null,
        jsx(SegmentedControl, {
          options: ATTITUDES,
          value: attitude,
          onChange: (next) => {
            setPendingWarning(null)
            setAttitude(next)
          }
        })
      ),

      pendingWarning
        ? jsxs('div', {
            className:
              'flex flex-col gap-2 rounded-[4px] border border-(--ui-stroke-secondary) px-3 py-2',
            children: [
              jsx('div', {
                className: 'text-xs font-medium',
                children: 'This model is expensive'
              }),
              jsx('div', {
                className: 'text-[0.6875rem] whitespace-pre-wrap text-(--ui-text-secondary)',
                children: pendingWarning.message
              }),
              jsxs('div', {
                className: 'flex gap-2',
                children: [
                  jsx(
                    Button,
                    {
                      size: 'xs',
                      disabled: saving,
                      onClick: () => save({ warning_id: pendingWarning.warning_id }),
                      children: 'Save anyway'
                    },
                    'confirm'
                  ),
                  jsx(
                    Button,
                    {
                      size: 'xs',
                      variant: 'ghost',
                      onClick: () => setPendingWarning(null),
                      children: 'Cancel'
                    },
                    'cancel'
                  )
                ]
              })
            ]
          })
        : null,

      jsxs('div', {
        className: 'flex items-center gap-3',
        children: [
          jsx(Button, {
            size: 'xs',
            disabled: !selected || saving,
            onClick: () => save(null),
            children: saving ? 'Saving…' : 'Save'
          }),
          notice
            ? jsx('span', {
                className: [
                  'text-[0.6875rem]',
                  notice.tone === 'error'
                    ? 'text-(--ui-text-secondary)'
                    : 'text-(--ui-text-tertiary)'
                ].join(' '),
                children: notice.message
              })
            : null
        ]
      })
    ]
  })
}

// ---------------------------------------------------------------------------
// Readiness cache
// ---------------------------------------------------------------------------
//
// The renderer must not POST prompt text on a profile it knows cannot use it.
// `unknown` is treated as "do not send" and triggers an async refresh, so the
// first submission after activation errs toward silence rather than egress.

let readinessState = 'unknown'
let disposed = true

export function getReadiness() {
  return readinessState
}

function refreshReadiness() {
  if (disposed) return Promise.resolve('unknown')
  return rest('/status')
    .then((status) => {
      readinessState = status && typeof status.state === 'string' ? status.state : 'unknown'
      return readinessState
    })
    .catch(() => {
      readinessState = 'unknown'
      return readinessState
    })
}

// ---------------------------------------------------------------------------
// Bubble state
// ---------------------------------------------------------------------------

const $bubble = atom(null)

let requestSeq = 0
let latestRequestId = null
let expiryTimer = null

/**
 * Invalidate any in-flight request and clear the bubble.
 *
 * This is Pet Chat's "abort": `ctx.rest` accepts no AbortSignal, so an
 * outstanding request cannot be cancelled at the transport. Instead its id
 * stops being the latest, which makes its eventual response unconditionally
 * undisplayable. The request is additionally time-bounded by `timeoutMs`.
 */
export function invalidate() {
  latestRequestId = null
  if (expiryTimer) {
    clearTimeout(expiryTimer)
    expiryTimer = null
  }
  $bubble.set(null)
}

function showBubble(kind, text, dismissMs) {
  if (typeof text !== 'string') return false
  const trimmed = text.trim().slice(0, MAX_BUBBLE_CHARS)
  if (!trimmed) return false
  if (expiryTimer) clearTimeout(expiryTimer)
  $bubble.set({ kind, text: trimmed, at: Date.now() })
  expiryTimer = setTimeout(() => $bubble.set(null), dismissMs || DEFAULT_DISMISS_MS)
  return true
}

// ---------------------------------------------------------------------------
// Pet probe
// ---------------------------------------------------------------------------

/**
 * Locate the single visible in-window pet, or return null.
 *
 * The pet's root element carries no class, id, or data attribute — it is a
 * `position: fixed` div at `z-index: 60` wrapping the sprite `<canvas>`. That
 * z-index is unique to the pet across the whole app, which is what makes this
 * probe specific rather than merely plausible.
 *
 * Zero or multiple candidates fail closed. That also covers the popped-out
 * overlay case for free: core unmounts the in-window pet while the overlay
 * owns the mascot, so there is nothing to anchor to and no bubble appears.
 */
export function findPetRect(doc, view) {
  const documentRef = doc || (typeof document === 'undefined' ? null : document)
  const windowRef = view || (typeof window === 'undefined' ? null : window)
  if (!documentRef || !windowRef || typeof windowRef.getComputedStyle !== 'function') {
    return null
  }

  const found = []
  // Canvases are rare; divs are not. Starting from the sprite keeps this cheap
  // enough to run on every response.
  for (const canvas of documentRef.querySelectorAll('canvas')) {
    let node = canvas.parentElement
    while (node) {
      const style = windowRef.getComputedStyle(node)
      if (style.position === 'fixed' && String(style.zIndex) === '60') {
        if (
          style.visibility !== 'hidden' &&
          style.display !== 'none' &&
          Number(style.opacity) !== 0
        ) {
          const rect = node.getBoundingClientRect()
          if (rect.width > 0 && rect.height > 0 && !found.includes(node)) {
            found.push(node)
          }
        }
        break
      }
      node = node.parentElement
    }
  }

  if (found.length !== 1) return null
  return found[0].getBoundingClientRect()
}

// ---------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------

/**
 * Start a quip request for a submitted draft, or decline to.
 *
 * Never throws, never awaits, and never touches the draft. Returns the request
 * id when a request was actually started, otherwise null — the return value
 * exists for tests; the composer ignores it.
 */
export function beginQuip(draftText) {
  if (disposed) return null
  const text = typeof draftText === 'string' ? draftText : ''
  if (!text.trim()) return null

  // A newer submission always wins; nothing is ever queued.
  invalidate()

  const readiness = readinessState
  if (readiness !== 'ready') {
    // No prompt body leaves the renderer on a profile known to be unusable.
    // Readiness errors still deserve their bubble, and `unknown` refreshes
    // quietly so the next submission can decide correctly.
    if (readiness === 'unknown') {
      void refreshReadiness()
    } else if (ERROR_COPY[readiness]) {
      showBubble('error', errorCopy(readiness), DEFAULT_DISMISS_MS)
    }
    return null
  }

  const requestId = `w${++requestSeq}`
  const profileSnapshot = readProfile()
  const startedAt = Date.now()
  latestRequestId = requestId

  // Started, never awaited. The explicit .catch() is what keeps a transport
  // failure from becoming an unhandled rejection in the Desktop renderer.
  rest('/quip', {
    method: 'POST',
    body: { request_id: requestId, prompt: text },
    timeoutMs: REQUEST_TIMEOUT_MS
  })
    .then((response) => deliver(requestId, profileSnapshot, startedAt, response))
    .catch(() => deliver(requestId, profileSnapshot, startedAt, null))

  return requestId
}

function readProfile() {
  try {
    return host.state.profile.get()
  } catch {
    return null
  }
}

/**
 * Decide whether a response may be shown. Every gate is checked
 * unconditionally, including the profile identity comparison.
 */
export function deliver(requestId, profileSnapshot, startedAt, response) {
  if (disposed) return 'disposed'
  if (requestId !== latestRequestId) return 'stale'
  if (readProfile() !== profileSnapshot) {
    invalidate()
    return 'profile_changed'
  }

  const maxAge =
    response && typeof response.max_response_age_ms === 'number'
      ? response.max_response_age_ms
      : DEFAULT_MAX_RESPONSE_AGE_MS
  if (Date.now() - startedAt > maxAge) return 'expired'

  if (findPetRect() === null) return 'pet_missing'

  if (!response) {
    return showBubble('error', errorCopy('backend_unreachable'), DEFAULT_DISMISS_MS)
      ? 'error'
      : 'suppressed'
  }

  const dismissMs =
    typeof response.dismiss_ms === 'number' ? response.dismiss_ms : DEFAULT_DISMISS_MS

  if (typeof response.quip === 'string' && response.quip.trim()) {
    return showBubble('quip', response.quip, dismissMs) ? 'quip' : 'suppressed'
  }

  // A no-quip response is silent unless its reason is user-actionable.
  const reason = response.reason
  if (typeof reason === 'string' && ERROR_COPY[reason]) {
    return showBubble('error', errorCopy(reason), dismissMs) ? 'error' : 'suppressed'
  }
  return 'silent'
}

// ---------------------------------------------------------------------------
// Bubble rendering
// ---------------------------------------------------------------------------

function prefersReducedMotion() {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/** Clamp the bubble into the viewport without ever affecting layout. */
export function bubbleBox(petRect, viewport) {
  const width = Math.min(260, Math.max(160, viewport.width - 24))
  const estimatedHeight = 64
  const gap = 10
  let left = petRect.left + petRect.width / 2 - width / 2
  left = Math.max(12, Math.min(left, viewport.width - width - 12))
  let top = petRect.top - estimatedHeight - gap
  if (top < 12) top = Math.min(petRect.bottom + gap, viewport.height - estimatedHeight - 12)
  top = Math.max(12, top)
  return { left, top, width }
}

function QuipBubble() {
  const bubble = useValue($bubble)
  const [rect, setRect] = useState(null)

  useEffect(() => {
    if (!bubble) {
      setRect(null)
      return undefined
    }
    // The pet roams, so the anchor is re-read on a timer rather than once.
    const track = () => {
      const next = findPetRect()
      setRect(next)
      // The pet can leave while the bubble is up; that is a suppression case.
      if (next === null) $bubble.set(null)
    }
    track()
    const id = setInterval(track, 250)
    return () => clearInterval(id)
  }, [bubble])

  if (!bubble || !rect) return null

  const viewport = { width: window.innerWidth, height: window.innerHeight }
  const box = bubbleBox(rect, viewport)
  const reduced = prefersReducedMotion()

  return jsx('div', {
    role: 'status',
    style: {
      position: 'fixed',
      left: `${box.left}px`,
      top: `${box.top}px`,
      width: `${box.width}px`,
      zIndex: 61,
      pointerEvents: 'auto',
      transition: reduced ? 'none' : 'opacity 160ms ease-out'
    },
    children: jsx('button', {
      type: 'button',
      'aria-label': 'Dismiss Pet Chat bubble',
      onClick: () => $bubble.set(null),
      className: [
        'w-full cursor-pointer rounded-[6px] border px-2.5 py-1.5 text-left text-[0.6875rem] leading-snug',
        'border-(--ui-stroke-secondary) bg-(--ui-bg-elevated) shadow-sm',
        bubble.kind === 'error' ? 'text-(--ui-text-tertiary)' : 'text-(--ui-text-secondary)'
      ].join(' '),
      children: bubble.text
    })
  })
}

/**
 * One non-repeating nudge when the plugin is on but no pair is saved.
 * Only a dismissal marker is persisted — never routing.
 */
export function maybeNotifyConfigure(ctx, status) {
  if (!status || status.state !== 'not_configured') return false
  if (ctx.storage.get(NOTIFIED_KEY, false)) return false
  ctx.storage.set(NOTIFIED_KEY, true)
  host.notify({
    kind: 'info',
    message: 'Pet Chat is enabled, but no Quip model is selected. Configure Pet Chat to continue.',
    // NotificationAction is { label, onClick } — a palette contribution uses
    // `run`, a notification action does not. They are different shapes.
    action: { label: 'Configure', onClick: () => host.navigate(ROUTE_PATH) }
  })
  return true
}

export default {
  id: PLUGIN_ID,
  name: 'Pet Chat',
  // Opt-in: enabling the plugin is a separate, explicit user act from
  // installing it, and neither selects a provider or model.
  defaultEnabled: false,
  register(ctx) {
    pluginCtx = ctx
    disposed = false
    readinessState = 'unknown'

    const dispose = ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: ROUTE_PATH },
        render: () => jsx(PetChatPage, {})
      },
      {
        id: 'configure',
        area: PALETTE_AREA,
        data: {
          id: 'pet-chat.configure',
          label: 'Pet Chat: Configure',
          keywords: ['pet', 'chat', 'quip', 'model', 'attitude'],
          run: () => host.navigate(ROUTE_PATH)
        }
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        // The command palette is keyboard-only (mod+k / mod+p), so a
        // palette-only entry point makes configuration unreachable for anyone
        // who cannot send that chord — a remote desktop session that swallows
        // Cmd, or any keyboard without it. A clickable row is the difference
        // between "configurable" and "configurable if your keyboard cooperates".
        data: { path: ROUTE_PATH, label: 'Pet Chat', codicon: 'comment' }
      },
      {
        id: 'capture',
        area: COMPOSER_AREAS.middleware,
        // Late in the chain: every other middleware has had its say, so the
        // text captured here is the text actually being sent.
        order: 1000,
        data: {
          handler: (draft) => {
            // Wrapped so a fault in Pet Chat can never affect the real send,
            // and synchronous so the chain is not awaited on our account.
            try {
              beginQuip(draft && typeof draft.text === 'string' ? draft.text : '')
            } catch {
              /* capture is best-effort; the send is not */
            }
            return draft
          }
        }
      },
      {
        id: 'bubble',
        area: STATUSBAR_AREAS.right,
        order: 200,
        // The status bar is only a mount point that is always present; the
        // bubble itself is position: fixed, so it never affects layout.
        render: () => jsx(QuipBubble, {})
      }
    ])

    // Readiness on activation, so the first submission can decide correctly
    // and the one-time Configure notification can fire. No prompt text.
    void refreshReadiness().then(() =>
      ctx
        .rest('/status')
        .then((status) => maybeNotifyConfigure(ctx, status))
        .catch(() => {})
    )

    // A profile switch invalidates unconditionally: pending work is dropped
    // and the bubble is cleared before the new profile's readiness is known.
    const unsubscribeProfile = host.state.profile.subscribe(() => {
      invalidate()
      readinessState = 'unknown'
      void refreshReadiness()
    })

    return () => {
      disposed = true
      invalidate()
      unsubscribeProfile()
      dispose()
      pluginCtx = null
    }
  }
}
