import { useMemo } from "react";
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
import { usePlanMutation } from "../api/hooks";
import type { LifecycleTab, Plan } from "../types";

const TAB_ORDER: LifecycleTab[] = ["Question", "Data", "Clean", "Explore", "Visualize", "Model", "Report"];

interface Props {
  projectId?: number;
  datasetId?: number;
  goal: string;
  onGoalChange: (goal: string) => void;
  plan: Plan | null;
  onPlan: (plan: Plan) => void;
}

export function QuestionTab({ projectId, datasetId, goal, onGoalChange, plan, onPlan }: Props) {
  const mutation = usePlanMutation(projectId, datasetId);

  const grouped = useMemo(() => {
    if (!plan) return new Map<LifecycleTab, Plan["steps"]>();
    const m = new Map<LifecycleTab, Plan["steps"]>();
    for (const tab of TAB_ORDER) m.set(tab, []);
    for (const step of plan.steps) {
      const arr = m.get(step.tab) ?? [];
      arr.push(step);
      m.set(step.tab, arr);
    }
    return m;
  }, [plan]);

  const ask = async () => {
    if (!projectId) return;
    const data = await mutation.mutateAsync(goal);
    onPlan(data);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Ask AI what to do next</Typography>
      <Typography color="text.secondary">
        Describe your goal in plain language. The AI will create a step-by-step plan mapped to each tab.
      </Typography>
      <TextField
        multiline
        minRows={4}
        label="What are you trying to learn or predict?"
        value={goal}
        onChange={(e) => onGoalChange(e.target.value)}
        fullWidth
      />
      <Box>
        <Tooltip title="The AI creates a plan only. It does not execute code in this step.">
          <span>
            <Button variant="contained" onClick={ask} disabled={!projectId || !goal.trim() || mutation.isPending}>
              Ask AI
            </Button>
          </span>
        </Tooltip>
      </Box>
      {mutation.isPending && <CircularProgress size={24} />}
      {mutation.error && <Alert severity="error">Could not generate a plan. Try rephrasing your goal.</Alert>}

      {plan && (
        <Stack spacing={2}>
          {TAB_ORDER.map((tab) => {
            const steps = grouped.get(tab) ?? [];
            return (
              <Card key={tab} variant="outlined">
                <CardContent>
                  <Stack direction="row" alignItems="center" spacing={1} mb={1}>
                    <Typography variant="subtitle1">{tab}</Typography>
                    <Chip size="small" label={`${steps.length} steps`} />
                  </Stack>
                  {steps.length === 0 ? (
                    <Typography color="text.secondary">No specific step suggested here yet.</Typography>
                  ) : (
                    <Stack spacing={1.5}>
                      {steps.map((s, idx) => (
                        <Box key={`${s.short_title}-${idx}`}>
                          <Typography fontWeight={600}>{s.short_title}</Typography>
                          <Typography color="text.secondary">{s.user_friendly_explanation}</Typography>
                        </Box>
                      ))}
                    </Stack>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}
