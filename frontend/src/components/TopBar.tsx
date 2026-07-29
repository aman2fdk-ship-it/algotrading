import { useAuth } from '@/contexts/AuthContext';

export default function TopBar() {
  const { user, logout } = useAuth();

  return (
    <header className="h-16 flex items-center justify-between px-6 border-b border-forex-border bg-forex-surface/60 backdrop-blur-xl sticky top-0 z-10">
      {/* Page title placeholder */}
      <div>
        <h1 className="text-lg font-semibold">Dashboard</h1>
        <p className="text-xs text-forex-text-muted">
          Welcome back, {user?.name || 'Trader'}
        </p>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Notification bell */}
        <button className="relative p-2 rounded-lg text-forex-text-dim hover:text-forex-text hover:bg-white/5 transition-all">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-forex-bearish rounded-full" />
        </button>

        {/* User avatar + logout */}
        <div className="flex items-center gap-3 pl-3 border-l border-forex-border">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-forex-cyan to-forex-bullish flex items-center justify-center text-gray-900 font-bold text-xs">
            {user?.name?.charAt(0).toUpperCase() || 'U'}
          </div>
          <button
            onClick={logout}
            className="text-xs text-forex-text-muted hover:text-forex-bearish transition-colors"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
