export type Band = "Severe" | "High" | "Moderate" | "Marginal";

export interface CascadeNode {
  id: string;
  name: string;
  sector: string;
  country?: string;
  lat?: number;
  lng?: number;
  tradable: boolean;
  impact: number;          // final signed impact, clamped [-1,1]
  band: Band;
  direction: "gain" | "loss";
  hop: number;
  confidence: number;      // 0..1, decays with hop distance
  path: string;            // strongest chain, e.g. "TSMC —SUP→ NVDA"
  actual?: number;         // Time Machine: realized abnormal return %
  actualDir?: "gain" | "loss";
  hit?: boolean;           // predicted direction == realized direction
  // runtime (mutated by the player / force layout)
  __cur?: number;          // currently displayed impact (tweened 0 -> impact)
  __ignite?: number;       // ignition timestamp (ms) for the pop animation
  __reveal?: number;       // Time Machine: actuals reveal timestamp
  x?: number;
  y?: number;
}

export interface CascadeLink {
  source: string | CascadeNode;
  target: string | CascadeNode;
  type: string;
  weight: number;
  sign: number;
  hop: number;
  magnitude: number;
  source_ref?: string;     // provenance: "public" | "10-K:<ticker>" | "wikidata:<qid>"
  __active?: boolean;
}

export interface Cascade {
  event: {
    id: string;
    headline: string;
    regime: "contagion" | "substitution";
    scope: string;
    date: string;
    category: string;
    severity: number;
    geo?: { lat: number; lng: number; zone?: string };
    split: "TRAIN" | "TEST";
  };
  nodes: CascadeNode[];
  links: CascadeLink[];
  hops: string[][];
  meta: {
    weights: Record<string, number>;
    seeds: { ticker: string; seed: number }[];
    reached: number;
    scored: number;
  };
}

export interface EventIndexRow {
  id: string;
  headline: string;
  date: string;
  regime: string;
  scope: string;
  severity: number;
  reached: number;
}
