import { useEffect, useState } from 'react'
import { api } from './api/client'
import { useFetch } from './hooks/useFetch'
import { StationChart } from './components/StationChart'
import { BracketsPane, DailyPane, DiscussionPane, JournalPane, ProfilePane, SettlementsPane } from './components/Panes'

const REFRESH_MS = 5 * 60 * 1000

export default function App() {
  const [stationId, setStationId] = useState('asos:KLAX')
  const [tick, setTick] = useState(0)
  const bump = () => setTick((t) => t + 1)
  const stations = useFetch((signal) => api.stations(signal), [])
  const page = useFetch((signal) => api.station(stationId, signal), [stationId], tick)
  const journal = useFetch((signal) => api.journal(stationId, signal), [stationId], tick)
  const health = useFetch((signal) => api.health(signal), [], tick)
  useRefresh(bump, REFRESH_MS)

  const p = page.data
  const stale = health.data ? !health.data.ok : true
  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <h1>camanchaca-demo</h1>
          <span className="sub">daily high and low, stored before settlement, scored every night</span>
        </div>
        <span className="stamp"><i className={`live${stale ? ' stale' : ''}`} />{p ? `as of ${new Date(p.as_of).toLocaleString([], { timeZone: p.station.tz })}` : page.loading ? 'loading…' : page.error}</span>
      </header>
      <div className="context">
        <label className="picker">Station
          <select value={stationId} onChange={(e) => setStationId(e.target.value)}>
            {(stations.data ?? []).map((s) => <option key={s.station_id} value={s.station_id}>{s.name} · {s.station_id.split(':')[1]}{s.depth === 'deep' ? ' · deep' : ''}</option>)}
          </select>
        </label>
        {p && <span className="stamp">{p.station.tz} · NWS {p.station.nws_office ?? '—'} · {p.unit === 'F' ? '°F' : '°C'}</span>}
      </div>
      {page.error && <section className="panel"><p className="note">{page.error}</p></section>}
      {p && (
        <div className="panels">
          <section className="panel">
            <div className="panel-h"><h2>Temperature · observed and every model's latest run</h2></div>
            <StationChart page={p} />
          </section>
          <section className="panel">
            <div className="pgrid">
              <div><div className="panel-h"><h2>NWS daily against the climate report</h2></div><DailyPane page={p} /></div>
              <div><div className="panel-h"><h2>Settlements</h2></div><SettlementsPane settlements={p.settlements} /></div>
            </div>
          </section>
          <section className="panel">
            <div className="panel-h"><h2>Market brackets · daily high</h2></div>
            <BracketsPane brackets={p.brackets} />
          </section>
          <section className="panel">
            <div className="panel-h"><h2>Vertical structure · latest run per model</h2></div>
            <ProfilePane profiles={p.profiles} tz={p.station.tz} />
          </section>
          <section className="panel">
            <div className="panel-h"><h2>Forecast discussion</h2></div>
            <DiscussionPane page={p} />
          </section>
          <section className="panel">
            <div className="panel-h"><h2>Journal · learn from each day</h2></div>
            <JournalPane stationId={stationId} tz={p.station.tz} entries={journal.data ?? []} onAdded={bump} />
          </section>
        </div>
      )}
      <footer>Every number on this page was written by a scheduled job before you opened it; the page draws what it is given. Nothing here trades.</footer>
    </div>
  )
}

function useRefresh(fn: () => void, ms: number) {
  // A plain interval, cleared on unmount; the fetch hook lets a slow request land rather
  // than restarting it.
  useEffect(() => {
    const id = setInterval(fn, ms)
    return () => clearInterval(id)
  }, [fn, ms])
}
