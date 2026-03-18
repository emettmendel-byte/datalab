import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  CircularProgress,
  MenuItem,
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
import { useDatasetsQuery, usePreviewQuery, useUploadDatasetMutation } from "../api/hooks";

interface Props {
  projectId?: number;
  selectedDatasetId?: number;
  onSelectDataset: (id: number) => void;
}

export function DataTab({ projectId, selectedDatasetId, onSelectDataset }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const datasetsQuery = useDatasetsQuery(projectId);
  const uploadMutation = useUploadDatasetMutation(projectId);
  const previewQuery = usePreviewQuery(selectedDatasetId, 1, 50);

  const datasetOptions = datasetsQuery.data ?? [];
  const hasDatasets = datasetOptions.length > 0;

  const previewColumns = useMemo(() => (previewQuery.data?.columns ?? []).map((c) => c.name), [previewQuery.data]);

  const upload = async () => {
    if (!file || !projectId) return;
    const uploaded = await uploadMutation.mutateAsync({
      file,
      name: name || file.name,
      description,
    });
    onSelectDataset(uploaded.dataset.id);
    setName("");
    setDescription("");
    setFile(null);
  };

  const uploadErrorMessage =
    uploadMutation.error instanceof Error
      ? uploadMutation.error.message
      : "Upload failed. Please verify your file format.";

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Upload and preview your data</Typography>
      <Typography color="text.secondary">
        Upload a CSV file to S3, then preview the first rows so you can confirm columns look correct.
      </Typography>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <TextField label="Dataset name" value={name} onChange={(e) => setName(e.target.value)} />
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            multiline
            minRows={2}
          />
          <Button variant="outlined" component="label">
            Choose CSV
            <input
              hidden
              type="file"
              accept=".csv,.tsv,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Button>
          {file && <Typography color="text.secondary">Selected: {file.name}</Typography>}
          <Tooltip title="Only CSV/delimited text files up to 50MB are supported.">
            <span>
              <Button variant="contained" onClick={upload} disabled={!projectId || !file || uploadMutation.isPending}>
                Upload dataset
              </Button>
            </span>
          </Tooltip>
          {uploadMutation.isPending && <CircularProgress size={20} />}
          {uploadMutation.error && <Alert severity="error">{uploadErrorMessage}</Alert>}
        </Stack>
      </Paper>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
        <TextField
          select
          label="Active dataset"
          value={selectedDatasetId ?? ""}
          onChange={(e) => onSelectDataset(Number(e.target.value))}
          sx={{ minWidth: 320 }}
        >
          {datasetOptions.map((d) => (
            <MenuItem key={d.id} value={d.id}>
              {d.name} {d.row_count ? `(${d.row_count} rows)` : ""}
            </MenuItem>
          ))}
        </TextField>
        {datasetsQuery.isLoading && <CircularProgress size={20} />}
      </Stack>
      {!hasDatasets && !datasetsQuery.isLoading && (
        <Alert severity="info">No datasets yet. Upload one to continue.</Alert>
      )}

      {previewQuery.isFetching && <CircularProgress size={24} />}
      {previewQuery.error && selectedDatasetId && (
        <Alert severity="warning">Could not preview this dataset yet.</Alert>
      )}

      {previewQuery.data && (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                {previewColumns.map((col) => (
                  <TableCell key={col}>{col}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {previewQuery.data.rows.map((row, idx) => (
                <TableRow key={idx}>
                  {previewColumns.map((col) => (
                    <TableCell key={col}>{String(row[col] ?? "")}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Stack>
  );
}
