import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  Pagination,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseIcon from "@mui/icons-material/Close";
import {
  useCleanMutation,
  useDiagnoseCleanMutation,
  usePreviewQuery,
  useSuggestCleanStepsMutation,
} from "../api/hooks";
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
  const [afterPage, setAfterPage] = useState(1);
  const beforePreview = usePreviewQuery(datasetId, 1, 20);
  const afterPreview = usePreviewQuery(datasetId, afterPage, 20);
  const cleanMutation = useCleanMutation(datasetId);
  const diagnoseMutation = useDiagnoseCleanMutation(datasetId);
  const suggestMutation = useSuggestCleanStepsMutation(datasetId);
  const [selected, setSelected] = useState<Record<number, boolean>>({});
  const [instruction, setInstruction] = useState("Focus on missing values, duplicates, and category consistency.");
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [diagnoseInput, setDiagnoseInput] = useState("Where is this dataset messy and what should I clean first?");
  const [diagnoseHistory, setDiagnoseHistory] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [suggestDialogOpen, setSuggestDialogOpen] = useState(false);
  const [compareDialogOpen, setCompareDialogOpen] = useState(false);
  const [beforePage, setBeforePage] = useState(1);

  const cleanSteps = useMemo(() => {
    const aiSteps = (suggestMutation.data?.steps ?? []).map((s, idx) => ({
      idx,
      operation_type: s.operation_type,
      short_title: s.operation_type,
      user_friendly_explanation: s.description,
      python_pandas_code: s.generated_code ?? null,
      parameters: s.parameters ?? {},
    }));
    if (aiSteps.length > 0) return aiSteps;

    const planSteps = (plan?.steps ?? []).filter((s) => s.tab === "Clean" || CLEAN_OPS.has(s.operation_type));
    return planSteps.map((s, idx) => ({
      idx,
      operation_type: s.operation_type,
      short_title: s.short_title,
      user_friendly_explanation: s.user_friendly_explanation,
      python_pandas_code: s.python_pandas_code,
      parameters: {},
    }));
  }, [plan, suggestMutation.data]);

  useEffect(() => {
    if (!datasetId) return;
    void suggestMutation.mutateAsync(undefined).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  useEffect(() => {
    setAfterPage(1);
    setBeforePage(1);
  }, [datasetId]);

  const selectedSteps = cleanSteps
    .filter((s) => selected[s.idx] ?? true)
    .map((s) => ({
      operation_type: s.operation_type,
      parameters: s.parameters ?? {},
      description: s.user_friendly_explanation || s.short_title,
      generated_code: s.python_pandas_code ?? null,
    }));

  const runCleaning = async () => {
    if (!datasetId) return;
    await cleanMutation.mutateAsync({ steps: selectedSteps, instruction });
    setAfterPage(1);
  };

  const askMessinessAI = async () => {
    if (!datasetId || !diagnoseInput.trim()) return;
    const userText = diagnoseInput.trim();
    setDiagnoseHistory((prev) => [...prev, { role: "user", text: userText }]);
    try {
      const resp = await diagnoseMutation.mutateAsync(userText);
      setDiagnoseHistory((prev) => [
        ...prev,
        { role: "assistant", text: `${resp.message} (source: ${resp.source})` },
      ]);
    } catch {
      setDiagnoseHistory((prev) => [
        ...prev,
        { role: "assistant", text: "I couldn't analyze messiness right now. Please try again." },
      ]);
    }
  };

  const askCleanAI = async () => {
    if (!datasetId || !chatInput.trim()) return;
    const userText = chatInput.trim();
    setChatHistory((prev) => [...prev, { role: "user", text: userText }]);
    setChatInput("");
    try {
      const resp = await suggestMutation.mutateAsync(userText);
      setChatHistory((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `Suggested ${resp.steps.length} safe cleaning steps (${resp.source}). Review them in the popup.`,
        },
      ]);
      setInstruction(userText);
      setSuggestDialogOpen(true);
    } catch {
      setChatHistory((prev) => [
        ...prev,
        { role: "assistant", text: "I couldn't generate suggestions right now. Please try a shorter instruction." },
      ]);
    }
  };

  const previewCols = beforePreview.data?.columns.map((c) => c.name) ?? [];
  const beforeRowsFromRun = cleanMutation.data?.before_window_rows ?? [];
  const beforeRows = beforeRowsFromRun.length > 0 ? beforeRowsFromRun : beforePreview.data?.rows ?? [];
  const beforeCols = beforeRows.length > 0 ? Object.keys(beforeRows[0] ?? {}) : previewCols;

  const beforePageSize = 20;
  const beforePages = Math.max(1, Math.ceil(beforeRows.length / beforePageSize));
  const beforeSlice = beforeRows.slice((beforePage - 1) * beforePageSize, beforePage * beforePageSize);

  const afterCols = (afterPreview.data?.columns ?? []).map((c) => c.name);
  const afterRows = afterPreview.data?.rows ?? cleanMutation.data?.rows ?? [];

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Safe step-by-step cleaning</Typography>
      <Typography color="text.secondary">
        Chat with AI to request cleaning. Suggestions appear in a popup where you choose steps, then run them safely.
      </Typography>
      {!datasetId && <Alert severity="info">Pick a dataset in the Data tab first.</Alert>}

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" mb={1}>Messiness analysis chat</Typography>
          <Stack spacing={1.5}>
            <Paper variant="outlined" sx={{ p: 1.5, maxHeight: 220, overflow: "auto" }}>
              <Stack spacing={1}>
                {diagnoseHistory.length === 0 && (
                  <Typography color="text.secondary">
                    Ask where data quality issues are likely, then use that guidance for cleaning.
                  </Typography>
                )}
                {diagnoseHistory.map((m, i) => (
                  <Box
                    key={`${m.role}-diag-${i}`}
                    sx={{
                      p: 1,
                      borderRadius: 1,
                      bgcolor: m.role === "user" ? "#e8f0fe" : "#f4f6f8",
                      alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                      maxWidth: "90%",
                    }}
                  >
                    <Typography variant="body2">{m.text}</Typography>
                  </Box>
                ))}
              </Stack>
            </Paper>
            <TextField
              fullWidth
              label="Ask about messy areas"
              value={diagnoseInput}
              onChange={(e) => setDiagnoseInput(e.target.value)}
            />
            <Tooltip title="Analyze likely data quality issues using schema + sample rows.">
              <span>
                <Button
                  variant="outlined"
                  onClick={askMessinessAI}
                  disabled={!datasetId || !diagnoseInput.trim() || diagnoseMutation.isPending}
                >
                  Analyze messiness
                </Button>
              </span>
            </Tooltip>
            {diagnoseMutation.isPending && <CircularProgress size={22} />}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" mb={1}>Cleaning execution chat</Typography>
          <Stack spacing={1.5}>
            <Paper variant="outlined" sx={{ p: 1.5, maxHeight: 220, overflow: "auto" }}>
              <Stack spacing={1}>
                {chatHistory.length === 0 && (
                  <Typography color="text.secondary">
                    Ask something like: "drop rows with missing churn label, fill numeric gaps with median, standardize city names".
                  </Typography>
                )}
                {chatHistory.map((m, i) => (
                  <Box
                    key={`${m.role}-${i}`}
                    sx={{
                      p: 1,
                      borderRadius: 1,
                      bgcolor: m.role === "user" ? "#e8f0fe" : "#f4f6f8",
                      alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                      maxWidth: "90%",
                    }}
                  >
                    <Typography variant="body2">{m.text}</Typography>
                  </Box>
                ))}
              </Stack>
            </Paper>
            <TextField
              fullWidth
              label="Tell AI how to clean the data"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
            />
            <Stack direction="row" spacing={1}>
              <Tooltip title="Send your instruction to AI and generate suggested clean steps.">
                <span>
                  <Button
                    variant="outlined"
                    onClick={askCleanAI}
                    disabled={!datasetId || !chatInput.trim() || suggestMutation.isPending}
                  >
                    Send
                  </Button>
                </span>
              </Tooltip>
              <Tooltip title="Open suggested clean steps popup.">
                <span>
                  <Button
                    variant="text"
                    onClick={() => setSuggestDialogOpen(true)}
                    disabled={cleanSteps.length === 0}
                  >
                    View suggestions
                  </Button>
                </span>
              </Tooltip>
            </Stack>
            {suggestMutation.isPending && <CircularProgress size={22} />}
            {suggestMutation.error && (
              <Alert severity="warning">Could not generate AI step suggestions. You can still execute manual/default steps.</Alert>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" mb={1}>Execute selected steps</Typography>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1} mb={1}>
            <TextField
              fullWidth
              label="Execution instruction sent to AI (optional)"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              multiline
              minRows={2}
            />
            <Tooltip title="This calls Ollama with your instruction + sample rows, then applies safe mapped operations.">
              <span>
                <Button
                  variant="contained"
                  onClick={runCleaning}
                  disabled={!datasetId || (!instruction.trim() && selectedSteps.length === 0) || cleanMutation.isPending}
                >
                  Execute clean steps
                </Button>
              </span>
            </Tooltip>
          </Stack>
          {suggestMutation.data?.source && <Typography color="text.secondary">Suggestion source: {suggestMutation.data.source}</Typography>}
          {selectedSteps.length === 0 && (
            <Alert severity="info">
              No selected suggested steps. Execution will still ask Ollama using your instruction.
            </Alert>
          )}
          {cleanMutation.isPending && <CircularProgress size={22} />}
          {cleanMutation.error && <Alert severity="error">Cleaning failed. Try fewer steps, then re-run.</Alert>}
          {cleanMutation.data?.execution_source && (
            <Alert severity="success">
              Cleaning completed via: {cleanMutation.data.execution_source}. Row count:{" "}
              {String(cleanMutation.data.row_count_before ?? "unknown")} {"->"}{" "}
              {String(cleanMutation.data.row_count_after ?? "unknown")}.
            </Alert>
          )}
        </CardContent>
      </Card>

      <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
        <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="subtitle1">Before (scrollable sample)</Typography>
            <IconButton size="small" onClick={() => setCompareDialogOpen(true)}>
              <OpenInFullIcon fontSize="small" />
            </IconButton>
          </Stack>
          <TableContainer sx={{ maxHeight: 360 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {beforeCols.map((c) => (
                    <TableCell key={c}>{c}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {beforeSlice.map((r, idx) => (
                  <TableRow key={idx}>
                    {beforeCols.map((c) => (
                      <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <Pagination
            sx={{ mt: 1 }}
            size="small"
            count={beforePages}
            page={beforePage}
            onChange={(_, p) => setBeforePage(p)}
          />
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="subtitle1">After (scrollable sample)</Typography>
            <IconButton size="small" onClick={() => setCompareDialogOpen(true)}>
              <OpenInFullIcon fontSize="small" />
            </IconButton>
          </Stack>
          {afterRows.length === 0 ? (
            <Typography color="text.secondary">Run clean steps to see the updated preview.</Typography>
          ) : (
            <TableContainer sx={{ maxHeight: 360 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {afterCols.map((c) => (
                      <TableCell key={c}>{c}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {afterRows.map((r, idx) => (
                    <TableRow key={idx}>
                      {afterCols.map((c) => (
                        <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <Button size="small" variant="outlined" disabled={afterPage <= 1} onClick={() => setAfterPage((p) => Math.max(1, p - 1))}>
              Previous
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={(afterPreview.data?.rows ?? []).length < 20}
              onClick={() => setAfterPage((p) => p + 1)}
            >
              Next
            </Button>
            <Typography variant="body2" color="text.secondary" sx={{ alignSelf: "center" }}>
              Page {afterPage}
            </Typography>
          </Stack>
        </Paper>
      </Stack>

      <Dialog open={suggestDialogOpen} onClose={() => setSuggestDialogOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Suggested cleaning steps</DialogTitle>
        <DialogContent>
          <Stack spacing={1}>
            {cleanSteps.length === 0 ? (
              <Alert severity="info">No suggestions yet. Ask the clean assistant first.</Alert>
            ) : (
              cleanSteps.map((s) => (
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
              ))
            )}
            <Button onClick={() => setSuggestDialogOpen(false)} variant="contained">
              Use selected steps
            </Button>
          </Stack>
        </DialogContent>
      </Dialog>

      <Dialog open={compareDialogOpen} onClose={() => setCompareDialogOpen(false)} fullScreen>
        <DialogTitle sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          Before vs After comparison
          <IconButton onClick={() => setCompareDialogOpen(false)}>
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle1">Before</Typography>
              <TableContainer sx={{ maxHeight: "70vh" }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {beforeCols.map((c) => (
                        <TableCell key={c}>{c}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {beforeSlice.map((r, idx) => (
                      <TableRow key={idx}>
                        {beforeCols.map((c) => (
                          <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle1">After</Typography>
              <TableContainer sx={{ maxHeight: "70vh" }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {afterCols.map((c) => (
                        <TableCell key={c}>{c}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {afterRows.map((r, idx) => (
                      <TableRow key={idx}>
                        {afterCols.map((c) => (
                          <TableCell key={c}>{String(r[c] ?? "")}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Stack>
        </DialogContent>
      </Dialog>
    </Stack>
  );
}
