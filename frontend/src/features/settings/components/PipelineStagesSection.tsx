import { useLeadPipelineStages } from '../../../hooks/useLeads';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Badge } from '../../../components/ui/Badge';

/**
 * Read-only view of the lead pipeline stages. The opportunity pipeline
 * was retired (2026-05-14) and stage CRUD is no longer exposed through
 * the API — only the GET /api/leads/pipeline-stages endpoint remains,
 * so this section just renders the configured stages for reference.
 */
export function PipelineStagesSection() {
  const { data: stages, isLoading } = useLeadPipelineStages();

  return (
    <Card>
      <CardHeader
        title="Pipeline Stages"
        description="Lead pipeline stages configured for this workspace"
      />
      <CardBody className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : !stages || stages.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-4">No pipeline stages configured.</p>
        ) : (
          <div className="space-y-2">
            {stages.map((stage) => (
              <div
                key={stage.id}
                className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className="h-3 w-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: stage.color }}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{stage.name}</p>
                    {stage.description && (
                      <p className="text-xs text-gray-500 truncate">{stage.description}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                  <Badge variant={stage.is_won ? 'green' : stage.is_lost ? 'red' : 'gray'} size="sm">
                    {stage.probability}%
                  </Badge>
                  {!stage.is_active && (
                    <Badge variant="yellow" size="sm">Inactive</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
