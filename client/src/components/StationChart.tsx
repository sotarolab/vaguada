import { useEffect, useMemo, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import type { StationPage } from '../api/client'

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
export const CHART_HEIGHT = 360

export const MODEL_STYLE: Record<string, { label: string; color: string; group: 'CONUS' | 'Global' | 'NWS' }> = {
  nbm: { label: 'NBM', color: '#f2c14e', group: 'CONUS' },
  hrrr: { label: 'HRRR', color: '#e5484d', group: 'CONUS' },
  gfs: { label: 'GFS', color: '#7e8794', group: 'Global' },
  ifs: { label: 'ECMWF IFS', color: '#22c55e', group: 'Global' },
  icon: { label: 'ICON', color: '#a3e635', group: 'Global' },
  nws: { label: 'NWS', color: '#ff5c8a', group: 'NWS' },
}
const DEFAULT_HIDDEN = ['icon']
const STORAGE = 'station.hidden'

function loadHidden(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE)
    if (raw) return new Set(JSON.parse(raw) as string[])
  } catch { /* no storage: the default */ }
  return new Set(DEFAULT_HIDDEN)
}
function saveHidden(h: Set<string>) {
  try { localStorage.setItem(STORAGE, JSON.stringify([...h])) } catch { /* nothing to do */ }
}

/** Wheel over the plot zooms the time axis around the cursor; drag selects, double click resets. */
export function wheelZoom(factor = 0.75): uPlot.Plugin {
  return {
    hooks: {
      ready: (u) => {
        const over = u.over
        over.addEventListener(
          'wheel',
          (e) => {
            e.preventDefault()
            const rect = over.getBoundingClientRect()
            const left = e.clientX - rect.left
            const xs = u.data[0]
            const dMin = xs[0], dMax = xs[xs.length - 1]
            const oRange = u.scales.x.max! - u.scales.x.min!
            const nRange = Math.min(dMax - dMin, e.deltaY < 0 ? oRange * factor : oRange / factor)
            const xVal = u.posToVal(left, 'x')
            let nMin = xVal - (left / rect.width) * nRange
            let nMax = nMin + nRange
            if (nMin < dMin) { nMin = dMin; nMax = dMin + nRange }
            if (nMax > dMax) { nMax = dMax; nMin = dMax - nRange }
            u.setScale('x', { min: nMin, max: nMax })
          },
          { passive: false },
        )
      },
    },
  }
}

interface Props {
  page: StationPage
  height?: number
}

/**
 * Observed temperature and every model's latest run on one axis, in station time, with a
 * NOW line. The legend on the right toggles lines; the choice survives a reload. Every
 * number drawn comes from the page as given; the component only maps values to pixels.
 */
export function StationChart({ page, height = CHART_HEIGHT }: Props) {
  const el = useRef<HTMLDivElement>(null)
  const range = useRef<[number, number] | null>(null)
  const [hidden, setHiddenState] = useState<Set<string>>(loadHidden)
  const setHidden = (f: (h: Set<string>) => Set<string>) =>
    setHiddenState((h) => { const n = f(h); saveHidden(n); return n })
  const toggle = (k: string) => setHidden((h) => { const n = new Set(h); if (n.has(k)) n.delete(k); else n.add(k); return n })
  const on = (k: string) => !hidden.has(k)
  const tz = page.station.tz
  const models = useMemo(() => page.models.filter((s) => MODEL_STYLE[s.model]), [page.models])

  useEffect(() => {
    const host = el.current
    if (!host) return
    const obs = page.observed['t2m']
    const xs = new Set<number>(obs?.t ?? [])
    for (const s of models) for (const t of s.t) xs.add(t)
    const x = [...xs].sort((a, b) => a - b)
    if (x.length === 0) return
    const at = new Map(x.map((t, i) => [t, i]))
    const blank = () => Array.from({ length: x.length }, () => null as number | null)
    const column = (t: number[], values: (number | null)[]) => {
      const out = blank()
      t.forEach((ti, i) => { out[at.get(ti)!] = values[i] ?? null })
      return out
    }
    const lines: { data: (number | null)[]; opts: uPlot.Series }[] = []
    if (obs) lines.push({ data: column(obs.t, obs.values), opts: { label: 'Observed', stroke: css('--obs'), width: 2, spanGaps: true, points: { show: true, size: 5 }, show: on('obs') } })
    for (const s of models) {
      const st = MODEL_STYLE[s.model]
      lines.push({ data: column(s.t, s.values), opts: { label: st.label, stroke: st.color, width: s.model === 'nws' ? 1.8 : 1.5, dash: s.model === 'nws' ? undefined : [2, 3], spanGaps: true, points: { show: false }, show: on(s.model) } })
    }
    const data: uPlot.AlignedData = [x, ...lines.map((l) => l.data)]
    const now = Date.now() / 1000
    let tip: HTMLDivElement | null = null
    let focused: number | null = null
    const opts: uPlot.Options = {
      width: host.clientWidth,
      height,
      tzDate: (t) => uPlot.tzDate(new Date(t * 1e3), tz),
      legend: { show: false },
      cursor: { y: false, focus: { prox: 12 } },
      plugins: [wheelZoom()],
      axes: [
        {
          stroke: css('--dim'), grid: { stroke: css('--rule') }, ticks: { show: false }, font: `11px ${css('--mono')}`,
          values: (_u, vals) => vals.map((t) => {
            const d = uPlot.tzDate(new Date(t * 1e3), tz)
            const h = d.getHours()
            return h === 0 ? d.toLocaleDateString([], { weekday: 'short' }) : `${h % 12 || 12}${h < 12 ? 'am' : 'pm'}`
          }),
        },
        { stroke: css('--dim'), grid: { stroke: css('--rule') }, ticks: { show: false }, size: 40, font: `11px ${css('--mono')}`, values: (_u, vals) => vals.map((v) => `${v}°`) },
      ],
      series: [{}, ...lines.map((l) => l.opts)],
      hooks: {
        init: [(u) => { tip = document.createElement('div'); tip.className = 'tip'; u.over.appendChild(tip) }],
        setSeries: [(_u, sidx, sopts) => { if ((sopts as { focus?: boolean }).focus != null) focused = sidx }],
        draw: [(u) => {
          const xp = u.valToPos(now, 'x', true)
          if (xp < u.bbox.left || xp > u.bbox.left + u.bbox.width) return
          const ctx = u.ctx
          ctx.save(); ctx.strokeStyle = css('--now'); ctx.setLineDash([4, 4]); ctx.lineWidth = 1.5
          ctx.beginPath(); ctx.moveTo(xp, u.bbox.top); ctx.lineTo(xp, u.bbox.top + u.bbox.height); ctx.stroke(); ctx.restore()
        }],
        setCursor: [(u) => {
          if (!tip) return
          const idx = u.cursor.idx
          const label = focused != null && focused > 0 ? u.series[focused].label : null
          const v = idx != null && focused != null ? (u.data[focused][idx] as number | null | undefined) : null
          if (idx == null || v == null || !label) { tip.style.display = 'none'; return }
          const d = new Date(u.data[0][idx] * 1e3)
          const when = d.toLocaleString([], { weekday: 'short', hour: 'numeric', timeZone: tz })
          tip.textContent = `${label} ${v.toFixed(1)}° · ${when}`
          tip.style.display = 'block'
          const left = u.valToPos(u.data[0][idx], 'x')
          const top = u.valToPos(v, 'y')
          const flip = left > u.over.clientWidth * 0.7
          tip.style.left = `${left + (flip ? -10 : 10)}px`
          tip.style.top = `${top - 10}px`
          tip.style.transform = flip ? 'translateX(-100%)' : ''
        }],
        setScale: [(u, key) => {
          if (key !== 'x') return
          const lo = u.scales.x.min!, hi = u.scales.x.max!
          range.current = lo <= x[0] && hi >= x[x.length - 1] ? null : [lo, hi]
        }],
      },
    }
    const u = new uPlot(opts, data, host)
    if (range.current && range.current[0] >= x[0] && range.current[1] <= x[x.length - 1]) u.setScale('x', { min: range.current[0], max: range.current[1] })
    const onResize = () => u.setSize({ width: host.clientWidth, height })
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); u.destroy() }
  }, [page, hidden, height, tz, models])

  const groups: { title: string; items: { key: string; label: string; color: string; note?: string }[] }[] = [
    { title: 'Station', items: [{ key: 'obs', label: 'Observed', color: 'var(--obs)' }, ...models.filter((s) => s.model === 'nws').map((s) => ({ key: 'nws', label: 'NWS', color: MODEL_STYLE.nws.color, note: runStamp(s.run_at, tz) }))] },
    { title: 'CONUS models', items: models.filter((s) => MODEL_STYLE[s.model].group === 'CONUS').map((s) => ({ key: s.model, label: MODEL_STYLE[s.model].label, color: MODEL_STYLE[s.model].color, note: runStamp(s.run_at, tz) })) },
    { title: 'Global models', items: models.filter((s) => MODEL_STYLE[s.model].group === 'Global').map((s) => ({ key: s.model, label: MODEL_STYLE[s.model].label, color: MODEL_STYLE[s.model].color, note: runStamp(s.run_at, tz) })) },
  ]
  return (
    <div className="chart-row">
      <div ref={el} className="chart" />
      <div className="picker-panel">
        {groups.map((g) => (
          <div key={g.title}>
            <div className="pick-h"><span>{g.title}</span></div>
            {g.items.map((it) => (
              <label key={it.key} className={`pick${on(it.key) ? '' : ' off'}`}>
                <input type="checkbox" checked={on(it.key)} onChange={() => toggle(it.key)} />
                <i style={{ background: it.color }} />
                <span className="name">{it.label}</span>
                {it.note && <span className="note-r">{it.note}</span>}
              </label>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function runStamp(runAt: string, tz: string): string {
  const d = new Date(runAt)
  return d.toLocaleString([], { weekday: 'short', hour: 'numeric', timeZone: tz })
}
