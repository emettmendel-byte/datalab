import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  useAskExploreQuestionMutation,
  useExplainExploreStepMutation,
  useExploreInsightsQuery,
  useExploreSuggestedQuestionsQuery,
} from "../api/hooks";
import type { Plan } from "../types";

interface Props {
  datasetId?: number;
  plan: Plan | null;
}

export function ExploreTab({ datasetId, plan }: Props) {
  const insightsQuery = useExploreInsightsQuery(datasetId);
  const suggestedQuery = useExploreSuggestedQuestionsQuery(datasetId);
  const askMutation = useAskExploreQuestionMutation(datasetId);
  const explainMutation = useExplainExploreStepMutation(datasetId);
  const [extraExplanation, setExtraExplanation] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);

  const firstExploreStep = useMemo(
    () => (plan?.steps ?? []).find((s) => s.tab === "Explore") ?? null,
    [plan],
  );

  const explain = async () => {
    if (!firstExploreStep || !datasetId) return;
    const result = await explainMutation.mutateAsync(firstExploreStep);
    setExtraExplanation(result.explanation);
  };

  const ask = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!datasetId || !text) return;
    setChat((prev) => [...prev, { role: "user", text }]);
    if (!q) setQuestion("");
    try {
      const result = await askMutation.mutateAsync(text);
      setChat((prev) => [...prev, { role: "assistant", text: result.answer }]);
    } catch {
      setChat((prev) => [...prev, { role: "assistant", text: "I couldn't answer that right now. Try rephrasing the question." }]);
    }
  };

  const suggestedQuestions = useMemo(() => suggestedQuery.data?.questions ?? [], [suggestedQuery.data]);

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Explore with AI chat</Typography>
      <Typography color="text.secondary">
        Ask questions about your data in plain language. You can use suggested prompts and review AI-selected summary statistics.
      </Typography>

      {!datasetId && <Alert severity="info">Select a dataset in the Data tab first.</Alert>}
      {(insightsQuery.isLoading || suggestedQuery.isLoading) && <CircularProgress size={24} />}
      {(insightsQuery.error || suggestedQuery.error) && <Alert severity="warning">Could not load explore context yet.</Alert>}

      <Card variant="outlined">
        <CardContent>
          <Typography fontWeight={700} mb={1}>Suggested questions</Typography>
          {suggestedQuestions.length === 0 ? (
            <Typography color="text.secondary">No suggested questions yet.</Typography>
          ) : (
            <Stack direction="row" useFlexGap flexWrap="wrap" gap={1}>
              {suggestedQuestions.map((q, i) => (
                <Chip key={`${q}-${i}`} label={q} onClick={() => void ask(q)} />
              ))}
            </Stack>
          )}
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography fontWeight={700} mb={1}>Explore chat</Typography>
          <Stack spacing={1.5}>
            <Box sx={{ border: "1px solid #ddd", borderRadius: 1, p: 1.5, maxHeight: 260, overflow: "auto" }}>
              <Stack spacing={1}>
                {chat.length === 0 && (
                  <Typography color="text.secondary">Ask anything like "What columns look most predictive?"</Typography>
                )}
                {chat.map((m, i) => (
                  <Box
                    key={`${m.role}-${i}`}
                    sx={{
                      p: 1,
                      borderRadius: 1,
                      bgcolor: m.role === "user" ? "#e8f0fe" : "#f4f6f8",
                      alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                      maxWidth: "92%",
                    }}
                  >
                    <Typography variant="body2">{m.text}</Typography>
                  </Box>
                ))}
              </Stack>
            </Box>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
              <TextField
                fullWidth
                label="Ask a question about this dataset"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <Button variant="contained" onClick={() => void ask()} disabled={!datasetId || !question.trim() || askMutation.isPending}>
                Ask
              </Button>
            </Stack>
            {askMutation.isPending && <CircularProgress size={20} />}
          </Stack>
        </CardContent>
      </Card>

      <Stack spacing={1.5}>
        <Typography variant="subtitle1">AI-selected summary statistics</Typography>
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
