import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { useExplainExploreStepMutation, useExploreInsightsQuery } from "../api/hooks";
import type { Plan } from "../types";

interface Props {
  datasetId?: number;
  plan: Plan | null;
}

export function ExploreTab({ datasetId, plan }: Props) {
  const insightsQuery = useExploreInsightsQuery(datasetId);
  const explainMutation = useExplainExploreStepMutation(datasetId);
  const [extraExplanation, setExtraExplanation] = useState<string>("");

  const firstExploreStep = useMemo(
    () => (plan?.steps ?? []).find((s) => s.tab === "Explore") ?? null,
    [plan],
  );

  const explain = async () => {
    if (!firstExploreStep || !datasetId) return;
    const result = await explainMutation.mutateAsync(firstExploreStep);
    setExtraExplanation(result.explanation);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Explore insights</Typography>
      <Typography color="text.secondary">
        This quick EDA scan summarizes missing values, distributions, and notable relationships in plain language.
      </Typography>

      {!datasetId && <Alert severity="info">Select a dataset in the Data tab first.</Alert>}
      {insightsQuery.isLoading && <CircularProgress size={24} />}
      {insightsQuery.error && <Alert severity="warning">Could not load insights yet.</Alert>}

      <Stack spacing={1.5}>
        {(insightsQuery.data ?? []).map((insight) => (
          <Card key={insight.id} variant="outlined">
            <CardContent>
              <Typography fontWeight={700}>{insight.title}</Typography>
              <Typography color="text.secondary">{insight.description}</Typography>
              {insight.chart_suggestion && (
                <Typography variant="body2" mt={1}>
                  Suggested chart: {insight.chart_suggestion.chart_type}
                </Typography>
              )}
            </CardContent>
          </Card>
        ))}
      </Stack>

      <Box>
        <Tooltip title="Uses the AI explainer to translate the Explore step into plain language.">
          <span>
            <Button
              variant="outlined"
              onClick={explain}
              disabled={!datasetId || !firstExploreStep || explainMutation.isPending}
            >
              Explain Explore step
            </Button>
          </span>
        </Tooltip>
      </Box>
      {explainMutation.isPending && <CircularProgress size={20} />}
      {extraExplanation && <Alert severity="info">{extraExplanation}</Alert>}
    </Stack>
  );
}
