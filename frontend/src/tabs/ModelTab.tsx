import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { usePredictMutation, useTrainModelMutation } from "../api/hooks";
import type { ModelRunSummary } from "../types";

interface Props {
  datasetId?: number;
  goal: string;
  onModelRun: (run: ModelRunSummary | null) => void;
  modelRun: ModelRunSummary | null;
}

export function ModelTab({ datasetId, goal, onModelRun, modelRun }: Props) {
  const [rowJson, setRowJson] = useState('{"example_feature": 1}');
  const trainMutation = useTrainModelMutation(datasetId);
  const predictMutation = usePredictMutation(modelRun?.model_run_id);

  const configObj = useMemo(() => {
    if (!modelRun?.config_json) return null;
    try {
      return JSON.parse(modelRun.config_json) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [modelRun]);

  const metricsObj = useMemo(() => {
    if (!modelRun?.metrics_json) return null;
    try {
      return JSON.parse(modelRun.metrics_json) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [modelRun]);

  const train = async () => {
    if (!datasetId) return;
    const data = await trainMutation.mutateAsync(goal || "Train a useful baseline model.");
    onModelRun(data);
  };

  const predict = async () => {
    if (!modelRun?.model_run_id) return;
    const row = JSON.parse(rowJson) as Record<string, unknown>;
    await predictMutation.mutateAsync(row);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Train a baseline model</Typography>
      <Typography color="text.secondary">
        Accuracy tells you how many predictions are correct overall. F1 balances precision and recall when classes are uneven.
      </Typography>
      {!datasetId && <Alert severity="info">Choose a dataset first.</Alert>}
      <Tooltip title="AutoML-light picks a simple algorithm and evaluates it quickly on sampled data.">
        <span>
          <Button variant="contained" onClick={train} disabled={!datasetId || trainMutation.isPending}>
            Train model
          </Button>
        </span>
      </Tooltip>
      {trainMutation.isPending && <CircularProgress size={22} />}
      {trainMutation.error && <Alert severity="error">Training failed. Try clarifying your goal.</Alert>}

      {modelRun && (
        <Card variant="outlined">
          <CardContent>
            <Typography fontWeight={700}>Model summary</Typography>
            <Typography variant="body2" color="text.secondary">
              Model run ID: {modelRun.model_run_id}
            </Typography>
            <Typography variant="body2" mt={1}>
              Task: {String(configObj?.task_type ?? "unknown")} | Target: {String(configObj?.target_column ?? "unknown")}
            </Typography>
            <Box mt={1}>
              <pre>{JSON.stringify(metricsObj ?? {}, null, 2)}</pre>
            </Box>
          </CardContent>
        </Card>
      )}

      <Card variant="outlined">
        <CardContent>
          <Typography fontWeight={700}>Try a prediction</Typography>
          <Typography color="text.secondary" variant="body2">
            Enter a JSON object with feature names and values.
          </Typography>
          <TextField
            fullWidth
            multiline
            minRows={4}
            value={rowJson}
            onChange={(e) => setRowJson(e.target.value)}
            sx={{ mt: 1 }}
          />
          <Button sx={{ mt: 1 }} variant="outlined" onClick={predict} disabled={!modelRun || predictMutation.isPending}>
            Predict
          </Button>
          {predictMutation.isPending && <CircularProgress sx={{ ml: 1 }} size={18} />}
          {predictMutation.error && (
            <Alert sx={{ mt: 1 }} severity="warning">
              Could not predict. Ensure your row keys and data types match training features.
            </Alert>
          )}
          {predictMutation.data && (
            <Box mt={1}>
              <pre>{JSON.stringify(predictMutation.data, null, 2)}</pre>
            </Box>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
