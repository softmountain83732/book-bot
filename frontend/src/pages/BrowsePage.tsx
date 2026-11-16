// src/pages/BrowsePage.tsx
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Search, X } from 'lucide-react';
import type { MajorSlug } from '../types';
import { MAJORS } from '../types';
import { fetchBooks } from '../api/books';
import { getSemesterOptions } from '../utils/semester';
import { BookCard } from '../components/BookCard';
import { BookCardSkeleton } from '../components/BookCardSkeleton';

export const BrowsePage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [selectedYear, setSelectedYear] = useState<number | null>(
    searchParams.get('year') ? Number(searchParams.get('year')) : null,
  );
  const [selectedMajor, setSelectedMajor] = useState<MajorSlug | null>(
    (searchParams.get('major') as MajorSlug) || null,
  );
  const [selectedSemester, setSelectedSemester] = useState<string>(
    searchParams.get('semester') || 'all',
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  const sentinelRef = useRef<HTMLDivElement>(null);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 400);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Sync filter changes to URL
  useEffect(() => {
    const params: Record<string, string> = {};
    if (selectedYear) params.year = String(selectedYear);
    if (selectedMajor) params.major = selectedMajor;
    if (selectedSemester && selectedSemester !== 'all') params.semester = selectedSemester;
    setSearchParams(params, { replace: true });
  }, [selectedYear, selectedMajor, selectedSemester]);

  const { data, isLoading, isFetchingNextPage, fetchNextPage, hasNextPage, error } =
    useInfiniteQuery({
      queryKey: ['books', selectedYear, selectedMajor, selectedSemester, debouncedSearch],
      queryFn: ({ pageParam = 1 }) =>
        fetchBooks({
          year: selectedYear ?? undefined,
          major_slug: selectedMajor ?? undefined,
          semester: selectedSemester !== 'all' ? selectedSemester : undefined,
          search: debouncedSearch || undefined,
          page: pageParam as number,
          page_size: 20,
        }),
      initialPageParam: 1,
      getNextPageParam: (lastPage) => lastPage.has_next ? lastPage.page + 1 : undefined,
    });

  // Infinite scroll via IntersectionObserver
  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 },
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const allBooks = data?.pages.flatMap((p) => p.items) ?? [];
  const totalBooks = data?.pages[0]?.total ?? 0;

  const semesterOptions = selectedYear ? getSemesterOptions(selectedYear) : [];

  const handleYearSelect = (yr: number | null) => {
    setSelectedYear(yr);
    setSelectedSemester('all');
  };

  const pillStyle = (active: boolean): React.CSSProperties => ({
    padding: '7px 14px',
    borderRadius: '20px',
    border: active ? 'none' : '1px solid rgba(0,0,0,0.1)',
    backgroundColor: active ? 'var(--tg-theme-button-color)' : 'var(--tg-theme-secondary-bg-color)',
    color: active ? 'var(--tg-theme-button-text-color)' : 'var(--tg-theme-text-color)',
    fontSize: '13px',
    fontWeight: active ? 700 : 500,
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
    flexShrink: 0,
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      {/* Header */}
      <h1 style={{ fontSize: '18px', fontWeight: 'bold' }}>📚 စာအုပ်များ ရှာဖွေရန်</h1>

      {/* Search */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 12px',
          borderRadius: '12px',
          backgroundColor: 'var(--tg-theme-secondary-bg-color)',
        }}
      >
        <Search size={16} color="var(--tg-theme-hint-color)" />
        <input
          type="text"
          placeholder="စာအုပ်အမည်ဖြင့် ရှာရန်..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            flex: 1,
            border: 'none',
            background: 'transparent',
            outline: 'none',
            fontSize: '14px',
            color: 'var(--tg-theme-text-color)',
          }}
        />
        {searchQuery && (
          <X size={16} color="var(--tg-theme-hint-color)" onClick={() => setSearchQuery('')} style={{ cursor: 'pointer' }} />
        )}
      </div>

      {/* Year filter */}
      <div>
        <p style={{ fontSize: '12px', color: 'var(--tg-theme-hint-color)', marginBottom: '8px', fontWeight: 600 }}>
          ပညာသင်နှစ်
        </p>
        <div className="no-scrollbar" style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px', scrollBehavior: 'smooth' }}>
          <button style={pillStyle(selectedYear === null)} onClick={() => handleYearSelect(null)}>
            အားလုံး
          </button>
          {[1, 2, 3, 4, 5, 6].map((yr) => (
            <button key={yr} style={pillStyle(selectedYear === yr)} onClick={() => handleYearSelect(yr)}>
              Year {yr}
            </button>
          ))}
        </div>
      </div>

      {/* Major filter */}
      <div>
        <p style={{ fontSize: '12px', color: 'var(--tg-theme-hint-color)', marginBottom: '8px', fontWeight: 600 }}>
          မေဂျာ
        </p>
        <div className="no-scrollbar" style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px', scrollBehavior: 'smooth' }}>
          <button style={pillStyle(selectedMajor === null)} onClick={() => setSelectedMajor(null)}>
            အားလုံး
          </button>
          {MAJORS.map((m) => (
            <button key={m.slug} style={pillStyle(selectedMajor === m.slug)} onClick={() => setSelectedMajor(m.slug)}>
              {m.name}
            </button>
          ))}
        </div>
      </div>

      {/* Semester filter — only when year is selected */}
      {selectedYear && (
        <div>
          <p style={{ fontSize: '12px', color: 'var(--tg-theme-hint-color)', marginBottom: '8px', fontWeight: 600 }}>
            Semester
          </p>
          <div className="no-scrollbar" style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '4px', scrollBehavior: 'smooth' }}>
            <button style={pillStyle(selectedSemester === 'all')} onClick={() => setSelectedSemester('all')}>
              အားလုံး
            </button>
            {semesterOptions.map((opt) => (
              <button
                key={opt.value}
                style={pillStyle(selectedSemester === opt.value)}
                onClick={() => setSelectedSemester(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Results count */}
      {!isLoading && (
        <p style={{ fontSize: '12px', color: 'var(--tg-theme-hint-color)' }}>
          စာအုပ် {totalBooks.toLocaleString()} အုပ် တွေ့ရှိသည်
        </p>
      )}

      {/* Error state */}
      {error && (
        <div style={{ textAlign: 'center', padding: '32px 16px' }}>
          <p style={{ fontSize: '32px', marginBottom: '8px' }}>⚠️</p>
          <p style={{ color: 'var(--tg-theme-hint-color)' }}>ဒေတာ ရယူ၍ မရပါ။ ထပ်မံ ကြိုးစားပါ။</p>
        </div>
      )}

      {/* Book grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: '12px',
        }}
      >
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => <BookCardSkeleton key={i} />)
          : allBooks.map((book) => (
              <BookCard
                key={book._id}
                book={book}
                onClick={() => navigate(`/books/${book._id}`)}
              />
            ))}

        {isFetchingNextPage &&
          Array.from({ length: 2 }).map((_, i) => <BookCardSkeleton key={`next-${i}`} />)}
      </div>

      {/* Empty state */}
      {!isLoading && !error && allBooks.length === 0 && (
        <div style={{ textAlign: 'center', padding: '48px 16px' }}>
          <p style={{ fontSize: '48px', marginBottom: '12px' }}>📭</p>
          <p style={{ fontWeight: 600, marginBottom: '6px' }}>စာအုပ် မတွေ့ပါ</p>
          <p style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)' }}>
            Filter များ ပြောင်းလဲ၍ ထပ်မံ ကြိုးစားပါ
          </p>
        </div>
      )}

      {/* Infinite scroll sentinel */}
      <div ref={sentinelRef} style={{ height: '1px' }} />
    </div>
  );
};
