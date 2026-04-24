import { useState } from 'react'
import './index.css'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RISK_STYLES = {
  low:    { badge: 'bg-green-100 text-green-800 border border-green-300',    dot: 'bg-green-500' },
  medium: { badge: 'bg-yellow-100 text-yellow-800 border border-yellow-300', dot: 'bg-yellow-500' },
  high:   { badge: 'bg-red-100 text-red-800 border border-red-300',          dot: 'bg-red-500' },
}

const SEVERITY_STYLES = {
  high:   'bg-red-100 text-red-700 border border-red-300',
  medium: 'bg-yellow-100 text-yellow-700 border border-yellow-300',
  low:    'bg-green-100 text-green-700 border border-green-300',
}

function riskStyle(level) {
  return RISK_STYLES[level?.toLowerCase()] ?? RISK_STYLES.low
}

function severityStyle(level) {
  return SEVERITY_STYLES[level?.toLowerCase()] ?? SEVERITY_STYLES.low
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Card({ title, icon, children, className = '' }) {
  return (
    <div className={`bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden ${className}`}>
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
        <span className="text-lg">{icon}</span>
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex flex-col items-center gap-3 py-12">
      <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      <p className="text-sm text-gray-500">Analyzing your query…</p>
    </div>
  )
}

function QueryFlowCard({ tool, args }) {
  return (
    <Card title="Query Flow" icon="⚙️">
      <div className="space-y-3">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Selected Tool</p>
          <span className="inline-block font-mono text-sm bg-blue-50 text-blue-700 border border-blue-200 rounded-lg px-3 py-1">
            {tool}
          </span>
        </div>
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Arguments</p>
          <div className="bg-gray-50 rounded-xl border border-gray-200 divide-y divide-gray-100">
            {Object.entries(args ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between items-center px-3 py-2 text-sm">
                <span className="font-mono text-gray-500">{k}</span>
                <span className="font-mono text-gray-800">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  )
}

function SafetyResultCard({ data }) {
  const risk = data?.risk_level?.toLowerCase() ?? 'low'
  const { badge, dot } = riskStyle(risk)

  return (
    <Card title="Safety Assessment" icon="🛡️">
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-semibold ${badge}`}>
            <span className={`w-2 h-2 rounded-full ${dot}`} />
            {risk.toUpperCase()} RISK
          </span>
        </div>

        <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Recommendation</p>
          <p className="text-gray-800 font-medium leading-snug">{data?.recommendation}</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-50 rounded-xl p-3 border border-gray-200 text-center">
            <p className="text-2xl font-bold text-gray-800">{data?.crime_count ?? 0}</p>
            <p className="text-xs text-gray-500 mt-0.5">Crimes Nearby</p>
          </div>
          <div className="bg-gray-50 rounded-xl p-3 border border-gray-200 text-center">
            <p className="text-2xl font-bold text-gray-800">{data?.incident_count ?? 0}</p>
            <p className="text-xs text-gray-500 mt-0.5">Reported Incidents</p>
          </div>
        </div>

        {data?.reasons?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Reasons</p>
            <ul className="space-y-1.5">
              {data.reasons.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="mt-1 text-gray-400">•</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}

function RecentCrimesCard({ crimes }) {
  if (!crimes?.length) {
    return (
      <Card title="Recent Crimes" icon="🔍">
        <p className="text-sm text-gray-400 text-center py-4">No nearby crimes found.</p>
      </Card>
    )
  }

  return (
    <Card title="Recent Crimes" icon="🔍">
      <div className="space-y-2">
        {crimes.map((c, i) => (
          <div
            key={i}
            className="flex items-center justify-between rounded-xl border border-gray-200 px-4 py-3 bg-gray-50"
          >
            <div className="flex items-center gap-3">
              <span className="text-gray-400 text-xs font-mono w-4">{i + 1}</span>
              <div>
                <p className="text-sm font-medium text-gray-800">{c.type}</p>
                {c.description && (
                  <p className="text-xs text-gray-500">{c.description}</p>
                )}
                <p className="text-xs text-gray-400">{c.distance.toFixed(2)} km away</p>
              </div>
            </div>
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${severityStyle(c.severity)}`}>
              {c.severity}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

function GenericResultCard({ data }) {
  if (typeof data === 'string') {
    return (
      <Card title="Result" icon="📋">
        <p className="text-sm text-gray-700 whitespace-pre-wrap">{data}</p>
      </Card>
    )
  }

  const items = Array.isArray(data) ? data.filter(i => i && typeof i === 'object') : (data && typeof data === 'object' ? [data] : [])

  if (!items.length) {
    return (
      <Card title="Result" icon="📋">
        <p className="text-sm text-gray-400 text-center py-4">No results returned.</p>
      </Card>
    )
  }

  return (
    <Card title="Result" icon="📋">
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={i} className="rounded-xl border border-gray-200 bg-gray-50 divide-y divide-gray-100">
            {Object.entries(item).map(([k, v]) => (
              <div key={k} className="flex justify-between items-center px-3 py-2 text-sm">
                <span className="font-mono text-gray-500">{k}</span>
                <span className="text-gray-800">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Example queries
// ---------------------------------------------------------------------------

const EXAMPLE_QUERIES = [
  'Is it safe to travel from downtown to Hyde Park?',
  'Show crimes near Navy Pier',
  'What buses are on Route 22?',
  'Get stops for Route 36',
]

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------

export default function App() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function handleSubmit(e) {
    e?.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed }),
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const data = await res.json()
      setResult(data)
    } catch (err) {
      setError(err.message ?? 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const steps = result?.steps ?? []

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Header */}
        <div className="text-center space-y-1">
          <div className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-1.5 rounded-full text-sm font-semibold shadow">
            🛡️ SafeTravel
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mt-3">Travel Safety Assistant</h1>
          <p className="text-gray-500 text-sm">Powered by Claude + MCP</p>
        </div>

        {/* Search form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-sm border border-gray-200 p-4 space-y-3">
          <textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() } }}
            placeholder="Ask about travel safety, bus routes, or incidents…"
            rows={3}
            className="w-full resize-none rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition"
          />
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLE_QUERIES.map(q => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuery(q)}
                  className="text-xs text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2.5 py-1 hover:bg-blue-100 transition"
                >
                  {q}
                </button>
              ))}
            </div>
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="shrink-0 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition"
            >
              {loading ? 'Asking…' : 'Ask'}
            </button>
          </div>
        </form>

        {/* Loading */}
        {loading && <Spinner />}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-2xl px-5 py-4 flex items-start gap-3">
            <span className="text-red-500 text-lg mt-0.5">⚠️</span>
            <div>
              <p className="font-semibold text-red-700 text-sm">Something went wrong</p>
              <p className="text-red-600 text-sm mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-4">
            {steps.map((step, i) => {
              const rawResult = step.result
              const firstItem = Array.isArray(rawResult) ? rawResult[0] : rawResult
              const isSafetyResult = firstItem?.risk_level !== undefined

              return (
                <div key={i} className="space-y-4">
                  <QueryFlowCard tool={step.tool} args={step.arguments} />
                  {isSafetyResult ? (
                    <>
                      <SafetyResultCard data={firstItem} />
                      <RecentCrimesCard crimes={firstItem?.recent_crimes} />
                    </>
                  ) : (
                    <GenericResultCard data={rawResult} />
                  )}
                </div>
              )
            })}
          </div>
        )}

      </div>
    </div>
  )
}
