import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '@/contexts/AuthContext';
import LoginPage from '@/pages/LoginPage';
import RegisterPage from '@/pages/RegisterPage';
import { api, ApiError } from '@/lib/api';

vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.status = status;
      this.detail = detail;
      this.name = 'ApiError';
    }
  },
  api: {
    register: vi.fn(),
    login: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
    refreshToken: vi.fn(),
    forgotPassword: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

const tokens = { access_token: 'access-123', refresh_token: 'refresh-123', token_type: 'bearer' };
const user = {
  id: 'u1',
  email: 'trader@example.com',
  name: 'Trader',
  is_active: true,
  is_verified: true,
  avatar_url: null,
  default_symbols: null,
  timezone: null,
  created_at: '2026-08-01T00:00:00Z',
  last_login: null,
};

function renderAt(path: string, ui: JSX.Element) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<div>INSIDE_DASHBOARD</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const ph = (placeholder: string) => screen.getByPlaceholderText(placeholder);

describe('auth flow', () => {
  beforeEach(() => {
    vi.mocked(api.register).mockReset();
    vi.mocked(api.login).mockReset();
    vi.mocked(api.getMe).mockReset();
  });
  it('register: validates password mismatch before submitting', async () => {
    const u = userEvent.setup();
    renderAt('/register', <RegisterPage />);
    await u.type(ph('John Trader'), 'Jane');
    await u.type(ph('trader@example.com'), 'jane@example.com');
    await u.type(ph('Min. 8 characters'), 'password123');
    await u.type(ph('Repeat password'), 'different123');
    await u.click(screen.getByRole('button', { name: /Create Account/i }));
    expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
    expect(api.register).not.toHaveBeenCalled();
  });
  it('register: rejects passwords shorter than 8 characters', async () => {
    const u = userEvent.setup();
    renderAt('/register', <RegisterPage />);
    await u.type(ph('John Trader'), 'Jane');
    await u.type(ph('trader@example.com'), 'jane@example.com');
    await u.type(ph('Min. 8 characters'), 'short');
    await u.type(ph('Repeat password'), 'short');
    await u.click(screen.getByRole('button', { name: /Create Account/i }));
    expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
    expect(api.register).not.toHaveBeenCalled();
  });
  it('register: on success stores token and redirects to dashboard', async () => {
    vi.mocked(api.register).mockResolvedValue(tokens as never);
    vi.mocked(api.getMe).mockResolvedValue(user as never);
    const u = userEvent.setup();
    renderAt('/register', <RegisterPage />);
    await u.type(ph('John Trader'), 'Jane');
    await u.type(ph('trader@example.com'), 'jane@example.com');
    await u.type(ph('Min. 8 characters'), 'password123');
    await u.type(ph('Repeat password'), 'password123');
    await u.click(screen.getByRole('button', { name: /Create Account/i }));
    expect(await screen.findByText('INSIDE_DASHBOARD')).toBeInTheDocument();
    expect(api.register).toHaveBeenCalledWith({
      name: 'Jane',
      email: 'jane@example.com',
      password: 'password123',
      confirm_password: 'password123',
    });
    expect(localStorage.getItem('access_token')).toBe('access-123');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-123');
  });
  it('login: on success stores token and redirects to dashboard', async () => {
    vi.mocked(api.login).mockResolvedValue(tokens as never);
    vi.mocked(api.getMe).mockResolvedValue(user as never);
    const u = userEvent.setup();
    renderAt('/login', <LoginPage />);
    await u.type(ph('trader@example.com'), 'trader@example.com');
    await u.type(ph('••••••••'), 'password123');
    await u.click(screen.getByRole('button', { name: /Sign In/i }));
    expect(await screen.findByText('INSIDE_DASHBOARD')).toBeInTheDocument();
    expect(api.login).toHaveBeenCalledWith({ email: 'trader@example.com', password: 'password123' });
    expect(localStorage.getItem('access_token')).toBe('access-123');
  });
  it('login: surfaces backend error detail on failure', async () => {
    vi.mocked(api.login).mockRejectedValue(new ApiError(401, 'Invalid credentials'));
    const u = userEvent.setup();
    renderAt('/login', <LoginPage />);
    await u.type(ph('trader@example.com'), 'trader@example.com');
    await u.type(ph('••••••••'), 'wrongpass');
    await u.click(screen.getByRole('button', { name: /Sign In/i }));
    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument();
    expect(localStorage.getItem('access_token')).toBeNull();
  });
});
