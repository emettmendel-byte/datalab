import { useMemo, useState } from "react";
import {
  AppBar,
  Box,
  Container,
  MenuItem,
  Tab,
  Tabs,
  TextField,
  Toolbar,
  Typography,
} from "@mui/material";
import { useProjectsQuery } from "./api/hooks";
import { TabPanel } from "./components/TabPanel";
import { CleanTab } from "./tabs/CleanTab";
import { DataTab } from "./tabs/DataTab";
import { ExploreTab } from "./tabs/ExploreTab";
import { ModelTab } from "./tabs/ModelTab";
import { QuestionTab } from "./tabs/QuestionTab";
import { ReportTab } from "./tabs/ReportTab";
import { VisualizeTab } from "./tabs/VisualizeTab";
import type { ModelRunSummary, Plan } from "./types";
import "./App.css";

const TAB_LABELS = ["Question", "Data", "Clean", "Explore", "Visualize", "Model", "Report"];

function App() {
  const [tab, setTab] = useState(0);
  const [selectedProjectId, setSelectedProjectId] = useState<number | undefined>(undefined);
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | undefined>(undefined);
  const [goal, setGoal] = useState("Predict churn risk and explain the key drivers.");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [modelRun, setModelRun] = useState<ModelRunSummary | null>(null);

  const projectsQuery = useProjectsQuery();
  const projects = projectsQuery.data ?? [];

  const activeProjectId = useMemo(() => {
    if (selectedProjectId) return selectedProjectId;
    return projects[0]?.id;
  }, [projects, selectedProjectId]);

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "#f7f9fc" }}>
      <AppBar position="static" color="primary">
        <Toolbar sx={{ display: "flex", gap: 2, alignItems: "center" }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            AI Data Lab
          </Typography>
          <TextField
            select
            size="small"
            label="Project"
            value={activeProjectId ?? ""}
            onChange={(e) => setSelectedProjectId(Number(e.target.value))}
            sx={{ minWidth: 260, bgcolor: "white", borderRadius: 1 }}
          >
            {projects.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.name}
              </MenuItem>
            ))}
          </TextField>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ py: 2 }}>
        <Tabs
          value={tab}
          onChange={(_, next) => setTab(next)}
          variant="scrollable"
          allowScrollButtonsMobile
          sx={{ bgcolor: "white", borderRadius: 1 }}
        >
          {TAB_LABELS.map((label) => (
            <Tab key={label} label={label} />
          ))}
        </Tabs>

        <TabPanel value={tab} index={0}>
          <QuestionTab
            projectId={activeProjectId}
            datasetId={selectedDatasetId}
            goal={goal}
            onGoalChange={setGoal}
            plan={plan}
            onPlan={setPlan}
          />
        </TabPanel>
        <TabPanel value={tab} index={1}>
          <DataTab
            projectId={activeProjectId}
            selectedDatasetId={selectedDatasetId}
            onSelectDataset={setSelectedDatasetId}
          />
        </TabPanel>
        <TabPanel value={tab} index={2}>
          <CleanTab datasetId={selectedDatasetId} plan={plan} />
        </TabPanel>
        <TabPanel value={tab} index={3}>
          <ExploreTab datasetId={selectedDatasetId} plan={plan} />
        </TabPanel>
        <TabPanel value={tab} index={4}>
          <VisualizeTab datasetId={selectedDatasetId} />
        </TabPanel>
        <TabPanel value={tab} index={5}>
          <ModelTab datasetId={selectedDatasetId} goal={goal} onModelRun={setModelRun} modelRun={modelRun} />
        </TabPanel>
        <TabPanel value={tab} index={6}>
          <ReportTab projectId={activeProjectId} modelRun={modelRun} />
        </TabPanel>
      </Container>
    </Box>
  );
}

export default App;
