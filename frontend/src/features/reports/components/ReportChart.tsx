/**
 * CSS-based chart rendering for report data.
 * Supports bar, line, pie, and table chart types.
 */

import type { ReportDataPoint } from '../../../api/reports';

interface ReportChartProps {
  chartType: string;
  data: ReportDataPoint[];
  total?: number | null;
  compact?: boolean;
}

const CHART_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
];

function BarChart({ data, compact }: { data: ReportDataPoint[]; compact?: boolean }) {
  const maxValue = Math.max(...data.map((d) => d.value), 1);

  return (
    <div className={compact ? 'space-y-1.5' : 'space-y-3'}>
      {data.map((point, idx) => {
        const width = (point.value / maxValue) * 100;
        return (
          <div key={idx} className="flex items-center gap-3">
            <div className={`${compact ? 'w-24' : 'w-32'} text-sm text-gray-600 truncate flex-shrink-0`} title={point.label}>
              {point.label}
            </div>
            <div className="flex-1">
              <div className={`${compact ? 'h-4' : 'h-6'} bg-gray-100 rounded-full overflow-hidden`}>
                <div
                  className="h-full rounded-full transition-[width] duration-300"
                  style={{ width: `${Math.max(width, 1)}%`, backgroundColor: CHART_COLORS[idx % CHART_COLORS.length] }}
                />
              </div>
            </div>
            <div className={`${compact ? 'w-16' : 'w-20'} text-sm text-gray-900 text-right font-medium tabular-nums flex-shrink-0`}>
              {point.value.toLocaleString()}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function LineChart({ data }: { data: ReportDataPoint[] }) {
  if (data.length === 0) return null;

  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const minValue = Math.min(...data.map((d) => d.value), 0);
  const range = maxValue - minValue || 1;
  const chartHeight = 200;
  const chartWidth = 100;

  const points = data.map((d, i) => ({
    x: data.length > 1 ? (i / (data.length - 1)) * chartWidth : 50,
    y: chartHeight - ((d.value - minValue) / range) * chartHeight,
  }));

  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
    .join(' ');

  return (
    <div>
      <svg viewBox={`-5 -10 ${chartWidth + 10} ${chartHeight + 20}`} className="w-full" style={{ maxHeight: '250px' }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
          <line
            key={ratio}
            x1={0}
            y1={chartHeight - ratio * chartHeight}
            x2={chartWidth}
            y2={chartHeight - ratio * chartHeight}
            stroke="#e5e7eb"
            strokeWidth={0.3}
          />
        ))}
        {/* Line */}
        <path d={pathD} fill="none" stroke="#3b82f6" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
        {/* Points */}
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={2} fill="#3b82f6" />
        ))}
      </svg>
      <div className="flex justify-between mt-2 text-xs text-gray-500 overflow-hidden">
        {data.length <= 8
          ? data.map((d, i) => (
              <span key={i} className="truncate text-center" style={{ maxWidth: `${100 / data.length}%` }}>
                {d.label}
              </span>
            ))
          : [data[0], data[Math.floor(data.length / 2)], data[data.length - 1]].map((d, i) => (
              <span key={i} className="truncate">
                {d.label}
              </span>
            ))}
      </div>
    </div>
  );
}

function PieChart({ data, total }: { data: ReportDataPoint[]; total?: number | null }) {
  const sum = total || data.reduce((s, d) => s + d.value, 0) || 1;
  let cumulativePercent = 0;

  const segments = data.map((d, i) => {
    const percent = d.value / sum;
    const start = cumulativePercent;
    cumulativePercent += percent;
    return { ...d, percent, start, color: CHART_COLORS[i % CHART_COLORS.length] };
  });

  const getCoordinatesForPercent = (percent: number) => {
    const x = Math.cos(2 * Math.PI * percent);
    const y = Math.sin(2 * Math.PI * percent);
    return [x, y];
  };

  return (
    <div className="flex flex-col sm:flex-row items-center gap-6">
      <svg viewBox="-1.1 -1.1 2.2 2.2" className="w-48 h-48 flex-shrink-0" style={{ transform: 'rotate(-90deg)' }}>
        {segments.map((seg, i) => {
          const [startX, startY] = getCoordinatesForPercent(seg.start);
          const [endX, endY] = getCoordinatesForPercent(seg.start + seg.percent);
          const largeArcFlag = seg.percent > 0.5 ? 1 : 0;

          if (segments.length === 1) {
            return <circle key={i} cx={0} cy={0} r={1} fill={seg.color} />;
          }

          const d = `M ${startX} ${startY} A 1 1 0 ${largeArcFlag} 1 ${endX} ${endY} L 0 0`;
          return <path key={i} d={d} fill={seg.color} />;
        })}
      </svg>
      <div className="space-y-2 min-w-0">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: seg.color }} />
            <span className="text-gray-700 truncate min-w-0">{seg.label}</span>
            <span className="text-gray-500 flex-shrink-0 tabular-nums">{(seg.percent * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TableChart({ data }: { data: ReportDataPoint[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Label
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
              Value
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {data.map((point, idx) => (
            <tr key={idx} className="hover:bg-gray-50">
              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                {point.label}
              </td>
              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600 text-right tabular-nums">
                {point.value.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReportChart({ chartType, data, total, compact }: ReportChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
        No data available
      </div>
    );
  }

  switch (chartType) {
    case 'bar':
    case 'funnel':
      return <BarChart data={data} compact={compact} />;
    case 'line':
      return <LineChart data={data} />;
    case 'pie':
      return <PieChart data={data} total={total} />;
    case 'table':
      return <TableChart data={data} />;
    default:
      return <BarChart data={data} compact={compact} />;
  }
}
