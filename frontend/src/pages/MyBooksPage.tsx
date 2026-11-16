// frontend/src/pages/MyBooksPage.tsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Pause, Play, Trash2, AlertCircle } from 'lucide-react';
import { fetchMyBooks, fetchSellerMetrics, executeListingAction } from '../api/myBooks';
import { getStatusBadgeClass, getStatusLabel, formatPrice, formatSemesterDisplay } from '../utils/semester';
import { getPhotoUrl } from '../api/books';
import { useTelegram } from '../hooks/useTelegram';
import type { Book } from '../types';

export const MyBooksPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { triggerHaptic, triggerSuccess } = useTelegram();

  const [activeTab, setActiveTab] = useState<string>('all');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const { data: metrics } = useQuery({
    queryKey: ['seller-metrics'],
    queryFn: fetchSellerMetrics,
  });

  const { data: booksData, isLoading, error } = useQuery({
    queryKey: ['my-books', activeTab],
    queryFn: () => fetchMyBooks(activeTab),
  });

  const actionMutation = useMutation({
    mutationFn: ({ bookId, action }: { bookId: string; action: 'delist' | 'relist' | 'delete' }) =>
      executeListingAction(bookId, action),
    onSuccess: () => {
      triggerSuccess();
      setConfirmDeleteId(null);
      queryClient.invalidateQueries({ queryKey: ['my-books'] });
      queryClient.invalidateQueries({ queryKey: ['seller-metrics'] });
    },
    onError: (err: any) => {
      triggerHaptic('heavy');
      alert(err.response?.data?.detail || 'လုပ်ဆောင်ချက် မအောင်မြင်ပါ။');
      setConfirmDeleteId(null);
    },
  });

  const tabs = [
    { id: 'all', label: 'အားလုံး' },
    { id: 'Available', label: 'ရောင်းရန်ရှိ' },
    { id: 'Pending', label: 'ညှိနှိုင်းဆဲ' },
    { id: 'Delisted', label: 'Delisted' },
    { id: 'Sold', label: 'ရောင်းပြီး' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingBottom: '32px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <BookOpen size={20} color="var(--tg-theme-button-color)" />
        <h1 style={{ fontSize: '18px', fontWeight: 'bold' }}>ကျွန်ုပ်၏ စာအုပ်များ</h1>
      </div>

      {/* Metrics Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '8px',
          textAlign: 'center',
        }}
      >
        <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '10px 4px', borderRadius: '10px' }}>
          <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#15803d' }}>{metrics?.active_count ?? 0}</div>
          <div style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>ရောင်းရန်ရှိ</div>
        </div>
        <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '10px 4px', borderRadius: '10px' }}>
          <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#c2410c' }}>{metrics?.pending_count ?? 0}</div>
          <div style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>ညှိနှိုင်းဆဲ</div>
        </div>
        <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '10px 4px', borderRadius: '10px' }}>
          <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#4338ca' }}>{metrics?.sold_count ?? 0}</div>
          <div style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>ရောင်းပြီး</div>
        </div>
        <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '10px 4px', borderRadius: '10px' }}>
          <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#b91c1c' }}>{metrics?.delisted_count ?? 0}</div>
          <div style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>Delisted</div>
        </div>
      </div>

      {/* Status Filter Tabs */}
      <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '4px' }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              triggerHaptic('light');
              setActiveTab(tab.id);
            }}
            style={{
              padding: '6px 12px',
              borderRadius: '20px',
              border: activeTab === tab.id ? 'none' : '1px solid rgba(0,0,0,0.1)',
              backgroundColor: activeTab === tab.id ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)',
              color: activeTab === tab.id ? 'var(--tg-theme-button-text-color)' : 'var(--tg-theme-text-color)',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--tg-theme-hint-color)' }}>
          စာအုပ်များ ရယူနေပါသည်...
        </div>
      )}

      {error && (
        <div style={{ textAlign: 'center', padding: '32px 16px' }}>
          <p style={{ color: 'var(--tg-theme-hint-color)' }}>ဒေတာ ရယူ၍ မရပါ။</p>
        </div>
      )}

      {/* Listings List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {booksData?.items.map((book: Book) => (
          <div
            key={book._id}
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              borderRadius: '12px',
              padding: '12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
              border: '1px solid rgba(0,0,0,0.04)',
            }}
          >
            <div style={{ display: 'flex', gap: '10px' }}>
              {/* Thumbnail */}
              <div
                style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  backgroundColor: 'rgba(0,0,0,0.06)',
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {book.has_photos || (book.photo_count ?? 0) > 0 || (book.photo_file_ids && book.photo_file_ids.length > 0) ? (
                  <img src={getPhotoUrl(book._id, 0)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
                ) : (
                  <span>📚</span>
                )}
              </div>

              {/* Title & Status */}
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '14px', lineHeight: 1.3, marginBottom: '4px' }}>
                  {book.title}
                </div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--tg-theme-button-color)', marginBottom: '4px' }}>
                  {formatPrice(book.price, book.is_negotiable)}
                </div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                  <span className={getStatusBadgeClass(book.status)} style={{ fontSize: '10px', padding: '2px 6px' }}>
                    {getStatusLabel(book.status)}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>
                    Year {book.year} · {formatSemesterDisplay(book.year, book.semester)}
                  </span>
                </div>
              </div>
            </div>

            {/* Management Actions */}
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', borderTop: '1px solid rgba(0,0,0,0.06)', paddingTop: '8px' }}>
              {book.status === 'Available' && (
                <button
                  onClick={() => actionMutation.mutate({ bookId: book._id, action: 'delist' })}
                  style={{
                    backgroundColor: 'transparent',
                    border: '1px solid var(--tg-theme-hint-color)',
                    borderRadius: '8px',
                    padding: '6px 10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <Pause size={12} />
                  Delist
                </button>
              )}

              {book.status === 'Delisted' && (
                <button
                  onClick={() => actionMutation.mutate({ bookId: book._id, action: 'relist' })}
                  style={{
                    backgroundColor: 'transparent',
                    border: '1px solid #15803d',
                    color: '#15803d',
                    borderRadius: '8px',
                    padding: '6px 10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <Play size={12} />
                  Relist
                </button>
              )}

              {book.status !== 'Pending' && book.status !== 'Deleted' && (
                <button
                  onClick={() => {
                    triggerHaptic('medium');
                    setConfirmDeleteId(book._id);
                  }}
                  style={{
                    backgroundColor: 'transparent',
                    border: '1px solid #ef4444',
                    color: '#ef4444',
                    borderRadius: '8px',
                    padding: '6px 10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    cursor: 'pointer',
                  }}
                >
                  <Trash2 size={12} />
                  Channel Post ဖျက်မည်
                </button>
              )}
            </div>
          </div>
        ))}

        {!isLoading && !error && booksData?.items.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 16px' }}>
            <p style={{ fontSize: '48px', marginBottom: '12px' }}>📖</p>
            <p style={{ fontWeight: 600, marginBottom: '6px' }}>စာအုပ် မရှိသေးပါ</p>
            <button className="btn-primary" style={{ marginTop: '12px' }} onClick={() => navigate('/sell')}>
              စာအုပ် အသစ်တင်မည်
            </button>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {confirmDeleteId && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '20px',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--tg-theme-bg-color)',
              borderRadius: '16px',
              padding: '20px',
              maxWidth: '320px',
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              textAlign: 'center',
            }}
          >
            <AlertCircle size={40} color="#ef4444" style={{ margin: '0 auto' }} />
            <h3 style={{ fontSize: '16px', fontWeight: 'bold' }}>Channel Post ဖျက်မှာ သေချာပါသလား?</h3>
            <p style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)' }}>
              Telegram Channel ပေါ်ရှိ ဓာတ်ပုံနှင့် စာသားအားလုံးကို အပြီးဖျက်မည်ဖြစ်ပြီး၊ Database တွင် Deleted အဖြစ် သိမ်းဆည်းထားပါမည်။
            </p>
            <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
              <button
                className="btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setConfirmDeleteId(null)}
              >
                မဖျက်တော့ပါ
              </button>
              <button
                className="btn-primary"
                style={{ flex: 1, backgroundColor: '#ef4444' }}
                onClick={() => actionMutation.mutate({ bookId: confirmDeleteId, action: 'delete' })}
                disabled={actionMutation.isPending}
              >
                {actionMutation.isPending ? 'ဖျက်နေပါသည်...' : 'အပြီးဖျက်မည်'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
