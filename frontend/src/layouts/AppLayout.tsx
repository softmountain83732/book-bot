// frontend/src/layouts/AppLayout.tsx
import React from 'react';
import { Outlet } from 'react-router-dom';
import { BottomNav } from '../components/BottomNav';
import { useAuth } from '../context/AuthContext';

export const AppLayout: React.FC = () => {
  const { isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="app-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '32px', marginBottom: '12px' }}>📚</div>
          <p style={{ color: 'var(--tg-theme-hint-color)', fontSize: '14px' }}>
            HBTU Marketplace ကို ဖွင့်နေပါသည်...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <main className="main-content">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
};
