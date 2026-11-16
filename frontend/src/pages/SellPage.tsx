// frontend/src/pages/SellPage.tsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Upload, X, BookPlus } from 'lucide-react';
import { MAJORS } from '../types';
import { getSemesterOptions } from '../utils/semester';
import { uploadBookPhoto, getSellDraft, publishListing, type PublishListingPayload } from '../api/sell';
import { useTelegram } from '../hooks/useTelegram';

export const SellPage: React.FC = () => {
  const navigate = useNavigate();
  const { triggerHaptic, triggerSuccess } = useTelegram();

  const [title, setTitle] = useState('');
  const [majorSlug, setMajorSlug] = useState('ceit');
  const [year, setYear] = useState<number>(1);
  const [semester, setSemester] = useState<string>('1');
  const [price, setPrice] = useState<string>('');
  const [isNegotiable, setIsNegotiable] = useState(false);
  const [condition, setCondition] = useState('Used');
  const [conditionDetails, setConditionDetails] = useState('');
  const [photoIds, setPhotoIds] = useState<string[]>([]);
  const [photoPreviews, setPhotoPreviews] = useState<string[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  // Restore draft on load
  const { data: draft } = useQuery({
    queryKey: ['sell-draft'],
    queryFn: getSellDraft,
  });

  useEffect(() => {
    if (draft) {
      if (draft.title) setTitle(draft.title);
      if (draft.major_slug) setMajorSlug(draft.major_slug);
      if (draft.year) setYear(draft.year);
      if (draft.semester) setSemester(String(draft.semester));
      if (draft.price) setPrice(String(draft.price));
      if (draft.is_negotiable !== undefined) setIsNegotiable(draft.is_negotiable);
      if (draft.condition) setCondition(draft.condition);
      if (draft.condition_details) setConditionDetails(draft.condition_details);
      if (draft.photo_file_ids) setPhotoIds(draft.photo_file_ids);
    }
  }, [draft]);

  // Dynamic semester options when Year updates
  const semesterOpts = getSemesterOptions(year);

  const handleYearChange = (newYear: number) => {
    setYear(newYear);
    // Automatically select default valid semester for the chosen year
    if (newYear === 2) {
      setSemester('3');
    } else {
      setSemester('1');
    }
  };

  const handlePhotoSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    if (photoIds.length + files.length > 4) {
      alert('ဓာတ်ပုံ အများဆုံး ၄ ပုံသာ တင်နိုင်ပါသည်');
      return;
    }

    setIsUploading(true);
    triggerHaptic('medium');

    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const res = await uploadBookPhoto(file);
        setPhotoIds((prev) => [...prev, res.file_id]);
        setPhotoPreviews((prev) => [...prev, URL.createObjectURL(file)]);
      }
      triggerSuccess();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'ဓာတ်ပုံ တင်ရာတွင် အမှားဖြစ်သွားပါသည်');
    } finally {
      setIsUploading(false);
    }
  };

  const removePhoto = (index: number) => {
    triggerHaptic('light');
    setPhotoIds((prev) => prev.filter((_, i) => i !== index));
    setPhotoPreviews((prev) => prev.filter((_, i) => i !== index));
  };

  const publishMutation = useMutation({
    mutationFn: (payload: PublishListingPayload) => publishListing(payload),
    onSuccess: (res) => {
      triggerSuccess();
      setShowConfirmModal(false);
      navigate(`/books/${res.book_id}`);
    },
    onError: (err: any) => {
      triggerHaptic('heavy');
      alert(err.response?.data?.detail || 'စာအုပ်တင်၍ မရပါ။');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || photoIds.length === 0) {
      alert('စာအုပ်အမည်နှင့် အနည်းဆုံး ဓာတ်ပုံ ၁ ပုံ ထည့်သွင်းပေးပါ');
      return;
    }
    triggerHaptic('medium');
    setShowConfirmModal(true);
  };

  const confirmPublish = () => {
    const payload: PublishListingPayload = {
      title: title.trim(),
      major_slug: majorSlug,
      year,
      semester,
      price: !isNegotiable && price ? parseFloat(price) : null,
      is_negotiable: isNegotiable,
      condition: condition || 'Used',
      condition_details: conditionDetails.trim() || null,
      photo_file_ids: photoIds,
    };
    publishMutation.mutate(payload);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', paddingBottom: '32px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <BookPlus size={20} color="var(--tg-theme-button-color)" />
        <h1 style={{ fontSize: '18px', fontWeight: 'bold' }}>စာအုပ် ရောင်းချရန်</h1>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
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
            onChange={(e) => setMajorSlug(e.target.value)}
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

        {/* Year and Dynamic Semester */}
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
              {semesterOpts.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Condition & Details */}
        <div>
          <label style={{ fontSize: '13px', fontWeight: 600, display: 'block', marginBottom: '8px' }}>
            စာအုပ်အခြေအနေ (Condition)
          </label>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
            <button
              type="button"
              style={{
                padding: '8px 16px',
                borderRadius: '20px',
                border: 'none',
                backgroundColor: 'var(--tg-theme-button-color)',
                color: 'var(--tg-theme-button-text-color)',
                fontSize: '13px',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                cursor: 'default',
              }}
            >
              <span>✓ Used</span>
              <span style={{ fontSize: '11px', opacity: 0.85 }}>(အသုံးပြုထားသည်)</span>
            </button>
          </div>

          {/* Condition Details */}
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
              placeholder="Describe the actual condition of your book. For example: Slightly damaged cover, some highlighted pages, clean inside pages..."
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
          <label style={{ fontSize: '13px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
            စာအုပ်ဓာတ်ပုံများ (အများဆုံး ၄ ပုံ) *
          </label>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {photoPreviews.map((preview, i) => (
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
                <img src={preview} alt="preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                <button
                  type="button"
                  onClick={() => removePhoto(i)}
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

            {photoIds.length < 4 && (
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

        <button
          type="submit"
          className="btn-primary"
          style={{ marginTop: '12px' }}
          disabled={publishMutation.isPending || isUploading}
        >
          တင်သွင်းမည်
        </button>
      </form>

      {/* Confirmation Modal */}
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
            }}
          >
            <h3 style={{ fontSize: '16px', fontWeight: 'bold', textAlign: 'center' }}>စာအုပ်တင်ရန် သေချာပါသလား?</h3>
            <div style={{ fontSize: '13px', lineHeight: 1.6, color: 'var(--tg-theme-hint-color)' }}>
              <div><b>အမည်:</b> {title}</div>
              <div><b>မေဂျာ:</b> {majorSlug.toUpperCase()} (Year {year})</div>
              <div><b>အခြေအနေ:</b> {condition || 'Used'} {conditionDetails.trim() ? `(${conditionDetails.trim()})` : ''}</div>
              <div><b>ဈေးနှုန်း:</b> {isNegotiable ? 'ညှိနှိုင်း' : `${price} MMK`}</div>
              <div><b>ပုံအရေအတွက်:</b> {photoIds.length} ပုံ</div>
            </div>
            <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
              <button
                className="btn-secondary"
                style={{ flex: 1 }}
                onClick={() => setShowConfirmModal(false)}
                disabled={publishMutation.isPending}
              >
                ပြင်ဆင်မည်
              </button>
              <button
                className="btn-primary"
                style={{ flex: 1 }}
                onClick={confirmPublish}
                disabled={publishMutation.isPending}
              >
                {publishMutation.isPending ? 'တင်နေပါသည်...' : 'တင်မည်'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
