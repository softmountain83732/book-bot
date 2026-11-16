// frontend/src/pages/AdminPage.tsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShieldAlert, Users, BookOpen, EyeOff, Eye, CheckCircle, XCircle } from 'lucide-react';
import { fetchAdminStats, fetchAdminBooks, moderateBook, fetchReports, resolveReport, type ReportItem } from '../api/admin';
import { useAuth } from '../context/AuthContext';
import { useTelegram } from '../hooks/useTelegram';
import type { Book } from '../types';

export const AdminPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { isAdmin } = useAuth();
  const { triggerHaptic, triggerSuccess } = useTelegram();

  const [activeTab, setActiveTab] = useState<'overview' | 'books' | 'reports'>('overview');
  const [reportFilter, setReportFilter] = useState<'Open' | 'all'>('Open');

  const { data: stats } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: fetchAdminStats,
    enabled: isAdmin,
  });

  const { data: booksData } = useQuery({
    queryKey: ['admin-books'],
    queryFn: () => fetchAdminBooks(),
    enabled: isAdmin && activeTab === 'books',
  });

  const { data: reportsData } = useQuery({
    queryKey: ['admin-reports', reportFilter],
    queryFn: () => fetchReports(reportFilter),
    enabled: isAdmin && activeTab === 'reports',
  });

  const moderateMutation = useMutation({
    mutationFn: ({ bookId, action }: { bookId: string; action: 'hide' | 'unhide' }) => moderateBook(bookId, action),
    onSuccess: () => {
      triggerSuccess();
      queryClient.invalidateQueries({ queryKey: ['admin-books'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
    },
    onError: (err: any) => {
      triggerHaptic('heavy');
      alert(err.response?.data?.detail || 'Moderation error');
    },
  });

  const reportMutation = useMutation({
    mutationFn: ({ reportId, resolution }: { reportId: string; resolution: 'Resolved' | 'Dismissed' }) =>
      resolveReport(reportId, resolution),
    onSuccess: () => {
      triggerSuccess();
      queryClient.invalidateQueries({ queryKey: ['admin-reports'] });
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] });
    },
  });

  if (!isAdmin) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px' }}>
        <ShieldAlert size={48} color="#ef4444" style={{ margin: '0 auto 16px' }} />
        <h2 style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '8px' }}>⛔ ခွင့်ပြုချက် မရှိပါ</h2>
        <p style={{ fontSize: '14px', color: 'var(--tg-theme-hint-color)', marginBottom: '16px' }}>
          ဤ Dashboard သည် Administrator သီးသန့် ဖြစ်ပါသည်။
        </p>
        <button className="btn-secondary" onClick={() => navigate('/')}>
          ပင်မစာမျက်နှာသို့
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingBottom: '32px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <ShieldAlert size={20} color="#ef4444" />
        <h1 style={{ fontSize: '18px', fontWeight: 'bold' }}>Admin Dashboard</h1>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '6px', borderBottom: '1px solid rgba(0,0,0,0.1)', paddingBottom: '6px' }}>
        <button
          onClick={() => setActiveTab('overview')}
          style={{
            padding: '8px 14px',
            borderRadius: '10px',
            border: 'none',
            backgroundColor: activeTab === 'overview' ? 'var(--tg-theme-button-color)' : 'transparent',
            color: activeTab === 'overview' ? 'var(--tg-theme-button-text-color)' : 'var(--tg-theme-text-color)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          ခြုံငုံသုံးသပ်ချက်
        </button>
        <button
          onClick={() => setActiveTab('books')}
          style={{
            padding: '8px 14px',
            borderRadius: '10px',
            border: 'none',
            backgroundColor: activeTab === 'books' ? 'var(--tg-theme-button-color)' : 'transparent',
            color: activeTab === 'books' ? 'var(--tg-theme-button-text-color)' : 'var(--tg-theme-text-color)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          စာအုပ်များ စီမံရန်
        </button>
        <button
          onClick={() => setActiveTab('reports')}
          style={{
            padding: '8px 14px',
            borderRadius: '10px',
            border: 'none',
            backgroundColor: activeTab === 'reports' ? 'var(--tg-theme-button-color)' : 'transparent',
            color: activeTab === 'reports' ? 'var(--tg-theme-button-text-color)' : 'var(--tg-theme-text-color)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Reports ({stats?.open_reports ?? 0})
        </button>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '14px', borderRadius: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: 'var(--tg-theme-hint-color)' }}>
              <Users size={16} />
              <span style={{ fontSize: '12px' }}>Registered Users</span>
            </div>
            <div style={{ fontSize: '22px', fontWeight: 'bold' }}>{stats?.total_users ?? 0}</div>
          </div>

          <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '14px', borderRadius: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: 'var(--tg-theme-hint-color)' }}>
              <BookOpen size={16} />
              <span style={{ fontSize: '12px' }}>စာအုပ် စုစုပေါင်း</span>
            </div>
            <div style={{ fontSize: '22px', fontWeight: 'bold' }}>{stats?.total_books ?? 0}</div>
          </div>

          <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '14px', borderRadius: '12px' }}>
            <div style={{ fontSize: '12px', color: '#15803d', marginBottom: '6px' }}>🟢 Available</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{stats?.available_books ?? 0}</div>
          </div>

          <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '14px', borderRadius: '12px' }}>
            <div style={{ fontSize: '12px', color: '#c2410c', marginBottom: '6px' }}>🟠 Pending (ညှိနှိုင်းဆဲ)</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{stats?.pending_books ?? 0}</div>
          </div>

          <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '14px', borderRadius: '12px' }}>
            <div style={{ fontSize: '12px', color: '#4338ca', marginBottom: '6px' }}>✅ Sold Out</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{stats?.sold_books ?? 0}</div>
          </div>

          <div style={{ backgroundColor: 'var(--tg-theme-secondary-bg-color)', padding: '14px', borderRadius: '12px' }}>
            <div style={{ fontSize: '12px', color: '#ef4444', marginBottom: '6px' }}>🚩 Open Reports</div>
            <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{stats?.open_reports ?? 0}</div>
          </div>
        </div>
      )}

      {/* Books Moderation Tab */}
      {activeTab === 'books' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {booksData?.items.map((book: Book) => (
            <div
              key={book._id}
              style={{
                backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                padding: '12px',
                borderRadius: '10px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <div style={{ fontWeight: 600, fontSize: '13px' }}>{book.title}</div>
                <div style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>
                  Seller ID: {book.seller_id} · {book.status} {book.admin_hidden && '(Hidden)'}
                </div>
              </div>
              <div>
                {book.admin_hidden ? (
                  <button
                    onClick={() => moderateMutation.mutate({ bookId: book._id, action: 'unhide' })}
                    style={{
                      padding: '6px 10px',
                      borderRadius: '8px',
                      border: '1px solid #15803d',
                      color: '#15803d',
                      background: 'transparent',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <Eye size={12} /> Unhide
                  </button>
                ) : (
                  <button
                    onClick={() => moderateMutation.mutate({ bookId: book._id, action: 'hide' })}
                    style={{
                      padding: '6px 10px',
                      borderRadius: '8px',
                      border: '1px solid #ef4444',
                      color: '#ef4444',
                      background: 'transparent',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <EyeOff size={12} /> Hide
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Reports Tab */}
      {activeTab === 'reports' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setReportFilter('Open')}
              style={{
                padding: '4px 10px',
                borderRadius: '14px',
                fontSize: '12px',
                border: 'none',
                backgroundColor: reportFilter === 'Open' ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)',
                color: reportFilter === 'Open' ? 'var(--tg-theme-button-text-color)' : 'var(--tg-theme-text-color)',
                cursor: 'pointer',
              }}
            >
              Open Reports
            </button>
            <button
              onClick={() => setReportFilter('all')}
              style={{
                padding: '4px 10px',
                borderRadius: '14px',
                fontSize: '12px',
                border: 'none',
                backgroundColor: reportFilter === 'all' ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)',
                color: reportFilter === 'all' ? 'var(--tg-theme-button-text-color)' : 'var(--tg-theme-text-color)',
                cursor: 'pointer',
              }}
            >
              History
            </button>
          </div>

          {reportsData?.items.map((rep: ReportItem) => (
            <div
              key={rep.id}
              style={{
                backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                padding: '12px',
                borderRadius: '10px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 600, fontSize: '13px' }}>{rep.book_title}</span>
                <span style={{ fontSize: '11px', fontWeight: 600, color: rep.status === 'Open' ? '#ef4444' : '#15803d' }}>
                  {rep.status}
                </span>
              </div>
              <div style={{ fontSize: '12px', color: 'var(--tg-theme-hint-color)' }}>
                အကြောင်းရင်း: <b>{rep.reason_label}</b>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>
                Reporter: {rep.reporter_id} · Seller: {rep.seller_id}
              </div>

              {rep.status === 'Open' && (
                <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                  <button
                    onClick={() => reportMutation.mutate({ reportId: rep.id, resolution: 'Resolved' })}
                    style={{
                      flex: 1,
                      padding: '6px',
                      borderRadius: '6px',
                      border: '1px solid #15803d',
                      color: '#15803d',
                      background: 'transparent',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '4px',
                    }}
                  >
                    <CheckCircle size={12} /> ဖြေရှင်းပြီး
                  </button>
                  <button
                    onClick={() => reportMutation.mutate({ reportId: rep.id, resolution: 'Dismissed' })}
                    style={{
                      flex: 1,
                      padding: '6px',
                      borderRadius: '6px',
                      border: '1px solid var(--tg-theme-hint-color)',
                      color: 'var(--tg-theme-hint-color)',
                      background: 'transparent',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '4px',
                    }}
                  >
                    <XCircle size={12} /> ပယ်ချမည်
                  </button>
                </div>
              )}
            </div>
          ))}

          {reportsData?.items.length === 0 && (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--tg-theme-hint-color)', fontSize: '13px' }}>
              Report မရှိပါ။
            </div>
          )}
        </div>
      )}
    </div>
  );
};
