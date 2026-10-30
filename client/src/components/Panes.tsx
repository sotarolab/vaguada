import { useState } from 'react'
import type { Bracket, JournalEntry, Profile, Settlement, StationPage } from '../api/client'
import { api } from '../api/client'

const pct = (p: number | null | undefined) => (p == null ? '—' : `${Math.round(p * 100)}¢`)
const deg = (v: number | null | undefined, digits = 0) => (v == null ? '—' : `${v.toFixed(digits)}°`)

export function DailyPane({ page }: { page: StationPage }) {
  const d = page.nws_daily
  const settled = new Map(page.settlements.map((s) => [`${s.local_day}:${s.target}`, s]))
  if (!d) return <p className="note">No NWS daily series stored yet.</p>
  return (
    <table className="grid">
      <thead><tr><th>Day</th><th className="r">NWS high</th><th className="r">Settled high</th><th className="r">NWS low</th><th className="r">Settled low</th></tr></thead>
      <tbody>
        {d.days.map((day, i) => {
          const hi = settled.get(`${day}:tmax`), lo = settled.get(`${day}:tmin`)
          return (
            <tr key={day}>
              <td className="num">{day}</td>
              <td className="r num">{deg(d.tmax[i])}</td>
              <td className="r num">{hi ? <>{deg(hi.value)} {!hi.final && <span className="pill prelim">prelim</span>}</> : '—'}</td>
              <td className="r num">{deg(d.tmin[i])}</td>
              <td className="r num">{lo ? <>{deg(lo.value)} {!lo.final && <span className="pill prelim">prelim</span>}</> : '—'}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function BracketsPane({ brackets }: { brackets: Bracket[] }) {
  if (brackets.length === 0) return <p className="note">No market for this station.</p>
  const days = [...new Set(brackets.map((b) => b.local_day))]
  return (
    <div className="pgrid">
      {days.map((day) => (
        <div key={day}>
          <span className="eyebrow">{day}</span>
          <table className="grid">
            <thead><tr><th>Bracket</th><th className="r">Bid</th><th className="r">Ask</th><th className="r">Last</th></tr></thead>
            <tbody>
              {brackets.filter((b) => b.local_day === day).map((b) => (
                <tr key={b.ticker}>
                  <td className="num">{label(b)}</td>
                  <td className="r num">{pct(b.yes_bid)}</td>
                  <td className="r num">{pct(b.yes_ask)}</td>
                  <td className="r num">{pct(b.last_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <p className="note">Public bracket prices sampled at the last slot. A column on the scorecard once days settle; nothing here trades.</p>
    </div>
  )
}

function label(b: Bracket): string {
  if (b.lo != null && b.hi != null) return `${b.lo}–${b.hi}°`
  if (b.lo != null) return `> ${b.lo}°`
  if (b.hi != null) return `< ${b.hi}°`
  return b.ticker
}

export function SettlementsPane({ settlements }: { settlements: Settlement[] }) {
  if (settlements.length === 0) return <p className="note">No climate report stored yet.</p>
  const days = [...new Set(settlements.map((s) => s.local_day))]
  return (
    <table className="grid">
      <thead><tr><th>Day</th><th className="r">High</th><th className="r">Low</th><th>Report</th></tr></thead>
      <tbody>
        {days.map((day) => {
          const hi = settlements.find((s) => s.local_day === day && s.target === 'tmax')
          const lo = settlements.find((s) => s.local_day === day && s.target === 'tmin')
          const prelim = !(hi?.final ?? lo?.final ?? false)
          return (
            <tr key={day}>
              <td className="num">{day}</td>
              <td className="r num">{deg(hi?.value)}</td>
              <td className="r num">{deg(lo?.value)}</td>
              <td><span className={`pill${prelim ? ' prelim' : ''}`}>{prelim ? 'preliminary' : 'final'}</span></td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function DiscussionPane({ page }: { page: StationPage }) {
  const d = page.discussion
  if (!d) return <p className="note">No forecast discussion stored for this office yet.</p>
  return (
    <details className="fold" open>
      <summary>
        <span>Area forecast discussion, {d.office}</span>
        <span className="stamp">{new Date(d.issued_at).toLocaleString([], { timeZone: page.station.tz })}</span>
      </summary>
      <pre style={{ whiteSpace: 'pre-wrap', font: '12px/1.5 var(--mono)', color: 'var(--ink)', maxHeight: 420, overflow: 'auto', margin: '8px 0 0' }}>{d.text}</pre>
    </details>
  )
}

export function ProfilePane({ profiles, tz }: { profiles: Profile[]; tz: string }) {
  if (profiles.length === 0) return <p className="note">No pressure-level profiles stored for this station; only deep stations carry them.</p>
  return (
    <div className="pgrid">
      {profiles.map((p) => (
        <div key={p.model}>
          <span className="eyebrow">{p.model.toUpperCase()} · valid {new Date(p.valid_at).toLocaleString([], { weekday: 'short', hour: 'numeric', timeZone: tz })}</span>
          <table className="grid diag">
            <thead><tr><th>hPa</th><th className="r">T</th><th className="r">Z m</th><th className="r">Wind</th><th className="r">RH</th></tr></thead>
            <tbody>
              {p.levels.map((l) => (
                <tr key={l.level_hpa}>
                  <td className="num">{l.level_hpa}</td>
                  <td className="r num">{deg(l.t, 1)}</td>
                  <td className="r num">{l.z_m == null ? '—' : Math.round(l.z_m)}</td>
                  <td className="r num">{l.wspd_ms == null ? '—' : `${Math.round(l.wspd_ms * 1.944)} kt ${l.wdir_deg == null ? '' : Math.round(l.wdir_deg) + '°'}`}</td>
                  <td className="r num">{l.rh == null ? '—' : `${Math.round(l.rh)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

const TAGS = ['marine layer', 'offshore flow', 'frontal passage', 'sea breeze', 'clear', 'overcast', 'rain', 'heat', 'models split']

export function JournalPane({ stationId, tz, entries, onAdded }: { stationId: string; tz: string; entries: JournalEntry[]; onAdded: () => void }) {
  // The station's local day, not the UTC date: an evening note belongs to today.
  const today = new Date().toLocaleDateString('en-CA', { timeZone: tz })
  const [day, setDay] = useState(today)
  const [uncertainty, setUncertainty] = useState(3)
  const [tags, setTags] = useState<Set<string>>(new Set())
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      await api.addJournal({ station_id: stationId, local_day: day, uncertainty, tags: [...tags], text })
      setText(''); setTags(new Set()); onAdded()
    } finally { setBusy(false) }
  }
  return (
    <div className="pgrid">
      <div className="card">
        <span className="eyebrow">Your reading of the day</span>
        <div className="row">
          <label className="picker">Day <input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label>
          <label className="picker">Uncertainty
            <div className="seg">{[1, 2, 3, 4, 5].map((n) => <button key={n} className={n === uncertainty ? 'on' : undefined} onClick={() => setUncertainty(n)}>{n}</button>)}</div>
          </label>
        </div>
        <div className="row">
          {TAGS.map((t) => (
            <label key={t} className={`pick${tags.has(t) ? '' : ' off'}`}>
              <input type="checkbox" checked={tags.has(t)} onChange={() => setTags((s) => { const n = new Set(s); if (n.has(t)) n.delete(t); else n.add(t); return n })} />
              <span className="name">{t}</span>
            </label>
          ))}
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="What the models are doing, what you expect, why." style={{ background: 'var(--panel2)', color: 'var(--ink)', border: '1px solid var(--rule)', font: '13px var(--sans)', padding: 6 }} />
        <div><button className="acct" disabled={busy} onClick={submit}>Record</button></div>
      </div>
      <div>
        <span className="eyebrow">Journal</span>
        {entries.length === 0 ? <p className="note">Nothing recorded yet.</p> : (
          <table className="grid">
            <thead><tr><th>Day</th><th>Unc.</th><th>Tags</th><th>Note</th></tr></thead>
            <tbody>
              {entries.map((e) => (
                <tr key={`${e.local_day}-${e.created_at}`}>
                  <td className="num">{e.local_day}</td>
                  <td className="num">{e.uncertainty ?? '—'}</td>
                  <td>{e.tags.join(', ')}</td>
                  <td>{e.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
