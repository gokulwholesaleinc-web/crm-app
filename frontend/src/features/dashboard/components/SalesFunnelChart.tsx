/**
 * Sales funnel chart - visual funnel showing lead progression through stages
 */

import type { SalesFunnelResponse } from '../../../types';

interface SalesFunnelChartProps {
  data: SalesFunnelResponse;
}

const stageLabels: Record<string, string> = {
  new: 'New',
  contacted: 'Contacted',
  qualified: 'Qualified',
  converted: 'Converted',
};

export function SalesFunnelChart({ data }: SalesFunnelChartProps) {
  const maxCount = Math.max(...data.stages.map(s => s.count), 1);

  return (
    <div className="space-y-4">
      {/* Funnel bars */}
      <div className="space-y-3">
        {data.stages.map((stage, index) => {
          const widthPct = Math.max((stage.count / maxCount) * 100, 8);
          return (
            <div key={stage.stage}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {stageLabels[stage.stage] || stage.stage}
                </span>
                <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{stage.count}</span>
              </div>
              <div className="relative">
                <div
                  className="h-8 rounded transition-all duration-500"
                  style={{
                    width: `${widthPct}%`,
                    backgroundColor: stage.color || '#6366f1',
                    margin: '0 auto',
                    marginLeft: `${(100 - widthPct) / 2}%`,
                    opacity: 0.85,
                  }}
                />
              </div>
              {/* Conversion arrow between stages */}
              {index < data.stages.length - 1 && data.conversions[index] && (
                <div className="flex items-center justify-center my-1">
                  <div className="text-xs text-gray-500 flex items-center gap-1">
                    <svg className="h-3 w-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                    </svg>
                    {data.conversions[index].rate}% conversion
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Average days in stage */}
      <div className="border-t dark:border-gray-700 pt-3 mt-3">
        <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
          Avg. Days in Stage
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {data.stages.map((stage) => (
            <div key={stage.stage} className="text-center p-2 bg-gray-50 dark:bg-gray-700 rounded">
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {stageLabels[stage.stage] || stage.stage}
              </div>
              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                {data.avg_days_in_stage[stage.stage] != null
                  ? `${data.avg_days_in_stage[stage.stage]} days`
                  : '-'}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SalesFunnelChart;
