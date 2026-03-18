import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  askExploreQuestion,
  askAgentPlan,
  createProject,
  diagnoseCleanMessiness,
  explainExploreStep,
  fetchChartData,
  generateReport,
  getExploreInsights,
  getExploreSuggestedQuestions,
  latestReport,
  listDatasets,
  listProjects,
  predictModel,
  previewDataset,
  runClean,
  suggestCleanSteps,
  suggestCharts,
  trainModel,
  uploadDataset,
} from "./client";
import type { ChartConfig, PlanStep } from "../types";

export function useProjectsQuery() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });
}

export function useCreateProjectMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { name: string; description?: string; user_id?: number }) => createProject(args),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useDatasetsQuery(projectId?: number) {
  return useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => listDatasets(projectId as number),
    enabled: Boolean(projectId),
  });
}

export function usePreviewQuery(datasetId?: number, page = 1, pageSize = 100) {
  return useQuery({
    queryKey: ["dataset-preview", datasetId, page, pageSize],
    queryFn: () => previewDataset(datasetId as number, page, pageSize),
    enabled: Boolean(datasetId),
  });
}

export function useUploadDatasetMutation(projectId?: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { file: File; name: string; description?: string }) => uploadDataset(projectId as number, args),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
    },
  });
}

export function usePlanMutation(projectId?: number, datasetId?: number | null) {
  return useMutation({
    mutationFn: (goal: string) => askAgentPlan(projectId as number, goal, datasetId),
  });
}

export function useCleanMutation(datasetId?: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      steps: Array<{ operation_type: string; parameters: object; description: string; generated_code?: string | null }>;
      instruction?: string;
    }) => runClean(datasetId as number, args.steps, args.instruction),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dataset-preview", datasetId] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });
}

export function useSuggestCleanStepsMutation(datasetId?: number) {
  return useMutation({
    mutationFn: (instruction?: string) => suggestCleanSteps(datasetId as number, instruction),
  });
}

export function useDiagnoseCleanMutation(datasetId?: number) {
  return useMutation({
    mutationFn: (instruction?: string) => diagnoseCleanMessiness(datasetId as number, instruction),
  });
}

export function useExploreInsightsQuery(datasetId?: number) {
  return useQuery({
    queryKey: ["explore-insights", datasetId],
    queryFn: () => getExploreInsights(datasetId as number),
    enabled: Boolean(datasetId),
  });
}

export function useExploreSuggestedQuestionsQuery(datasetId?: number) {
  return useQuery({
    queryKey: ["explore-suggested-questions", datasetId],
    queryFn: () => getExploreSuggestedQuestions(datasetId as number),
    enabled: Boolean(datasetId),
  });
}

export function useAskExploreQuestionMutation(datasetId?: number) {
  return useMutation({
    mutationFn: (question: string) => askExploreQuestion(datasetId as number, question),
  });
}

export function useExplainExploreStepMutation(datasetId?: number) {
  return useMutation({
    mutationFn: (step: PlanStep) => explainExploreStep(datasetId as number, step),
  });
}

export function useSuggestChartsMutation(datasetId?: number) {
  return useMutation({
    mutationFn: (question: string) => suggestCharts(datasetId as number, question),
  });
}

export function useChartDataMutation(datasetId?: number) {
  return useMutation({
    mutationFn: (config: ChartConfig) => fetchChartData(datasetId as number, config),
  });
}

export function useTrainModelMutation(datasetId?: number) {
  return useMutation({
    mutationFn: (goal: string) => trainModel(datasetId as number, goal),
  });
}

export function usePredictMutation(modelRunId?: number) {
  return useMutation({
    mutationFn: (row: Record<string, unknown>) => predictModel(modelRunId as number, row),
  });
}

export function useGenerateReportMutation(modelRunId?: number) {
  return useMutation({
    mutationFn: () => generateReport(modelRunId as number),
  });
}

export function useLatestReportQuery(projectId?: number) {
  return useQuery({
    queryKey: ["latest-report", projectId],
    queryFn: () => latestReport(projectId as number),
    enabled: Boolean(projectId),
    retry: false,
  });
}
