import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CircularProgress,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import Plot from "react-plotly.js";
import { useChartDataMutation, useSuggestChartsMutation } from "../api/hooks";
import type { ChartConfig } from "../types";

interface Props {
  datasetId?: number;
}

export function VisualizeTab({ datasetId }: Props) {
  const [question, setQuestion] = useState("Show me key patterns in this data.");
  const [selectedConfig, setSelectedConfig] = useState<ChartConfig | null>(null);

  const suggestMutation = useSuggestChartsMutation(datasetId);
  const chartDataMutation = useChartDataMutation(datasetId);

  const suggestions = suggestMutation.data ?? [];
  const plotly = chartDataMutation.data?.plotly;

  const suggest = async () => {
    const configs = await suggestMutation.mutateAsync(question);
    if (configs.length > 0) setSelectedConfig(configs[0]);
  };

  const loadChart = async (cfg: ChartConfig) => {
    setSelectedConfig(cfg);
    await chartDataMutation.mutateAsync(cfg);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Visualize your data</Typography>
      <Typography color="text.secondary">
        Ask for chart ideas in plain language. We return lightweight Plotly-ready data for quick interaction.
      </Typography>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
        <TextField
          fullWidth
          label="Visualization question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Tooltip title="Examples: 'Compare sales by region' or 'Show trend over time'.">
          <span>
            <Button variant="contained" onClick={suggest} disabled={!datasetId || suggestMutation.isPending}>
              Suggest charts
            </Button>
          </span>
        </Tooltip>
      </Stack>
      {suggestMutation.isPending && <CircularProgress size={22} />}
      {suggestMutation.error && <Alert severity="error">Could not suggest charts right now.</Alert>}

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" }, gap: 1.5 }}>
        {suggestions.map((cfg) => (
          <Box key={cfg.id}>
            <Card variant={selectedConfig?.id === cfg.id ? "elevation" : "outlined"}>
              <CardActionArea onClick={() => loadChart(cfg)}>
                <CardContent>
                  <Typography fontWeight={700}>{cfg.chart_type}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {cfg.description || `${cfg.x ?? ""} ${cfg.y ? `vs ${cfg.y}` : ""}`}
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Box>
        ))}
      </Box>

      {chartDataMutation.isPending && <CircularProgress size={24} />}
      {chartDataMutation.error && <Alert severity="warning">Could not render this chart with the current config.</Alert>}

      {plotly && (
        <Box sx={{ border: "1px solid #ddd", borderRadius: 2, p: 1 }}>
          <Plot
            data={[
              {
                type: plotly.type as never,
                mode: plotly.type === "scatter" ? "markers" : undefined,
                x: plotly.x as never,
                y: plotly.y as never,
                marker: plotly.color ? ({ color: plotly.color as never } as never) : undefined,
              },
            ]}
            layout={{
              title: selectedConfig?.description ?? "Chart preview",
              autosize: true,
              margin: { t: 40, r: 20, l: 40, b: 40 },
            }}
            style={{ width: "100%", height: 420 }}
            useResizeHandler
            config={{ responsive: true }}
          />
        </Box>
      )}
    </Stack>
  );
}
