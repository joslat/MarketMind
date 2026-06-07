import { create } from "zustand";
import type { Cascade, CascadeNode, EventIndexRow } from "./types";

interface LedgerRow {
  id: string;
  name: string;
  impact: number;
  direction: "gain" | "loss";
  band: string;
  hop: number;
}

interface State {
  index: EventIndexRow[];
  cascade: Cascade | null;
  eventId: string | null;
  ledger: LedgerRow[];
  playToken: number; // bump to (re)start the wave
  cinematic: boolean;
  timeMachine: boolean;   // reveal golden actuals after the cascade
  revealActuals: boolean; // set true once the wave settles (in time-machine mode)
  view: "graph" | "map";
  error: string | null;
  selected: string | null;       // ticker the user drilled into (path isolate + per-hop math)
  loadIndex: () => Promise<void>;
  select: (id: string) => Promise<void>;
  setLedger: (rows: LedgerRow[]) => void;
  replay: () => void;
  toggleCinematic: () => void;
  toggleTimeMachine: () => void;
  setReveal: (v: boolean) => void;
  toggleView: () => void;
  setSelected: (id: string | null) => void;
}

// the curated demo playlist for cinematic mode (the beats we record)
export const PLAYLIST = [
  "evt_tsmc_quake_2024",
  "evt_chip_controls_tighten_2023",
  "evt_deepseek_selloff_2025",
  "evt_taiwan_strait_scare_2022",
  "evt_nvda_ai_surge_2024",
];

export const useStore = create<State>((set, get) => ({
  index: [],
  cascade: null,
  eventId: null,
  ledger: [],
  playToken: 0,
  cinematic: false,
  timeMachine: false,
  revealActuals: false,
  view: "graph",
  error: null,
  selected: null,
  loadIndex: async () => {
    try {
      const r = await fetch(`${import.meta.env.BASE_URL}cascades/index.json`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      set({ index: await r.json(), error: null });
    } catch (e: any) {
      set({ error: `Could not load cascades — run \`python tools/export_cascades.py\` first (${e.message})` });
    }
  },
  select: async (id) => {
    try {
      const r = await fetch(`${import.meta.env.BASE_URL}cascades/${id}.json`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const c: Cascade = await r.json();
      c.nodes.forEach((n: CascadeNode) => {
        n.__cur = 0;
        n.__ignite = 0;
      });
      set({ cascade: c, eventId: id, ledger: [], playToken: get().playToken + 1, revealActuals: false, error: null, selected: null });
      if (typeof window !== "undefined") window.history.replaceState(null, "", "#" + id); // shareable permalink
    } catch (e: any) {
      set({ error: `Could not load event ${id} (${e.message})` });
    }
  },
  setLedger: (rows) => set({ ledger: rows }),
  replay: () => set({ playToken: get().playToken + 1, revealActuals: false }),
  toggleCinematic: () => set({ cinematic: !get().cinematic }),
  toggleTimeMachine: () => set({ timeMachine: !get().timeMachine, revealActuals: false, playToken: get().playToken + 1 }),
  setReveal: (v) => set({ revealActuals: v }),
  toggleView: () => set({ view: get().view === "graph" ? "map" : "graph" }),
  setSelected: (id) => set({ selected: id }),
}));
