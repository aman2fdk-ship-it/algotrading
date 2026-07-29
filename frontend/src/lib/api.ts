const API_BASE = import.meta.env.VITE_API_URL || '';

interface ApiOptions extends RequestInit {
  skipAuth?: boolean;
}

class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.name = 'ApiError';
  }
}

async function request<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
  const { skipAuth, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((fetchOptions.headers as Record<string, string>) || {}),
  };

  if (!skipAuth) {
    const token = localStorage.getItem('access_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const url = `${API_BASE}/api${endpoint}`;
  const response = await fetch(url, { ...fetchOptions, headers });

  if (!response.ok) {
    let detail = 'An error occurred';
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // use default
    }
    throw new ApiError(response.status, detail);
  }

  return response.json();
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  is_verified: boolean;
  avatar_url: string | null;
  default_symbols: string | null;
  timezone: string | null;
  created_at: string;
  last_login: string | null;
}

export interface MessageResponse {
  message: string;
}

export const api = {
  register: (data: { name: string; email: string; password: string; confirm_password: string }) =>
    request<TokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  login: (data: { email: string; password: string }) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  forgotPassword: (data: { email: string }) =>
    request<MessageResponse>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    }),

  refreshToken: (refreshToken: string) =>
    request<TokenResponse>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipAuth: true,
    }),

  getMe: () => request<UserResponse>('/auth/me'),

  updateSettings: (data: { name?: string; default_symbols?: string; timezone?: string }) =>
    request<UserResponse>('/auth/settings', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  logout: () =>
    request<MessageResponse>('/auth/logout', { method: 'POST' }),
};

export { ApiError };
export type { ApiOptions };
