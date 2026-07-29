import { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'ai-analysis', label: 'AI Analysis', icon: '🤖' },
  { id: 'backtesting', label: 'Backtesting', icon: '⏪' },
  { id: 'risk', label: 'Risk Management', icon: '🛡️' },
  { id: 'journal', label: 'Trade Journal', icon: '📓' },
  { id: 'alerts', label: 'Alerts', icon: '🔔' },
  { id: 'settings', label: 'Settings', icon: '⚙️' },
];

export default function Sidebar() {
  const [activeId, setActiveId] = useState('dashboard');
  const [collapsed, setCollapsed] = useState(false);
  const { user } = useAuth();

  return (
    <aside
      className={`
        h-screen sticky top-0 flex flex-col bg-forex-surface/80 backdrop-blur-xl
        border-r border-forex-border transition-all duration-300
        ${collapsed ? 'w-[72px]' : 'w-[240px]'}
      `}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-forex-border">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-forex-bullish to-forex-cyan flex items-center justify-center text-gray-900 font-bold text-sm shrink-0">
          FX
        </div>
        {!collapsed && (
          <span className="font-bold text-sm tracking-wide">
            Forex<span className="text-forex-bullish">AI</span>
          </span>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveId(item.id)}
            className={`sidebar-link w-full text-left ${activeId === item.id ? 'active' : ''} ${collapsed ? 'justify-center px-2' : ''}`}
            title={collapsed ? item.label : undefined}
          >
            <span className="text-lg shrink-0">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
          </button>
        ))}
      </nav>

      {/* User + collapse toggle */}
      <div className="border-t border-forex-border p-3">
        {!collapsed && user && (
          <div className="flex items-center gap-3 px-2 py-2 mb-2">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-forex-cyan to-forex-bullish flex items-center justify-center text-gray-900 font-bold text-xs shrink-0">
              {user.name.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium truncate">{user.name}</p>
              <p className="text-[10px] text-forex-text-muted truncate">{user.email}</p>
            </div>
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center py-2 rounded-lg text-forex-text-muted hover:text-forex-text hover:bg-white/5 transition-all"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <span className="text-sm">{collapsed ? '▶' : '◀'}</span>
        </button>
      </div>
    </aside>
  );
}
