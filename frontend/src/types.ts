export interface Track {
  id: string;
  title: string;
  artist: string;
  duration_sec: number | null;
  audio_url: string;
  cover_url: string | null;
  license_url?: string | null;
  license_short?: string | null;
  source: string;
  external_id: string;
}

export interface AuthUser {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
}

export interface PlaylistSummary {
  id: string;
  name: string;
}

export interface PlaylistDetail extends PlaylistSummary {
  tracks: Track[];
}
