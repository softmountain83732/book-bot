// frontend/src/pages/PurchasesPage.tsx
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShoppingBag, AlertCircle } from 'lucide-react';
import { fetchPurchaseHistory, cancelPurchaseRequest, type PurchaseHistoryItem } from '../api/purchases';
import { useTelegram } from '../hooks/useTelegram';

export const PurchasesPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { triggerHaptic, triggerSuccess } = useTelegram();
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['purchases-history'],
    queryFn: () => fetchPurchaseHistory(1, 50),
  });

  const cancelMutation = useMutation({
    mutationFn: (requestId: string) => cancelPurchaseRequest(requestId),
    onSuccess: () => {
      triggerSuccess();
      setShowConfirmModal(null);
      setCancellingId(null);
      queryClient.invalidateQueries({ queryKey: ['purchases-history'] });
    },
    onError: (err: any) => {
      triggerHaptic('heavy');
      alert(err.response?.data?.detail || 'Cancellation failed');
      setCancellingId(null);
    },
  });

  const handleCancelClick = (reqId: string) => {
    triggerHaptic('medium');
    setShowConfirmModal(reqId);
  };

  const confirmCancel = () => {
    if (!showConfirmModal) return;
    setCancellingId(showConfirmModal);
    cancelMutation.mutate(showConfirmModal);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Pending':
        return <span className="badge badge-pending">စောင့်ဆိုင်းဆဲ</span>;
      case 'Sold':
        return <span className="badge badge-sold">အောင်မြင်သည်</span>;
      case 'CancelledByBuyer':
      case 'CancelledBySeller':
      case 'AdminCancelled':
        return <span className="badge badge-cancelled">ပယ်ဖျက်ပြီး</span>;
      default:
        return <span className="badge badge-cancelled">{status}</span>;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <ShoppingBag size={20} color="var(--tg-theme-button-color)" />
        <h1 style={{ fontSize: '18px', fontWeight: 'bold' }}>ဝယ်ယူမှု မှတ်တမ်း</h1>
      </div>

      {isLoading && (
        <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--tg-theme-hint-color)' }}>
          မှတ်တမ်းများကို ရယူနေပါသည်...
        </div>
      )}

      {error && (
        <div style={{ textAlign: 'center', padding: '32px 16px' }}>
          <AlertCircle size={32} color="#ef4444" style={{ marginBottom: '8px' }} />
          <p style={{ color: 'var(--tg-theme-hint-color)' }}>ဒေတာ ရယူ၍ မရပါ။</p>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {data?.items.map((item: PurchaseHistoryItem) => (
          <div
            key={item.id}
            style={{
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              borderRadius: '12px',
              padding: '12px 14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              border: '1px solid rgba(0,0,0,0.04)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ fontWeight: 600, fontSize: '14px', flex: 1 }}>{item.book_title}</div>
              {getStatusBadge(item.status)}
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--tg-theme-hint-color)' }}>
              <span>
                {item.price ? `${item.price.toLocaleString()} MMK` : 'ညှိနှိုင်း'}
              </span>
              <span>{new Date(item.created_at).toLocaleDateString()}</span>
            </div>

            {item.status === 'Pending' && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
                <button
                  onClick={() => handleCancelClick(item.id)}
                  disabled={cancellingId === item.id}
                  style={{
                    backgroundColor: 'transparent',
                    border: '1px solid #ef4444',
                    color: '#ef4444',
                    borderRadius: '8px',
                    padding: '6px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {cancellingId === item.id ? 'ပယ်ဖျက်နေပါသည်...' : 'ဝယ်ယူမှု ပယ်ဖျက်မည်'}
                </button>
              </div>
            )}
          </div>
        ))}

        {!isLoading && !error && data?.items.length === 0 && (
          <div style={{ textAlign: 'center', padding: '48px 16px' }}>
            <ShoppingBag size={48} color="var(--tg-theme-hint-color)" style={{ marginBottom: '12px' }} />
            <p style={{ fontWeight: 600, marginBottom: '6px' }}>ဝယ်ယူမှု မှတ်တမ်း မရှိသေးပါ</p>
          </div>
        )}
      </div>

      {/* Confirmation Dialog */}
      {showConfirmModal && (
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
            <AlertCircle size={40} color="#f59e0b" style={{ margin: '0 auto' }} />
            <h3 style={{ fontSize: '16px', fontWeight: 'bold' }}>ဝယ်ယူမှု ပယ်ဖျက်မည်လား?</h3>
            <p style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)' }}>
              ဒီ Purchase Request ကို ပယ်ဖျက်ပြီး စာအုပ်ကို အများပြည်သူဝယ်ယူနိုင်အောင် ပြန်ဖွင့်ပေးပါမည်။
            </p>
            <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
              <button
                className="btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setShowConfirmModal(null)}
              >
                မလုပ်တော့ပါ
              </button>
              <button
                className="btn-primary"
                style={{ flex: 1, backgroundColor: '#ef4444' }}
                onClick={confirmCancel}
              >
                ပယ်ဖျက်မည်
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
