import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { ApiError } from '@/lib/api';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('Connection error. Is the backend running?');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-forex-bg flex">
      {/* Left: branding */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-forex-bullish/10 via-transparent to-forex-cyan/5" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-forex-bullish/5 via-transparent to-transparent" />
        <div className="relative flex flex-col justify-center px-16">
          <div className="mb-8">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-forex-bullish to-forex-cyan flex items-center justify-center text-gray-900 font-bold text-lg mb-6">
              FX
            </div>
            <h1 className="text-4xl font-bold mb-4">
              Forex<span className="text-forex-bullish">AI</span> Terminal
            </h1>
            <p className="text-forex-text-dim text-lg leading-relaxed max-w-md">
              Institutional-grade forex analysis. AI-powered recommendations,
              real-time charts, and professional risk management — all in one terminal.
            </p>
          </div>
          <div className="flex gap-6 text-sm text-forex-text-muted">
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-forex-bullish" />
              AI Analysis
            </span>
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-forex-cyan" />
              Live Charts
            </span>
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-forex-bearish" />
              Risk Mgmt
            </span>
          </div>
        </div>
        {/* Decorative grid lines */}
        <div className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)',
            backgroundSize: '60px 60px',
          }}
        />
      </div>

      {/* Right: login form */}
      <div className="flex-1 flex items-center justify-center px-6">
        <div className="w-full max-w-md">
          <div className="glass-panel p-8">
            {/* Mobile logo */}
            <div className="lg:hidden flex items-center gap-3 mb-8">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-forex-bullish to-forex-cyan flex items-center justify-center text-gray-900 font-bold">
                FX
              </div>
              <span className="font-bold text-lg">
                Forex<span className="text-forex-bullish">AI</span>
              </span>
            </div>

            <h2 className="text-2xl font-bold mb-1">Welcome back</h2>
            <p className="text-forex-text-dim text-sm mb-6">
              Sign in to access your terminal
            </p>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-forex-bearish-dim border border-forex-bearish/30 text-forex-bearish text-sm">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-forex-text-dim mb-1.5">
                  Email
                </label>
                <input
                  type="email"
                  className="glass-input"
                  placeholder="trader@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-forex-text-dim mb-1.5">
                  Password
                </label>
                <input
                  type="password"
                  className="glass-input"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="btn-primary w-full flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <span className="w-4 h-4 border-2 border-gray-900/30 border-t-gray-900 rounded-full animate-spin" />
                    Signing in...
                  </>
                ) : (
                  'Sign In'
                )}
              </button>
            </form>

            <div className="mt-6 flex items-center justify-between text-sm">
              <Link
                to="/forgot-password"
                className="text-forex-text-dim hover:text-forex-bullish transition-colors"
              >
                Forgot password?
              </Link>
              <Link
                to="/register"
                className="text-forex-bullish hover:text-forex-cyan transition-colors font-medium"
              >
                Create account
              </Link>
            </div>
          </div>

          <p className="text-center text-xs text-forex-text-muted mt-6">
            Advisory only — not financial advice
          </p>
        </div>
      </div>
    </div>
  );
}
