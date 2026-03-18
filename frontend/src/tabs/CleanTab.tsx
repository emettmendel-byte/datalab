import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  CircularProgress,
  FormControlLabel,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import { useCleanMutation, usePreviewQuery } from "../api/hooks";
import type { Plan } from "../types";

const CLEAN_OPS = new Set([
  "DROP_COLUMNS",
  "DROP_ROWS_WITH_MISSING",
  "FILL_MISSING",
  "CAST_TYPE",
  "FILTER_ROWS",
  "DEDUP_ROWS",
  "STANDARDIZE_CATEGORIES",
  "PARSE_DATES",
  "drop_columns",
  "drop_rows_with_missing",
  "fill_missing",
  "cast_type",
  "filter_rows",
  "dedup_rows",
  "standardize_categories",
  "parse_dates",
]);

interface Props {
  datasetId?: number;
  plan: Plan | null;
}

export function CleanTab({ datasetId, plan }: Props) {
  const beforePreview = usePreviewQuery(datasetId, 1, 20);
  const cleanMutation = useCleanMutation(datasetId);
  const [selected, setSelected] = useState<Record<number, boolean>>({});

  const cleanSteps = useMemo(() => {
    const steps = (plan?.steps ?? []).filter((s) => s.tab === "Clean" || CLEAN_OPS.has(s.operation_type));
    return steps.map((s, idx) => ({ ...s, idx }));
  }, [plan]);

  const selectedSteps = cleanSteps
    .filter((s) => selected[s.idx] ?? true)
    .map((s) => ({
      operation_type: s.operation_type,
      parameters: {},
      description: s.user_friendly_explanation || s.short_title,
      generated_code: s.python_pandas_code ?? null,
    }));

  const runCleaning = async () => {
    if (!datasetId || selectedSteps.length === 0) return;
    await cleanMutation.mutateAsync(selectedSteps);
  };

  const previewCols = beforePreview.data?.columns.map((c) => c.name) ?? [];
  const afterRows = cleanMutation.data?.rows ?? [];

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Safe step-by-step cleaning</Typography>
      <Typography color="text.secondary">
        Choose which suggested clean steps to apply. We use safe built-in operations rather than executing arbitrary code.
      </Typography>
      {!datasetId && <Alert severity="info">Pick a dataset in the Data tab first.</Alert>}

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" mb={1}>
            Suggested clean steps
          </Typography>
          {cleanSteps.length === 0 ? (
            <Alert severity="info">No clean steps from the plan yet. Ask AI in the Question tab first.</Alert>
          ) : (
            <Stack spacing={1}>
              {cleanSteps.map((s) => (
                <FormControlLabel
                  key={s.idx}
                  control={
                    <Checkbox
                      checked={selected[s.idx] ?? true}
                      onChange={(_, checked) => setSelected((prev) => ({ ...prev, [s.idx]: checked }))}
                    />
                  }
                  label={
                    <Box>
                      <Typography fontWeight={600}>{s.short_title}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        {s.user_friendly_explanation}
                      </Typography>
                    </Box>
                  }
                />
              ))}
              <Tooltip title="This applies selected clean steps and creates a cleaned dataset version.">
                <span>
                  <Button
                    variant="contained"
                    onClick={runCleaning}
                    disabled={!datasetId || selectedSteps.length === 0 || cleanMutation.isPending}
                  >
                    Execute clean steps
                  </Button>
                </span>
              </Tooltip>
              {cleanMutation.isPending && <CircularProgress size={22} />}
              {cleanMutation.error && (
                <Alert severity="error">
                  Cleaning failed. Try fewer steps, then re-run.
                </Alert>
              )}
            </Stack>
          )}
        </CardContent>
      </Card>

      <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
        <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle1">Before (sample)</Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {previewCols.map((c) => (
                    <TableCell key={c}>{c}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {(beforePreview.data?.rows ?? []).slice(0, 8).map((r, idx) => (
                  <TableRow key={idx}>
                    {previewCols.map((c) => (
                      <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle1">After (sample)</Typography>
          {afterRows.length === 0 ? (
            <Typography color="text.secondary">Run clean steps to see the updated preview.</Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {Object.keys(afterRows[0] ?? {}).map((c) => (
                      <TableCell key={c}>{c}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {afterRows.slice(0, 8).map((r, idx) => (
                    <TableRow key={idx}>
                      {Object.keys(afterRows[0] ?? {}).map((c) => (
                        <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Paper>
      </Stack>
    </Stack>
  );
}
