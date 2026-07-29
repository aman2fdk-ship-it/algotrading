import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { ApiError } from '@/lib/api';

export default function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setLoading(true);
    try {
      await register(name, email, password, confirmPassword);
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
    <div className="min-h-screen bg-forex-bg flex items-center justify-center px-6">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-forex-bullish to-forex-cyan flex items-center justify-center text-gray-900 font-bold">
            FX
          </div>
          <span className="font-bold text-lg">
            Forex<span className="text-forex-bullish">AI</span>
          </span>
        </div>

        <div className="glass-panel p-8">
          <h2 className="text-2xl font-bold mb-1">Create account</h2>
          <p className="text-forex-text-dim text-sm mb-6">
            Start your forex analysis journey
          </p>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-forex-bearish-dim border border-forex-bearish/30 text-forex-bearish text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-forex-text-dim mb-1.5">
                Full Name
              </label>
              <input
                type="text"
                className="glass-input"
                placeholder="John Trader"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

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
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-forex-text-dim mb-1.5">
                Password
              </label>
              <input
                type="password"
                className="glass-input"
                placeholder="Min. 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-forex-text-dim mb-1.5">
                Confirm Password
              </label>
              <input
                type="password"
                className="glass-input"
                placeholder="Repeat password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
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
                  Creating account...
                </>
              ) : (
                'Create Account'
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-forex-text-dim">
            Already have an account?{' '}
            <Link
              to="/login"
              className="text-forex-bullish hover:text-forex-cyan transition-colors font-medium"
            >
              Sign in
            </Link>
          </p>
        </div>

        <p className="text-center text-xs text-forex-text-muted mt-6">
          Advisory only — not financial advice
        </p>
      </div>
    </div>
  );
}
