// frontend/src/context/AuthContext.tsx
import React, { createContext, useContext, useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import type { AuthResponse, UserProfile } from '../types';

interface AuthContextType {
  user: UserProfile | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  isAdmin: false,
  refreshProfile: async () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { initData, isReady } = useTelegram();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const authenticate = async () => {
    setIsLoading(true);
    try {
      if (initData) {
        // Authenticate with Telegram initData
        const res = await apiClient.post<AuthResponse>('/auth/telegram', {
          init_data: initData,
        });
        localStorage.setItem('hbtu_auth_token', res.data.access_token);
      }

      // Fetch user profile
      const profileRes = await apiClient.get<UserProfile>('/auth/me');
      setUser(profileRes.data);
    } catch (err) {
      console.warn('Authentication skipped or failed (browser dev mode):', err);
      // For local browser testing without Telegram
      if (import.meta.env.DEV && !initData) {
        setUser({
          user_id: 99999999,
          first_name: 'Developer',
          last_name: 'Preview',
          username: 'dev_user',
          language_code: 'my',
          is_admin: true,
          created_at: new Date().toISOString(),
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isReady) {
      authenticate();
    }
  }, [isReady, initData]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        isAdmin: !!user?.is_admin,
        refreshProfile: authenticate,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
