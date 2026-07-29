import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import toast from 'react-hot-toast';
import { api, type UserResponse, ApiError } from '@/lib/api';

interface AuthState {
  user: UserResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string, confirmPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  forgotPassword: (email: string) => Promise<void>;
  updateSettings: (data: { name?: string; default_symbols?: string; timezone?: string }) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const userData = await api.getMe();
      setUser(userData);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Try refresh
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
          try {
            const tokens = await api.refreshToken(refreshToken);
            localStorage.setItem('access_token', tokens.access_token);
            localStorage.setItem('refresh_token', tokens.refresh_token);
            const userData = await api.getMe();
            setUser(userData);
          } catch {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
          }
        } else {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
        }
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const login = async (email: string, password: string) => {
    const tokens = await api.login({ email, password });
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    const userData = await api.getMe();
    setUser(userData);
    toast.success(`Welcome back, ${userData.name}!`);
  };

  const register = async (
    name: string,
    email: string,
    password: string,
    confirmPassword: string,
  ) => {
    const tokens = await api.register({
      name,
      email,
      password,
      confirm_password: confirmPassword,
    });
    localStorage.setItem('access_token', tokens.access_token);
    localStorage.setItem('refresh_token', tokens.refresh_token);
    const userData = await api.getMe();
    setUser(userData);
    toast.success(`Welcome to ForexAI Terminal, ${userData.name}!`);
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // silent
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setUser(null);
    toast.success('Logged out successfully');
  };

  const forgotPassword = async (email: string) => {
    const result = await api.forgotPassword({ email });
    toast.success(result.message);
  };

  const updateSettings = async (data: {
    name?: string;
    default_symbols?: string;
    timezone?: string;
  }) => {
    const updated = await api.updateSettings(data);
    setUser(updated);
    toast.success('Settings updated');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        forgotPassword,
        updateSettings,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
