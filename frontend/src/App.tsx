import { useEffect, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CircularProgress,
  Container,
  Divider,
  Menu,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Toolbar,
  Typography,
} from "@mui/material";
import { useCreateProjectMutation, useProjectsQuery } from "./api/hooks";
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
  const [activeProjectId, setActiveProjectId] = useState<number | undefined>(undefined);
  const [selectedDatasetId, setSelectedDatasetId] = useState<number | undefined>(undefined);
  const [goal, setGoal] = useState("Predict churn risk and explain the key drivers.");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [modelRun, setModelRun] = useState<ModelRunSummary | null>(null);
  const [projectMenuAnchor, setProjectMenuAnchor] = useState<HTMLElement | null>(null);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDescription, setNewProjectDescription] = useState("");

  const projectsQuery = useProjectsQuery();
  const createProjectMutation = useCreateProjectMutation();
  const projects = projectsQuery.data ?? [];

  useEffect(() => {
    if (!activeProjectId || projects.every((p) => p.id !== activeProjectId)) {
      // force selection gate even when projects exist
      return;
    }
  }, [projects, activeProjectId]);

  const activeProject = projects.find((p) => p.id === activeProjectId);

  const enterProject = (projectId: number) => {
    setActiveProjectId(projectId);
    setSelectedDatasetId(undefined);
    setPlan(null);
    setModelRun(null);
    setTab(0);
  };

  const createAndEnter = async () => {
    if (!newProjectName.trim()) return;
    const project = await createProjectMutation.mutateAsync({
      name: newProjectName.trim(),
      description: newProjectDescription.trim() || undefined,
      user_id: 1,
    });
    setNewProjectName("");
    setNewProjectDescription("");
    enterProject(project.id);
  };

  if (!activeProjectId) {
    return (
      <Box sx={{ minHeight: "100vh", bgcolor: "#f7f9fc", py: 6 }}>
        <Container maxWidth="md">
          <Stack spacing={3}>
            <Typography variant="h4">Choose a Project</Typography>
            <Typography color="text.secondary">
              Start by selecting an existing project or creating a new one. You will enter the full lifecycle workspace after this step.
            </Typography>

            {projectsQuery.isLoading && <CircularProgress size={26} />}
            {projectsQuery.error && (
              <Alert severity="error">Could not load projects. Make sure the backend is running.</Alert>
            )}

            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" mb={1}>
                  Existing projects
                </Typography>
                {projects.length === 0 ? (
                  <Typography color="text.secondary">No projects yet. Create one below.</Typography>
                ) : (
                  <Stack spacing={1}>
                    {projects.map((project) => (
                      <Card key={project.id} variant="outlined">
                        <CardActionArea onClick={() => enterProject(project.id)}>
                          <CardContent>
                            <Typography fontWeight={700}>{project.name}</Typography>
                            <Typography color="text.secondary">
                              {project.description || "No description yet"}
                            </Typography>
                          </CardContent>
                        </CardActionArea>
                      </Card>
                    ))}
                  </Stack>
                )}
              </CardContent>
            </Card>

            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" mb={1}>
                  Create a new project
                </Typography>
                <Stack spacing={1.5}>
                  <TextField
                    label="Project name"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    fullWidth
                  />
                  <TextField
                    label="Description (optional)"
                    value={newProjectDescription}
                    onChange={(e) => setNewProjectDescription(e.target.value)}
                    fullWidth
                    multiline
                    minRows={2}
                  />
                  <Box>
                    <Button
                      variant="contained"
                      onClick={createAndEnter}
                      disabled={!newProjectName.trim() || createProjectMutation.isPending}
                    >
                      Create project and continue
                    </Button>
                  </Box>
                  {createProjectMutation.isPending && <CircularProgress size={20} />}
                  {createProjectMutation.error && (
                    <Alert severity="error">Could not create project. Try a different name.</Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Container>
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "#f7f9fc" }}>
      <AppBar position="static" color="primary">
        <Toolbar sx={{ display: "flex", gap: 2, alignItems: "center" }}>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            AI Data Lab
          </Typography>
          <Button
            variant="contained"
            color="secondary"
            onClick={(e) => setProjectMenuAnchor(e.currentTarget)}
            sx={{ minWidth: 240 }}
          >
            {activeProject?.name ?? "Project"}
          </Button>
          <Menu
            anchorEl={projectMenuAnchor}
            open={Boolean(projectMenuAnchor)}
            onClose={() => setProjectMenuAnchor(null)}
          >
            <MenuItem
              onClick={() => {
                setProjectMenuAnchor(null);
                setActiveProjectId(undefined);
              }}
            >
              Change project...
            </MenuItem>
            <Divider />
            {projects.map((p) => (
              <MenuItem
                key={p.id}
                selected={p.id === activeProjectId}
                onClick={() => {
                  setProjectMenuAnchor(null);
                  enterProject(p.id);
                }}
              >
                {p.name}
              </MenuItem>
            ))}
          </Menu>
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
