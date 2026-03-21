export function TrackRowSkeleton() {
  return (
    <div className="flex animate-pulse items-center gap-3 rounded-lg px-2 py-2.5">
      <div className="h-12 w-12 shrink-0 rounded-md bg-spotify-highlight" />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="h-3.5 w-3/4 rounded bg-spotify-highlight" />
        <div className="h-3 w-1/2 rounded bg-spotify-border" />
      </div>
      <div className="h-3 w-10 shrink-0 rounded bg-spotify-border" />
    </div>
  );
}

export function TrackListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i}>
          <TrackRowSkeleton />
        </li>
      ))}
    </ul>
  );
}
