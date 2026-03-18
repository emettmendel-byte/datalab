import { Alert, Button, Card, CardContent, CircularProgress, Stack, Tooltip, Typography } from "@mui/material";
import ReactMarkdown from "react-markdown";
import { useGenerateReportMutation, useLatestReportQuery } from "../api/hooks";
import type { ModelRunSummary } from "../types";

interface Props {
  projectId?: number;
  modelRun: ModelRunSummary | null;
}

export function ReportTab({ projectId, modelRun }: Props) {
  const latestQuery = useLatestReportQuery(projectId);
  const generateMutation = useGenerateReportMutation(modelRun?.model_run_id);

  const generate = async () => {
    if (!modelRun) return;
    await generateMutation.mutateAsync();
  };

  const regenerateMoreDetail = async () => {
    if (!modelRun) return;
    // Backend currently uses same endpoint; this button simply re-generates.
    await generateMutation.mutateAsync();
  };

  const reportBody = generateMutation.data?.body ?? latestQuery.data?.body;

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Narrative report</Typography>
      <Typography color="text.secondary">
        This report is written for non-technical users, with practical conclusions and next steps.
      </Typography>
      {!modelRun && <Alert severity="info">Train a model in the Model tab before generating a report.</Alert>}
      <Stack direction="row" spacing={1}>
        <Tooltip title="Generates a lifecycle-structured markdown report.">
          <span>
            <Button variant="contained" onClick={generate} disabled={!modelRun || generateMutation.isPending}>
              Generate report
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Calls the same endpoint again to refresh content with more depth.">
          <span>
            <Button variant="outlined" onClick={regenerateMoreDetail} disabled={!modelRun || generateMutation.isPending}>
              Regenerate with more detail
            </Button>
          </span>
        </Tooltip>
      </Stack>
      {(generateMutation.isPending || latestQuery.isLoading) && <CircularProgress size={24} />}
      {(generateMutation.error || latestQuery.error) && (
        <Alert severity="warning">Could not load a report yet. Generate one after training.</Alert>
      )}
      {reportBody && (
        <Card variant="outlined">
          <CardContent>
            <ReactMarkdown>{reportBody}</ReactMarkdown>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
