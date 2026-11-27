// frontend/src/pages/HomePage.tsx
import React from 'react';
import { Search, ChevronRight, BookPlus, ShieldCheck, Sparkles, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MAJORS } from '../types';
import { useAuth } from '../context/AuthContext';
import { useTelegram } from '../hooks/useTelegram';
import { fetchBooks } from '../api/books';
import { BookCard } from '../components/BookCard';
import { BookCardSkeleton } from '../components/BookCardSkeleton';

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const { triggerHaptic } = useTelegram();

  const years = [1, 2, 3, 4, 5, 6];

  // Fetch recently listed available books
  const {
    data: recentBooksData,
    isLoading: isRecentLoading,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: ['recent-books'],
    queryFn: () => fetchBooks({ page: 1, page_size: 6 }),
    staleTime: 60 * 1000,
  });

  const recentBooks = recentBooksData?.items ?? [];
  const adminContactUrl = (import.meta.env.VITE_ADMIN_CONTACT_URL || '').trim();

  const handleRefresh = () => {
    triggerHaptic('light');
    refetch();
  };

  const handleContactAdmin = () => {
    if (!adminContactUrl) return;
    triggerHaptic('light');
    const tg = window.Telegram?.WebApp;
    if (tg && adminContactUrl.startsWith('https://t.me/')) {
      tg.openTelegramLink(adminContactUrl);
    } else if (tg && typeof tg.openLink === 'function') {
      tg.openLink(adminContactUrl);
    } else {
      window.open(adminContactUrl, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <h1 style={{ fontSize: '20px', fontWeight: 'bold' }}>
            မင်္ဂလာပါ {user?.first_name || 'မိတ်ဆွေ'} 👋
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)' }}>
            HBTU Book Marketplace မှ ကြိုဆိုပါသည်
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {adminContactUrl && (
            <button
              type="button"
              onClick={handleContactAdmin}
              className="contact-admin-btn"
              aria-label="Contact Admin"
            >
              <span className="contact-admin-btn__label">Contact Admin</span>
            </button>
          )}
          <button
            onClick={handleRefresh}
            aria-label="Refresh"
            style={{
              padding: '8px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--tg-theme-secondary-bg-color)',
              color: 'var(--tg-theme-hint-color)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <RefreshCw size={16} className={isRefetching ? 'animate-spin' : ''} />
          </button>
          {isAdmin && (
            <button
              onClick={() => {
                triggerHaptic('light');
                navigate('/admin');
              }}
              style={{
                padding: '6px 10px',
                borderRadius: '8px',
                border: 'none',
                background: '#ef4444',
                color: '#fff',
                fontSize: '12px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                cursor: 'pointer',
              }}
            >
              <ShieldCheck size={14} />
              Admin
            </button>
          )}
        </div>
      </div>

      {/* Search Bar Shortcut */}
      <div
        onClick={() => {
          triggerHaptic('light');
          navigate('/browse');
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '12px 14px',
          borderRadius: '12px',
          backgroundColor: 'var(--tg-theme-secondary-bg-color)',
          color: 'var(--tg-theme-hint-color)',
          cursor: 'pointer',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        <Search size={18} />
        <span style={{ fontSize: '14px' }}>စာအုပ်အမည်ဖြင့် ရှာဖွေမည်...</span>
      </div>

      {/* Sell Callout Banner */}
      <div
        onClick={() => {
          triggerHaptic('light');
          navigate('/sell');
        }}
        style={{
          padding: '16px',
          borderRadius: '14px',
          background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
          color: '#ffffff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          boxShadow: '0 4px 12px rgba(37, 99, 235, 0.25)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              backgroundColor: 'rgba(255, 255, 255, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <BookPlus size={24} />
          </div>
          <div>
            <div style={{ fontWeight: 'bold', fontSize: '15px' }}>စာအုပ် ရောင်းချင်တာလား</div>
            <div style={{ fontSize: '12px', opacity: 0.9 }}>ဒီကနေ ကျောင်းသားအချင်းချင်းရောင်းနိုင်ပါတယ်</div>
          </div>
        </div>
        <ChevronRight size={20} />
      </div>

      {/* Year Filter Pills */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <h2 style={{ fontSize: '15px', fontWeight: 600 }}>🎓 ပညာသင်နှစ်အလိုက် ရှာရန်</h2>
          <span
            onClick={() => {
              triggerHaptic('light');
              navigate('/browse');
            }}
            style={{ fontSize: '12px', color: 'var(--tg-theme-link-color)', cursor: 'pointer', fontWeight: 500 }}
          >
            အားလုံးကြည့်ရန် →
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
          {years.map((yr) => (
            <div
              key={yr}
              onClick={() => {
                triggerHaptic('light');
                navigate(`/browse?year=${yr}`);
              }}
              style={{
                padding: '12px 8px',
                borderRadius: '10px',
                backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                textAlign: 'center',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '13px',
                transition: 'transform 0.1s ease',
              }}
              className="card-press"
            >
              Year {yr}
            </div>
          ))}
        </div>
      </div>

      {/* Majors Shortcuts */}
      <div>
        <h2 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '10px' }}>
          📚 မေဂျာအလိုက် ကြည့်ရန်
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {MAJORS.map((m) => (
            <span
              key={m.slug}
              onClick={() => {
                triggerHaptic('light');
                navigate(`/browse?major=${m.slug}`);
              }}
              style={{
                padding: '8px 14px',
                borderRadius: '20px',
                backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                fontSize: '13px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
              className="card-press"
            >
              {m.name}
            </span>
          ))}
        </div>
      </div>

      {/* Recently Listed Books Section */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <h2 style={{ fontSize: '15px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Sparkles size={16} color="var(--tg-theme-button-color)" />
            အသစ်တင်ထားသော စာအုပ်များ
          </h2>
          <span
            onClick={() => {
              triggerHaptic('light');
              navigate('/browse');
            }}
            style={{ fontSize: '12px', color: 'var(--tg-theme-link-color)', cursor: 'pointer', fontWeight: 500 }}
          >
            အားလုံး ({recentBooksData?.total ?? 0}) →
          </span>
        </div>

        {isRecentLoading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
            <BookCardSkeleton />
            <BookCardSkeleton />
          </div>
        ) : recentBooks.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
            {recentBooks.map((book) => (
              <BookCard
                key={book._id}
                book={book}
                onClick={() => navigate(`/books/${book._id}`)}
              />
            ))}
          </div>
        ) : (
          <div
            style={{
              padding: '24px 16px',
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              borderRadius: '12px',
              textAlign: 'center',
              color: 'var(--tg-theme-hint-color)',
              fontSize: '13px',
            }}
          >
            လောလောဆယ် ရောင်းရန်တင်ထားသော စာအုပ်မရှိသေးပါ။
          </div>
        )}
      </div>
    </div>
  );
};
