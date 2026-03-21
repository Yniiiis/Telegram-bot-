import { NavLink } from "react-router-dom";

const linkClass =
  "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium text-spotify-muted transition";

export function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 flex border-t border-spotify-border bg-spotify-base/95 pb-[max(env(safe-area-inset-bottom),0.35rem)] pt-1 backdrop-blur-md">
      <NavLink
        to="/"
        end
        className={({ isActive }) =>
          `${linkClass} ${isActive ? "!text-white" : ""}`
        }
      >
        <HomeIcon />
        Home
      </NavLink>
      <NavLink
        to="/search"
        className={({ isActive }) => `${linkClass} ${isActive ? "!text-spotify-accent" : ""}`}
      >
        <SearchNavIcon />
        Search
      </NavLink>
      <NavLink
        to="/favorites"
        className={({ isActive }) => `${linkClass} ${isActive ? "!text-spotify-accent" : ""}`}
      >
        <HeartIcon />
        Liked
      </NavLink>
      <NavLink
        to="/playlists"
        className={({ isActive }) => `${linkClass} ${isActive ? "!text-spotify-accent" : ""}`}
      >
        <ListIcon />
        Lists
      </NavLink>
    </nav>
  );
}

function HomeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 3 2 12h3v8h6v-5h2v5h6v-8h3L12 3Z" />
    </svg>
  );
}

function SearchNavIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Zm0-2a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11Z" />
      <path d="M16.5 16.5 21 21" stroke="currentColor" strokeWidth="2" fill="none" />
    </svg>
  );
}

function HeartIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <path
        d="M12 21s-6.716-4.432-9-8.5C.5 8.5 2.5 5 6.5 5c2.2 0 3.5 1.5 3.5 1.5S11.3 5 13.5 5c4 0 6 3.5 4.5 7.5C18.716 16.568 12 21 12 21Z"
        strokeWidth="1.6"
      />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M4 6h16v2H4V6Zm0 5h16v2H4v-2Zm0 5h10v2H4v-2Z" />
    </svg>
  );
}
