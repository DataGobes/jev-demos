import { createContext } from "react";

export type SpecElement = { type: string; props: Record<string, unknown>; children: string[] };
export type AltEntry = { id: string; kind: string; title: string; p: number; element: SpecElement };
export type PanelActions = { alternates: (panelIndex: number) => AltEntry[]; swap: (panelIndex: number, altId: string) => void };

export const RowsContext = createContext<Record<string, unknown>[]>([]);
export const PanelActionsContext = createContext<PanelActions>({ alternates: () => [], swap: () => {} });
