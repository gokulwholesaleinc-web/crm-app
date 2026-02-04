import { useState, useCallback } from 'react';
import {
  DndContext,
  DragOverlay,
  DragStartEvent,
  DragEndEvent,
  DragOverEvent,
  closestCorners,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import { KanbanColumn } from './KanbanColumn';
import { KanbanCard, Opportunity } from './KanbanCard';

export interface KanbanStage {
  id: string;
  title: string;
  color: string;
}

interface KanbanBoardProps {
  stages: KanbanStage[];
  opportunities: Opportunity[];
  onOpportunityMove: (
    opportunityId: string,
    newStage: string,
    newIndex: number
  ) => Promise<void>;
  onOpportunityClick?: (opportunity: Opportunity) => void;
}

export function KanbanBoard({
  stages,
  opportunities,
  onOpportunityMove,
  onOpportunityClick,
}: KanbanBoardProps) {
  const [activeOpportunity, setActiveOpportunity] = useState<Opportunity | null>(
    null
  );
  const [localOpportunities, setLocalOpportunities] =
    useState<Opportunity[]>(opportunities);

  // Update local state when props change
  if (
    JSON.stringify(opportunities.map((o) => o.id)) !==
    JSON.stringify(localOpportunities.map((o) => o.id))
  ) {
    setLocalOpportunities(opportunities);
  }

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    })
  );

  const getOpportunitiesByStage = useCallback(
    (stage: string) => {
      return localOpportunities.filter((o) => o.stage === stage);
    },
    [localOpportunities]
  );

  const getTotalValueByStage = useCallback(
    (stage: string) => {
      return getOpportunitiesByStage(stage).reduce(
        (sum, o) => sum + o.value,
        0
      );
    },
    [getOpportunitiesByStage]
  );

  const findOpportunityById = useCallback(
    (id: string) => {
      return localOpportunities.find((o) => o.id === id);
    },
    [localOpportunities]
  );

  const handleDragStart = (event: DragStartEvent) => {
    const { active } = event;
    const opportunity = findOpportunityById(active.id as string);
    if (opportunity) {
      setActiveOpportunity(opportunity);
    }
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;

    if (!over) return;

    const activeId = active.id as string;
    const overId = over.id as string;

    const activeOpportunity = findOpportunityById(activeId);
    if (!activeOpportunity) return;

    // Check if we're over a column
    const overData = over.data.current;
    if (overData?.type === 'column') {
      const newStage = overData.stage;
      if (activeOpportunity.stage !== newStage) {
        setLocalOpportunities((prev) =>
          prev.map((o) =>
            o.id === activeId ? { ...o, stage: newStage } : o
          )
        );
      }
      return;
    }

    // Check if we're over another opportunity
    const overOpportunity = findOpportunityById(overId);
    if (!overOpportunity || activeId === overId) return;

    // If dropping on a different stage
    if (activeOpportunity.stage !== overOpportunity.stage) {
      setLocalOpportunities((prev) => {
        const activeIndex = prev.findIndex((o) => o.id === activeId);
        const overIndex = prev.findIndex((o) => o.id === overId);

        const updatedOpportunities = [...prev];
        updatedOpportunities[activeIndex] = {
          ...updatedOpportunities[activeIndex],
          stage: overOpportunity.stage,
        };

        return arrayMove(updatedOpportunities, activeIndex, overIndex);
      });
    } else {
      // Reordering within the same column
      setLocalOpportunities((prev) => {
        const activeIndex = prev.findIndex((o) => o.id === activeId);
        const overIndex = prev.findIndex((o) => o.id === overId);
        return arrayMove(prev, activeIndex, overIndex);
      });
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;

    setActiveOpportunity(null);

    if (!over) return;

    const activeId = active.id as string;
    const opportunity = findOpportunityById(activeId);

    if (!opportunity) return;

    const newStage = opportunity.stage;
    const stageOpportunities = getOpportunitiesByStage(newStage);
    const newIndex = stageOpportunities.findIndex((o) => o.id === activeId);

    try {
      await onOpportunityMove(activeId, newStage, newIndex);
    } catch {
      // Revert on error
      setLocalOpportunities(opportunities);
    }
  };

  const handleDragCancel = () => {
    setActiveOpportunity(null);
    setLocalOpportunities(opportunities);
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {stages.map((stage) => (
          <KanbanColumn
            key={stage.id}
            id={stage.id}
            title={stage.title}
            opportunities={getOpportunitiesByStage(stage.id)}
            totalValue={getTotalValueByStage(stage.id)}
            color={stage.color}
            onOpportunityClick={onOpportunityClick}
          />
        ))}
      </div>

      <DragOverlay>
        {activeOpportunity && (
          <div className="rotate-3">
            <KanbanCard opportunity={activeOpportunity} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
