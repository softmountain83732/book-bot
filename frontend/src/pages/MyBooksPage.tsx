// frontend/src/pages/MyBooksPage.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Pause, Play, Trash2, AlertCircle, Edit3, Upload, X } from 'lucide-react';
import {
  fetchMyBooks,
  fetchSellerMetrics,
  executeListingAction,
  fetchMyBookDetail,
  editMyBook,
  type EditListingPayload,
} from '../api/myBooks';
import { getStatusBadgeClass, getStatusLabel, formatPrice, formatSemesterDisplay, getSemesterOptions } from '../utils/semester';
import { getPhotoUrl } from '../api/books';
import { uploadBookPhoto } from '../api/sell';
import { useTelegram } from '../hooks/useTelegram';
import { MAJORS, type Book, type MajorSlug } from '../types';

interface PhotoItem {
  file_id: string;
  previewUrl: string;
}

interface EditBookModalProps {
  bookId: string;
  onClose: () => void;
  onSuccess: () => void;
}

const EditBookModal: React.FC<EditBookModalProps> = ({ bookId, onClose, onSuccess }) => {
  const { triggerHaptic, triggerSuccess } = useTelegram();

  const [title, setTitle] = useState('');
  const [majorSlug, setMajorSlug] = useState<MajorSlug>('ceit');
  const [year, setYear] = useState<number>(1);
  const [semester, setSemester] = useState<string>('1');
  const [price, setPrice] = useState<string>('');
  const [isNegotiable, setIsNegotiable] = useState(false);
  const [condition, setCondition] = useState('Used');
  const [conditionDetails, setConditionDetails] = useState('');
  const [photos, setPhotos] = useState<PhotoItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data: book, isLoading: isBookLoading } = useQuery({
    queryKey: ['my-book-detail', bookId],
    queryFn: () => fetchMyBookDetail(bookId),
  });

  useEffect(() => {
    if (book) {
      setTitle(book.title || '');
      setMajorSlug((book.major_slug as MajorSlug) || 'ceit');
      setYear(book.year || 1);
      setSemester(String(book.semester ?? (book.year === 2 ? '3' : '1')));
      setPrice(book.price !== null && book.price !== undefined ? String(book.price) : '');
      setIsNegotiable(Boolean(book.is_negotiable));
      setCondition(book.condition || 'Used');
      setConditionDetails(book.condition_details || '');

      const fids = book.photo_file_ids || [];
      setPhotos(
        fids.map((fid, idx) => ({
          file_id: fid,
          previewUrl: getPhotoUrl(book._id, idx),
        }))
      );
    }
  }, [book]);

  const handleYearChange = (newYear: number) => {
    setYear(newYear);
    if (newYear === 2) {
      setSemester('3');
    } else {
      setSemester('1');
    }
  };

  const handleRemovePhoto = (index: number) => {
    if (photos.length <= 1) {
      alert('အနည်းဆုံး ဓာတ်ပုံ ၁ ပုံ ရှိရပါမည်');
      return;
    }
    triggerHaptic('light');
    setPhotos((prev) => prev.filter((_, i) => i !== index));
  };

  const handlePhotoSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    if (photos.length + files.length > 4) {
      alert('ဓာတ်ပုံ အများဆုံး ၄ ပုံသာ တင်နိုင်ပါသည်');
      return;
    }

    setIsUploading(true);
    triggerHaptic('medium');

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const res = await uploadBookPhoto(file);
        setPhotos((prev) => [
          ...prev,
          {
            file_id: res.file_id,
            previewUrl: URL.createObjectURL(file),
          },
        ]);
      }
      triggerSuccess();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'ဓာတ်ပုံ တင်ရာတွင် အမှားဖြစ်သွားပါသည်');
    } finally {
      setIsUploading(false);
    }
  };

  const editMutation = useMutation({
    mutationFn: (payload: EditListingPayload) => editMyBook(bookId, payload),
    onSuccess: () => {
      triggerSuccess();
      onSuccess();
    },
    onError: (err: any) => {
      triggerHaptic('heavy');
      setSaveError(err.response?.data?.detail || 'စာအုပ် ပြင်ဆင်၍ မရပါ။');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);

    const cleanTitle = title.trim();
    if (cleanTitle.length < 2 || cleanTitle.length > 120) {
      setSaveError('စာအုပ်အမည်သည် အနည်းဆုံး ၂ လုံးမှ ၁၂၀ လုံးအတွင်း ဖြစ်ရပါမည်');
      return;
    }

    if (photos.length === 0) {
      setSaveError('အနည်းဆုံး ဓာတ်ပုံ ၁ ပုံ ရှိရပါမည်');
      return;
    }

    if (!isNegotiable) {
      const p = parseFloat(price);
      if (!price || isNaN(p) || p <= 0) {
        setSaveError('ဈေးနှုန်း ထည့်သွင်းပေးပါ သို့မဟုတ် ဈေးညှိနှိုင်းဟု ရွေးချယ်ပေးပါ');
        return;
      }
      if (p > 10000000) {
        setSaveError('ဈေးနှုန်း ပမာဏများလွန်းနေပါသည်');
        return;
      }
    }

    if (conditionDetails.trim().length > 500) {
      setSaveError('စာအုပ်အခြေအနေ အသေးစိတ်သည် စာလုံးရေ ၅၀၀ ထက် မကျော်ရပါ');
      return;
    }

    const payload: EditListingPayload = {
      title: cleanTitle,
      major_slug: majorSlug,
      year,
      semester,
      price: !isNegotiable && price ? parseFloat(price) : null,
      is_negotiable: isNegotiable,
      condition: condition || 'Used',
      condition_details: conditionDetails.trim() || null,
      photo_file_ids: photos.map((p) => p.file_id),
    };

    editMutation.mutate(payload);
  };

  return (
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
        padding: '16px',
      }}
    >
      <div
        style={{
          backgroundColor: 'var(--tg-theme-bg-color)',
          borderRadius: '16px',
          padding: '20px',
          maxWidth: '420px',
          width: '100%',
          maxHeight: '90vh',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: '17px', fontWeight: 'bold', margin: 0 }}>
            စာအုပ်အချက်အလက် ပြင်ဆင်ရန်
          </h2>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--tg-theme-hint-color)',
              padding: '4px',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {isBookLoading ? (
          <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--tg-theme-hint-color)' }}>
            အချက်အလက်များ ရယူနေဆဲ...
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {saveError && (
              <div
                style={{
                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                  color: '#ef4444',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  fontSize: '13px',
                }}
              >
                {saveError}
              </div>
            )}

            {/* Title */}
            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                စာအုပ်အမည် *
              </label>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="ဥပမာ - Engineering Mathematics 1"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '10px',
                  border: '1px solid rgba(0,0,0,0.1)',
                  backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                  color: 'var(--tg-theme-text-color)',
                  fontSize: '14px',
                }}
              />
            </div>

            {/* Major */}
            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                မေဂျာ *
              </label>
              <select
                value={majorSlug}
                onChange={(e) => setMajorSlug(e.target.value as MajorSlug)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '10px',
                  border: '1px solid rgba(0,0,0,0.1)',
                  backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                  color: 'var(--tg-theme-text-color)',
                  fontSize: '14px',
                }}
              >
                {MAJORS.map((m) => (
                  <option key={m.slug} value={m.slug}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Year & Semester */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label style={{ fontSize: '13px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                  ပညာသင်နှစ် *
                </label>
                <select
                  value={year}
                  onChange={(e) => handleYearChange(parseInt(e.target.value, 10))}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: '10px',
                    border: '1px solid rgba(0,0,0,0.1)',
                    backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                    color: 'var(--tg-theme-text-color)',
                    fontSize: '14px',
                  }}
                >
                  {[1, 2, 3, 4, 5, 6].map((yr) => (
                    <option key={yr} value={yr}>
                      Year {yr}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '13px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                  Semester *
                </label>
                <select
                  value={semester}
                  onChange={(e) => setSemester(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: '10px',
                    border: '1px solid rgba(0,0,0,0.1)',
                    backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                    color: 'var(--tg-theme-text-color)',
                    fontSize: '14px',
                  }}
                >
                  {getSemesterOptions(year).map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Condition & Details */}
            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                စာအုပ်အခြေအနေ (Condition)
              </label>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                <span
                  style={{
                    padding: '6px 14px',
                    borderRadius: '20px',
                    backgroundColor: 'var(--tg-theme-button-color)',
                    color: 'var(--tg-theme-button-text-color)',
                    fontSize: '12px',
                    fontWeight: 600,
                  }}
                >
                  ✓ Used (အသုံးပြုထားသည်)
                </span>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <label style={{ fontSize: '13px', fontWeight: 600 }}>
                    Book Condition Details
                  </label>
                  <span style={{ fontSize: '11px', color: conditionDetails.length > 500 ? '#ef4444' : 'var(--tg-theme-hint-color)' }}>
                    {conditionDetails.length} / 500
                  </span>
                </div>
                <textarea
                  rows={3}
                  maxLength={500}
                  value={conditionDetails}
                  onChange={(e) => setConditionDetails(e.target.value)}
                  placeholder="Describe the actual condition of your book..."
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: '10px',
                    border: '1px solid rgba(0,0,0,0.1)',
                    backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                    color: 'var(--tg-theme-text-color)',
                    fontSize: '13px',
                    resize: 'vertical',
                    outline: 'none',
                    fontFamily: 'inherit',
                  }}
                />
              </div>
            </div>

            {/* Price & Negotiable */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '13px', fontWeight: 600 }}>ဈေးနှုန်း (MMK)</label>
                <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={isNegotiable}
                    onChange={(e) => setIsNegotiable(e.target.checked)}
                  />
                  ဈေးညှိနှိုင်း
                </label>
              </div>
              <input
                type="number"
                disabled={isNegotiable}
                value={isNegotiable ? '' : price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder={isNegotiable ? 'ဈေးညှိနှိုင်း' : 'ဥပမာ - 15000'}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '10px',
                  border: '1px solid rgba(0,0,0,0.1)',
                  backgroundColor: isNegotiable ? 'rgba(0,0,0,0.04)' : 'var(--tg-theme-secondary-bg-color)',
                  color: 'var(--tg-theme-text-color)',
                  fontSize: '14px',
                }}
              />
            </div>

            {/* Photos (up to 4) */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <label style={{ fontSize: '13px', fontWeight: 600 }}>
                  စာအုပ်ဓာတ်ပုံများ (အများဆုံး ၄ ပုံ) *
                </label>
                <span style={{ fontSize: '11px', color: 'var(--tg-theme-hint-color)' }}>
                  {photos.length} / 4
                </span>
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {photos.map((item, i) => (
                  <div
                    key={i}
                    style={{
                      width: '74px',
                      height: '74px',
                      borderRadius: '10px',
                      overflow: 'hidden',
                      position: 'relative',
                      border: '1px solid rgba(0,0,0,0.1)',
                    }}
                  >
                    <img src={item.previewUrl} alt="preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    <button
                      type="button"
                      onClick={() => handleRemovePhoto(i)}
                      style={{
                        position: 'absolute',
                        top: 2,
                        right: 2,
                        background: 'rgba(0,0,0,0.6)',
                        border: 'none',
                        borderRadius: '50%',
                        width: '20px',
                        height: '20px',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer',
                      }}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}

                {photos.length < 4 && (
                  <label
                    style={{
                      width: '74px',
                      height: '74px',
                      borderRadius: '10px',
                      border: '2px dashed var(--tg-theme-hint-color)',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      backgroundColor: 'var(--tg-theme-secondary-bg-color)',
                    }}
                  >
                    <Upload size={18} color="var(--tg-theme-hint-color)" />
                    <span style={{ fontSize: '10px', color: 'var(--tg-theme-hint-color)', marginTop: '2px' }}>
                      {isUploading ? 'တင်နေဆဲ...' : 'ပုံထည့်ရန်'}
                    </span>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      disabled={isUploading}
                      onChange={handlePhotoSelect}
                      style={{ display: 'none' }}
                    />
                  </label>
                )}
              </div>
            </div>

            {/* Buttons */}
            <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
              <button
                type="button"
                className="btn-secondary"
                style={{ flex: 1 }}
                onClick={onClose}
                disabled={editMutation.isPending || isUploading}
              >
                မလုပ်တော့ပါ (Cancel)
              </button>
              <button
                type="submit"
                className="btn-primary"
                style={{ flex: 1.2 }}
                disabled={editMutation.isPending || isUploading}
              >
                {editMutation.isPending ? 'သိမ်းဆည်းနေပါသည်...' : 'သိမ်းဆည်းမည် (Save)'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export const MyBooksPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { triggerHaptic, triggerSuccess } = useTelegram();

  const [activeTab, setActiveTab] = useState<string>('all');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [editingBookId, setEditingBookId] = useState<string | null>(null);

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
              {(book.status === 'Available' || book.status === 'Delisted') && (
                <button
                  type="button"
                  onClick={() => {
                    triggerHaptic('light');
                    setEditingBookId(book._id);
                  }}
                  style={{
                    backgroundColor: 'transparent',
                    border: '1px solid var(--tg-theme-button-color, #2563eb)',
                    color: 'var(--tg-theme-button-color, #2563eb)',
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
                  <Edit3 size={12} />
                  ပြင်ဆင်မည် (Edit)
                </button>
              )}

              {book.status === 'Available' && (
                <button
                  type="button"
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
                  type="button"
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
                  type="button"
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

      {/* Edit Book Modal */}
      {editingBookId && (
        <EditBookModal
          bookId={editingBookId}
          onClose={() => setEditingBookId(null)}
          onSuccess={() => {
            setEditingBookId(null);
            queryClient.invalidateQueries({ queryKey: ['my-books'] });
            queryClient.invalidateQueries({ queryKey: ['seller-metrics'] });
          }}
        />
      )}

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
                type="button"
                className="btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setConfirmDeleteId(null)}
              >
                မဖျက်တော့ပါ
              </button>
              <button
                type="button"
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
