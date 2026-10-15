export type CatalogStatus = "active" | "inactive" | "all";
export type VideoRelationStatus = "" | "confirmed" | "pending_confirmation" | "video_only" | "not_linked";
export type CatalogVideoRelationship = {
  video_isrc: string;
  audio_relationship_status: Exclude<VideoRelationStatus, "">;
  confirmed_audio_isrc: string | null;
  proposed_audio_isrc: string | null;
  proposed_audio_title: string | null;
  is_composite_video: boolean;
  notes: string;
  review_closed?: boolean;
  requires_user_confirmation?: boolean;
  recording_evidence?: { official_video_url: string; release: { url: string } };
};

export type CatalogInitialFilter = {
  source?: string;
  account?: string;
  status?: CatalogStatus;
  requestId: number;
};

export type CatalogItem = {
  video_isrcs?: string[];
  catalog_aliases?: string[];
  video_relationships?: CatalogVideoRelationship[];
  catalog_key: string;
  asset_isrc: string | null;
  track_id: string | null;
  track_title: string | null;
  artist_statement: string | null;
  first_transaction_month: string | null;
  last_transaction_month: string | null;
  amount_usd: number;
  units: number;
  sources: string | null;
  accounts: string | null;
  content_types: string | null;
  source_sheets: string | null;
  title_variants: string | null;
  artist_variants: string | null;
  external_release_date: string | null;
  external_match_url: string | null;
  external_label: string | null;
  label_normalized_auto: string | null;
  label_normalized_override: string | null;
  label_normalized: string | null;
  active: boolean;
  include_in_reports: boolean;
  catalog_business_status: string | null;
  status_notes: string | null;
  status_updated_at: string | null;
};

export type CatalogData = {
  items: CatalogItem[];
  total: number;
  limit: number;
  offset: number;
  totals: {
    amount_usd: number;
    units: number;
  };
  options: {
    sources: string[];
    accounts: string[];
    artists: string[];
    labels: string[];
    first_month: string | null;
    last_month: string | null;
  };
};

export type CatalogQuery = {
  videoRelationStatus?: VideoRelationStatus;
  source: string;
  account: string;
  artist: string;
  keyword: string;
  label: string;
  startMonth: string | null;
  endMonth: string | null;
  status: CatalogStatus;
  limit: number;
  offset: number;
};

export type CatalogUpdate = {
  catalog_key: string;
  active: boolean;
  include_in_reports: boolean;
  business_status: string;
  notes: string;
  label_normalized_override?: string | null;
};
