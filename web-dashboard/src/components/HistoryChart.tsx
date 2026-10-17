import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

type Point = { at: string; value: number; unit: string }

export function HistoryChart({ values }: { values: Point[] }) {
  const data = values.map(point => ({ ...point, time: new Date(point.at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }))
  const unit = values[0]?.unit ?? ''
  return <div className="chart-wrap" role="img" aria-label={`${values.length} historical sensor readings chart`}>
    <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 12, right: 12, left: -12, bottom: 2 }}>
      <CartesianGrid stroke="#e9efed" strokeDasharray="3 5" vertical={false} />
      <XAxis dataKey="time" tick={{ fill: '#87938f', fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={46} />
      <YAxis tick={{ fill: '#87938f', fontSize: 10 }} tickLine={false} axisLine={false} width={52} />
      <Tooltip formatter={(value) => [`${value} ${unit}`, 'Reading']} contentStyle={{ borderRadius: 12, border: '1px solid #e5ebe8', boxShadow: '0 8px 25px #0e31221a', fontSize: 12 }} />
      <Line type="monotone" dataKey="value" stroke="#138a69" strokeWidth={2.2} dot={false} activeDot={{ r: 4, fill: '#138a69', stroke: '#fff', strokeWidth: 2 }} connectNulls={false} />
    </LineChart></ResponsiveContainer>
    <span className="chart-unit">{unit}</span>
  </div>
}
