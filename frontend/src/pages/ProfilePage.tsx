// frontend/src/pages/ProfilePage.tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { User, BookOpen, ShoppingBag, Heart, ShieldCheck, ExternalLink, Bell } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTelegram } from '../hooks/useTelegram';

export const ProfilePage: React.FC = () => {
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const { triggerHaptic } = useTelegram();

  const handleNav = (path: string) => {
    triggerHaptic('light');
    navigate(path);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingBottom: '32px' }}>
      <h1 style={{ fontSize: '18px', fontWeight: 'bold' }}>👤 ကျွန်ုပ်၏ Profile</h1>

      {/* Profile Card */}
      <div
        style={{
          backgroundColor: 'var(--tg-theme-secondary-bg-color)',
          borderRadius: '16px',
          padding: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: '14px',
          border: '1px solid rgba(0,0,0,0.04)',
        }}
      >
        <div
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            backgroundColor: 'var(--tg-theme-button-color)',
            color: 'var(--tg-theme-button-text-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '22px',
            fontWeight: 'bold',
          }}
        >
          {user?.first_name ? user.first_name[0] : <User size={28} />}
        </div>

        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '16px', fontWeight: 'bold' }}>
            {user?.first_name} {user?.last_name || ''}
          </div>
          {user?.username && (
            <div style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)' }}>
              @{user.username}
            </div>
          )}
          <div style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)', marginTop: '2px' }}>
            User ID: <code>{user?.user_id}</code>
          </div>
        </div>

        {isAdmin && (
          <span
            style={{
              padding: '4px 8px',
              borderRadius: '8px',
              backgroundColor: '#ef4444',
              color: '#fff',
              fontSize: '11px',
              fontWeight: 'bold',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <ShieldCheck size={12} />
            Admin
          </span>
        )}
      </div>

      {/* Notifications Notice */}
      <div
        style={{
          backgroundColor: 'rgba(59,130,246,0.08)',
          border: '1px solid rgba(59,130,246,0.2)',
          borderRadius: '12px',
          padding: '12px 14px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px',
        }}
      >
        <Bell size={20} color="#2563eb" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div style={{ fontSize: '12px', lineHeight: 1.5 }}>
          <b>Telegram Bot အသိပေးချက်များ</b><br />
          ဝယ်ယူမှု၊ ရောင်းချမှုနှင့် အတည်ပြုချက်ဆိုင်ရာ အသိပေးစာများကို Bot Private Chat တွင် အလိုအလျောက် ပေးပို့ပေးပါမည်။
        </div>
      </div>

      {/* Quick Navigation Menu */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h2 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--tg-theme-hint-color)' }}>
          ဖြတ်လမ်းများ
        </h2>

        <div
          onClick={() => handleNav('/my-books')}
          style={{
            backgroundColor: 'var(--tg-theme-secondary-bg-color)',
            padding: '14px',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <BookOpen size={18} color="var(--tg-theme-button-color)" />
            <span style={{ fontSize: '14px', fontWeight: 500 }}>ကျွန်ုပ်၏ စာအုပ်များ (My Books)</span>
          </div>
          <ExternalLink size={16} color="var(--tg-theme-hint-color)" />
        </div>

        <div
          onClick={() => handleNav('/purchases')}
          style={{
            backgroundColor: 'var(--tg-theme-secondary-bg-color)',
            padding: '14px',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ShoppingBag size={18} color="var(--tg-theme-button-color)" />
            <span style={{ fontSize: '14px', fontWeight: 500 }}>ဝယ်ယူမှု မှတ်တမ်းများ (Purchases)</span>
          </div>
          <ExternalLink size={16} color="var(--tg-theme-hint-color)" />
        </div>

        <div
          onClick={() => handleNav('/favorites')}
          style={{
            backgroundColor: 'var(--tg-theme-secondary-bg-color)',
            padding: '14px',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            cursor: 'pointer',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Heart size={18} color="#ef4444" />
            <span style={{ fontSize: '14px', fontWeight: 500 }}>သိမ်းထားသော စာအုပ်များ (Favorites)</span>
          </div>
          <ExternalLink size={16} color="var(--tg-theme-hint-color)" />
        </div>

        {isAdmin && (
          <div
            onClick={() => handleNav('/admin')}
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              padding: '14px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <ShieldCheck size={18} color="#ef4444" />
              <span style={{ fontSize: '14px', fontWeight: 500, color: '#ef4444' }}>Admin Panel</span>
            </div>
            <ExternalLink size={16} color="var(--tg-theme-hint-color)" />
          </div>
        )}
      </div>
    </div>
  );
};
