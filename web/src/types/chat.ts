export type ChatRole = "user" | "assistant";
export type ChatTurnStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface ChatReference {
  label: string;
  url?: string;
  detail?: string;
}

export interface ChatSeries {
  type: "bar" | "scatter";
  name: string;
  x: Array<string | number>;
  y: number[];
  mode?: "lines" | "markers" | "lines+markers";
}

export interface ChatChart {
  type: "bar" | "line";
  title?: string;
  x: Array<string | number>;
  series: Array<{ name: string; y: Array<number | null> }>;
  unit?: string;
}

export interface ChatDisplayColumn {
  key: string;
  label: string;
  unit?: string;
}

export interface ChatDisplay {
  display_id: string;
  kind: "table" | "chart";
  title: string;
  value_kind: "reported" | "observed" | "calculated" | "inferred" | "estimated" | "scheduled" | "mixed" |
    "derived_sum_of_reported_quarters" | "candidate_unapproved" | "missing";
  sources: ChatReference[];
  columns?: ChatDisplayColumn[];
  rows?: Array<Record<string, string | number | boolean | null>>;
  chart?: ChatChart;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  turn_id?: string;
  created_at?: string;
  references?: ChatReference[];
  chart?: ChatChart;
  displays?: ChatDisplay[];
  pending?: boolean;
  retryMessageId?: string;
  clientMessageId?: string;
}

export interface ChatTurn {
  id: string;
  status: ChatTurnStatus;
  error_message?: string | null;
}

export interface ChatConversation {
  id: string;
  snapshot_version: string;
  messages: ChatMessage[];
  turns: ChatTurn[];
}

export interface ChatContext {
  tab: "reading" | "economy" | "flights";
  period: string;
  entity: string | string[];
  card_id?: string;
  filters?: {
    segment?: "total" | "domestic" | "international";
    start?: string;
    end?: string;
    entities?: Array<"AEROMEXICO" | "VOLARIS" | "VIVA_AEROBUS" | "INDUSTRY">;
    network_mode?: "domestic" | "international";
    domestic_months?: string[];
    region?: string;
    range?: "all" | "12" | "8" | "4";
  };
}

export interface ChatEvent {
  seq?: number;
  type: "turn.queued" | "turn.started" | "message.delta" | "message.completed" | "tool.started" | "tool.completed" |
    "turn.completed" | "turn.failed" | "turn.cancelled";
  turn_id?: string;
  [key: string]: unknown;
}
