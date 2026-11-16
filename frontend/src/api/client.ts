// frontend/src/api/client.ts
import axios from 'axios';

// When running in development, proxies to http://localhost:8000
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Request interceptor: Attach JWT token or Telegram initData
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('hbtu_auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Attach raw Telegram.WebApp.initData if present
    if (window.Telegram?.WebApp?.initData) {
      config.headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: Handle session expiration
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('hbtu_auth_token');
    }
    return Promise.reject(error);
  }
);
