import { Box } from "@mui/material";
import type { ReactNode } from "react";

interface Props {
  value: number;
  index: number;
  children: ReactNode;
}

export function TabPanel({ value, index, children }: Props) {
  if (value !== index) return null;
  return <Box sx={{ py: 2 }}>{children}</Box>;
}
