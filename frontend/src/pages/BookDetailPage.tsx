// frontend/src/pages/BookDetailPage.tsx
import React, { useEffect, useState, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Heart, Flag, CheckCircle, AlertTriangle, X } from 'lucide-react';
import { fetchBookById, getPhotoUrl } from '../api/books';
import { addFavorite, removeFavorite } from '../api/favorites';
import { requestBuyBook } from '../api/purchases';
import { submitBookReport } from '../api/reports';
import { formatSemesterDisplay, formatPrice, getStatusBadgeClass, getStatusLabel } from '../utils/semester';
import { useAuth } from '../context/AuthContext';
import { useTelegram } from '../hooks/useTelegram';

const REPORT_REASONS = [
  { key: 'fake', label: 'သတင်းအချက်အလက် မမှန်ကန်ခြင်း' },
  { key: 'spam', label: 'ကြော်ငြာ/Spam ဖြစ်ခြင်း' },
  { key: 'offensive', label: 'မလျော်ကန်သော အကြောင်းအရာပါဝင်ခြင်း' },
  { key: 'wrong_major', label: 'မေဂျာ/ပညာသင်နှစ် မှားယွင်းနေခြင်း' },
  { key: 'other', label: 'အခြား အကြောင်းရင်း' },
];

export const BookDetailPage: React.FC = () => {
  const { bookId } = useParams<{ bookId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { tg, triggerHaptic, triggerSuccess, triggerError } = useTelegram();
  const [photoIndex, setPhotoIndex] = useState(0);
  const [imgError, setImgError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [showBuyConfirm, setShowBuyConfirm] = useState(false);
  const [buyMessage, setBuyMessage] = useState<string | null>(null);

  // Report Modal state
  const [showReportModal, setShowReportModal] = useState(false);
  const [reportReason, setReportReason] = useState('fake');
  const [reportNotes, setReportNotes] = useState('');
  const [reportSuccess, setReportSuccess] = useState<string | null>(null);

  // Touch swipe support for photo gallery
  const touchStartXRef = useRef<number | null>(null);

  const { data: book, isLoading, error } = useQuery({
    queryKey: ['book', bookId],
    queryFn: () => fetchBookById(bookId!),
    enabled: !!bookId,
  });

  const [isFav, setIsFav] = useState<boolean>(false);

  useEffect(() => {
    if (book) {
      setIsFav(book.is_favorite ?? false);
    }
  }, [book]);

  // Telegram BackButton integration
  useEffect(() => {
    if (!tg) return;
    tg.BackButton.show();
    const handler = () => navigate(-1);
    tg.BackButton.onClick(handler);
    return () => {
      tg.BackButton.offClick(handler);
      tg.BackButton.hide();
    };
  }, [tg, navigate]);

  const toggleFavMutation = useMutation({
    mutationFn: () => (isFav ? removeFavorite(bookId!) : addFavorite(bookId!)),
    onSuccess: (res) => {
      triggerHaptic('medium');
      setIsFav(res.is_favorite);
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
    },
  });

  const buyMutation = useMutation({
    mutationFn: () => requestBuyBook(bookId!),
    onSuccess: (res) => {
      triggerSuccess();
      setShowBuyConfirm(false);
      setBuyMessage(res.message);
      queryClient.invalidateQueries({ queryKey: ['book', bookId] });
      queryClient.invalidateQueries({ queryKey: ['purchases-history'] });
    },
    onError: (err: any) => {
      triggerError();
      alert(err.response?.data?.detail || 'ဝယ်ယူမှု စတင်၍ မရပါ။');
      setShowBuyConfirm(false);
    },
  });

  const reportMutation = useMutation({
    mutationFn: () =>
      submitBookReport({
        book_id: bookId!,
        reason: reportReason,
        notes: reportNotes || undefined,
      }),
    onSuccess: (res) => {
      triggerSuccess();
      setReportSuccess(res.message);
      setTimeout(() => {
        setShowReportModal(false);
        setReportSuccess(null);
        setReportNotes('');
      }, 1500);
    },
    onError: (err: any) => {
      triggerError();
      alert(err.response?.data?.detail || 'Report တင်၍ မရပါ။ ထပ်မံကြိုးစားပါ။');
    },
  });

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div
          style={{
            width: '100%',
            aspectRatio: '4/3',
            backgroundColor: 'var(--tg-theme-secondary-bg-color)',
            borderRadius: '12px',
            animation: 'skeleton-pulse 1.4s ease-in-out infinite',
          }}
        />
        <div style={{ height: '20px', width: '70%', backgroundColor: 'var(--tg-theme-secondary-bg-color)', borderRadius: '6px' }} />
        <div style={{ height: '16px', width: '40%', backgroundColor: 'var(--tg-theme-secondary-bg-color)', borderRadius: '6px' }} />
        <style>{`@keyframes skeleton-pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
      </div>
    );
  }

  if (error || !book) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 16px' }}>
        <p style={{ fontSize: '48px', marginBottom: '12px' }}>⚠️</p>
        <p style={{ fontWeight: 600, marginBottom: '8px' }}>စာအုပ် ရှာမတွေ့ပါ</p>
        <p style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)', marginBottom: '16px' }}>
          ဤ listing ကို ဖျက်ထားနိုင်သည် သို့မဟုတ် မရနိုင်ပါ။
        </p>
        <button className="btn-secondary" onClick={() => navigate(-1)}>
          ← နောက်သို့ ပြန်သွားမည်
        </button>
      </div>
    );
  }

  const photoCount =
    typeof book.photo_count === 'number' && book.photo_count > 0
      ? book.photo_count
      : book.has_photos
      ? 1
      : (book.photo_file_ids?.length ?? 0);

  const prevPhoto = () => {
    triggerHaptic('light');
    setPhotoIndex((i) => Math.max(0, i - 1));
    setImgError(false);
  };

  const nextPhoto = () => {
    triggerHaptic('light');
    setPhotoIndex((i) => Math.min(photoCount - 1, i + 1));
    setImgError(false);
  };

  const handleRetryPhoto = () => {
    triggerHaptic('light');
    setImgError(false);
    setRetryKey((k) => k + 1);
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartXRef.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStartXRef.current === null) return;
    const touchEndX = e.changedTouches[0].clientX;
    const diff = touchStartXRef.current - touchEndX;

    if (Math.abs(diff) > 40) {
      if (diff > 0 && photoIndex < photoCount - 1) {
        nextPhoto();
      } else if (diff < 0 && photoIndex > 0) {
        prevPhoto();
      }
    }
    touchStartXRef.current = null;
  };

  const isSeller = user?.user_id === book.seller_id;
  const canBuy = book.status === 'Available' && !isSeller;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingBottom: '24px' }}>
      {/* Photo Gallery with Touch Swipe */}
      {photoCount > 0 ? (
        <div
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', touchAction: 'pan-y' }}
        >
          <div
            style={{
              width: '100%',
              aspectRatio: '4/3',
              backgroundColor: 'var(--tg-theme-secondary-bg-color)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {!imgError ? (
              <img
                key={`${photoIndex}-${retryKey}`}
                src={`${getPhotoUrl(book._id, photoIndex)}${retryKey > 0 ? `?retry=${retryKey}` : ''}`}
                alt={`${book.title} photo ${photoIndex + 1}`}
                onError={() => setImgError(true)}
                loading="eager"
                decoding="async"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            ) : (
              <div style={{ textAlign: 'center', padding: '16px', color: 'var(--tg-theme-hint-color)' }}>
                <span style={{ fontSize: '48px', display: 'block', marginBottom: '8px' }}>📚</span>
                <p style={{ fontSize: '13px', marginBottom: '8px' }}>ဓာတ်ပုံ ဖွင့်မရသေးပါ</p>
                <button
                  type="button"
                  onClick={handleRetryPhoto}
                  style={{
                    padding: '6px 12px',
                    fontSize: '12px',
                    borderRadius: '8px',
                    border: '1px solid var(--tg-theme-button-color)',
                    background: 'transparent',
                    color: 'var(--tg-theme-button-color)',
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  🔄 ပြန်လည်ကြိုးစားမည်
                </button>
              </div>
            )}
          </div>

          {/* Nav arrows */}
          {photoCount > 1 && (
            <>
              {photoIndex > 0 && (
                <button
                  onClick={prevPhoto}
                  aria-label="Previous photo"
                  style={{
                    position: 'absolute',
                    left: '8px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'rgba(0,0,0,0.5)',
                    border: 'none',
                    borderRadius: '50%',
                    width: '36px',
                    height: '36px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    color: '#fff',
                  }}
                >
                  <ChevronLeft size={20} />
                </button>
              )}
              {photoIndex < photoCount - 1 && (
                <button
                  onClick={nextPhoto}
                  aria-label="Next photo"
                  style={{
                    position: 'absolute',
                    right: '8px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'rgba(0,0,0,0.5)',
                    border: 'none',
                    borderRadius: '50%',
                    width: '36px',
                    height: '36px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    color: '#fff',
                  }}
                >
                  <ChevronRight size={20} />
                </button>
              )}

              {/* Dot indicators */}
              <div
                style={{
                  position: 'absolute',
                  bottom: '10px',
                  left: 0,
                  right: 0,
                  display: 'flex',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                {Array.from({ length: photoCount }).map((_, i) => (
                  <div
                    key={i}
                    onClick={() => {
                      setPhotoIndex(i);
                      setImgError(false);
                    }}
                    style={{
                      width: i === photoIndex ? '16px' : '6px',
                      height: '6px',
                      borderRadius: '3px',
                      backgroundColor: i === photoIndex ? '#fff' : 'rgba(255,255,255,0.5)',
                      transition: 'all 0.2s',
                      cursor: 'pointer',
                    }}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        <div
          style={{
            width: '100%',
            aspectRatio: '4/3',
            borderRadius: '12px',
            backgroundColor: 'var(--tg-theme-secondary-bg-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span style={{ fontSize: '64px' }}>📚</span>
        </div>
      )}

      {/* Buy success message banner */}
      {buyMessage && (
        <div
          style={{
            backgroundColor: '#dcfce7',
            color: '#15803d',
            padding: '12px 14px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '13px',
            fontWeight: 500,
          }}
        >
          <CheckCircle size={18} />
          <span>{buyMessage}</span>
        </div>
      )}

      {/* Title & Status */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
        <h1 style={{ fontSize: '18px', fontWeight: 'bold', flex: 1, lineHeight: 1.4 }}>{book.title}</h1>
        <span className={getStatusBadgeClass(book.status)} style={{ flexShrink: 0 }}>
          {getStatusLabel(book.status)}
        </span>
      </div>

      {/* Price */}
      <p style={{ fontSize: '22px', fontWeight: 'bold', color: 'var(--tg-theme-button-color)' }}>
        {formatPrice(book.price, book.is_negotiable)}
      </p>

      {/* Detail fields */}
      <div
        style={{
          backgroundColor: 'var(--tg-theme-secondary-bg-color)',
          borderRadius: '12px',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px' }}>
          <span style={{ fontSize: '14px', color: 'var(--tg-theme-hint-color)' }}>မေဂျာ</span>
          <span style={{ fontSize: '14px', fontWeight: 600 }}>{book.major}</span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
          <span style={{ fontSize: '14px', color: 'var(--tg-theme-hint-color)' }}>ပညာသင်နှစ်</span>
          <span style={{ fontSize: '14px', fontWeight: 600 }}>Year {book.year}</span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
          <span style={{ fontSize: '14px', color: 'var(--tg-theme-hint-color)' }}>Semester</span>
          <span style={{ fontSize: '14px', fontWeight: 600 }}>{formatSemesterDisplay(book.year, book.semester)}</span>
        </div>

        {/* Condition & Custom Condition Details */}
        <div
          style={{
            padding: '12px 16px',
            borderTop: '1px solid rgba(0,0,0,0.06)',
            display: 'flex',
            flexDirection: 'column',
            gap: book.condition_details ? '8px' : '0',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '14px', color: 'var(--tg-theme-hint-color)' }}>အခြေအနေ</span>
            <span style={{ fontSize: '14px', fontWeight: 600 }}>{book.condition || 'Used'}</span>
          </div>

          {book.condition_details && (
            <div
              style={{
                backgroundColor: 'rgba(0, 0, 0, 0.03)',
                borderRadius: '8px',
                padding: '10px 12px',
                marginTop: '2px',
              }}
            >
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--tg-theme-hint-color)', marginBottom: '4px' }}>
                အခြေအနေ အသေးစိတ် (Condition Details):
              </div>
              <p
                style={{
                  fontSize: '13px',
                  lineHeight: 1.5,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  color: 'var(--tg-theme-text-color)',
                }}
              >
                {book.condition_details}
              </p>
            </div>
          )}
        </div>

        {book.seller_username && (
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
            <span style={{ fontSize: '14px', color: 'var(--tg-theme-hint-color)' }}>ရောင်းသူ</span>
            <span style={{ fontSize: '14px', fontWeight: 600 }}>@{book.seller_username}</span>
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {canBuy && (
          <button
            className="btn-primary"
            onClick={() => {
              triggerHaptic('medium');
              setShowBuyConfirm(true);
            }}
          >
            🛒 ဝယ်ယူမည်
          </button>
        )}

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            className="btn-secondary"
            style={{ flex: 1, gap: '6px' }}
            onClick={() => toggleFavMutation.mutate()}
            disabled={toggleFavMutation.isPending}
          >
            <Heart size={16} fill={isFav ? '#ef4444' : 'none'} color={isFav ? '#ef4444' : 'currentColor'} />
            {isFav ? 'သိမ်းထားပြီး' : 'သိမ်းထားမည်'}
          </button>

          {!isSeller && (
            <button
              style={{
                padding: '10px 14px',
                borderRadius: '10px',
                border: '1.5px solid #ef4444',
                background: 'transparent',
                color: '#ef4444',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
              onClick={() => {
                triggerHaptic('light');
                setShowReportModal(true);
              }}
            >
              <Flag size={14} />
              Report
            </button>
          )}
        </div>
      </div>

      {/* Buy Confirmation Modal */}
      {showBuyConfirm && (
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
            <AlertTriangle size={40} color="#3b82f6" style={{ margin: '0 auto' }} />
            <h3 style={{ fontSize: '16px', fontWeight: 'bold' }}>စာအုပ်ဝယ်ယူရန် သေချာပါသလား?</h3>
            <p style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)' }}>
              ဝယ်ယူရန် Request တင်လိုက်ပါက ရောင်းသူထံသို့ အကြောင်းကြားစာ ပို့ပေးမည်ဖြစ်ပြီး၊ ရောင်းသူ၏ Telegram Contact ကို Bot Private Chat တွင် ကြည့်ရှုနိုင်ပါမည်။
            </p>
            <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
              <button
                className="btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setShowBuyConfirm(false)}
                disabled={buyMutation.isPending}
              >
                မလုပ်တော့ပါ
              </button>
              <button
                className="btn-primary"
                style={{ flex: 1 }}
                onClick={() => buyMutation.mutate()}
                disabled={buyMutation.isPending}
              >
                {buyMutation.isPending ? 'ပို့နေပါသည်...' : 'ဝယ်ယူမည်'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Report Modal */}
      {showReportModal && (
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
            zIndex: 110,
            padding: '20px',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--tg-theme-bg-color)',
              borderRadius: '16px',
              padding: '20px',
              maxWidth: '340px',
              width: '100%',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Flag size={18} color="#ef4444" />
                စာအုပ် Report တင်မည်
              </h3>
              <button
                onClick={() => setShowReportModal(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--tg-theme-hint-color)' }}
              >
                <X size={20} />
              </button>
            </div>

            {reportSuccess ? (
              <div style={{ textAlign: 'center', padding: '16px 0', color: '#15803d' }}>
                <CheckCircle size={36} style={{ margin: '0 auto 8px' }} />
                <p style={{ fontWeight: 600, fontSize: '14px' }}>{reportSuccess}</p>
              </div>
            ) : (
              <>
                <p style={{ fontSize: '12px', color: 'var(--tg-theme-hint-color)' }}>
                  မလျော်ကန်သော သို့မဟုတ် အမှားပါရှိသော Listing ကို Admin ထံ အကြောင်းကြားနိုင်ပါသည်။
                </p>

                {/* Reason select */}
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                    အကြောင်းရင်း ရွေးချယ်ပါ
                  </label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {REPORT_REASONS.map((r) => (
                      <label
                        key={r.key}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          padding: '8px 10px',
                          borderRadius: '8px',
                          backgroundColor:
                            reportReason === r.key
                              ? 'rgba(59,130,246,0.1)'
                              : 'var(--tg-theme-secondary-bg-color)',
                          cursor: 'pointer',
                          fontSize: '13px',
                        }}
                      >
                        <input
                          type="radio"
                          name="reportReason"
                          value={r.key}
                          checked={reportReason === r.key}
                          onChange={(e) => setReportReason(e.target.value)}
                        />
                        <span>{r.label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Notes input */}
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, display: 'block', marginBottom: '4px' }}>
                    အသေးစိတ် ဖြည့်စွက်ချက် (ရွေးချယ်နိုင်သည်)
                  </label>
                  <textarea
                    rows={2}
                    value={reportNotes}
                    onChange={(e) => setReportNotes(e.target.value)}
                    placeholder="နောက်ထပ် ဖော်ပြလိုသည်များ ရေးသားပါ..."
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '8px',
                      border: '1px solid rgba(0,0,0,0.1)',
                      backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                      color: 'var(--tg-theme-text-color)',
                      fontSize: '13px',
                      resize: 'none',
                      outline: 'none',
                    }}
                  />
                </div>

                <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                  <button
                    className="btn-secondary"
                    style={{ flex: 1 }}
                    onClick={() => setShowReportModal(false)}
                    disabled={reportMutation.isPending}
                  >
                    မလုပ်တော့ပါ
                  </button>
                  <button
                    className="btn-primary"
                    style={{ flex: 1, backgroundColor: '#ef4444' }}
                    onClick={() => reportMutation.mutate()}
                    disabled={reportMutation.isPending}
                  >
                    {reportMutation.isPending ? 'တင်နေပါသည်...' : 'Report တင်မည်'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
