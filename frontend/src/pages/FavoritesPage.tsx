// frontend/src/pages/FavoritesPage.tsx
import React, { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Heart } from 'lucide-react';
import { fetchFavorites, removeFavorite } from '../api/favorites';
import { BookCard } from '../components/BookCard';
import { BookCardSkeleton } from '../components/BookCardSkeleton';
import { useTelegram } from '../hooks/useTelegram';

export const FavoritesPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { triggerHaptic } = useTelegram();
  const sentinelRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, isFetchingNextPage, fetchNextPage, hasNextPage, error } =
    useInfiniteQuery({
      queryKey: ['favorites'],
      queryFn: ({ pageParam = 1 }) => fetchFavorites(pageParam as number, 20),
      initialPageParam: 1,
      getNextPageParam: (lastPage) => (lastPage.has_next ? lastPage.page + 1 : undefined),
    });

  const removeFavMutation = useMutation({
    mutationFn: (bookId: string) => removeFavorite(bookId),
    onSuccess: () => {
      triggerHaptic('medium');
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
    },
  });

  useEffect(() => {
    if (!sentinelRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const allBooks = data?.pages.flatMap((p) => p.items) ?? [];
  const total = data?.pages[0]?.total ?? 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Heart size={20} color="#ef4444" fill="#ef4444" />
        <h1 style={{ fontSize: '18px', fontWeight: 'bold' }}>သိမ်းထားသော စာအုပ်များ</h1>
      </div>

      {!isLoading && (
        <p style={{ fontSize: '12px', color: 'var(--tg-theme-hint-color)' }}>
          စုစုပေါင်း {total.toLocaleString()} အုပ်
        </p>
      )}

      {error && (
        <div style={{ textAlign: 'center', padding: '32px 16px' }}>
          <p style={{ fontSize: '32px', marginBottom: '8px' }}>⚠️</p>
          <p style={{ color: 'var(--tg-theme-hint-color)' }}>စာရင်းရယူ၍ မရပါ။</p>
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: '12px',
        }}
      >
        {isLoading
          ? Array.from({ length: 4 }).map((_, i) => <BookCardSkeleton key={i} />)
          : allBooks.map((book) => (
              <BookCard
                key={book._id}
                book={book}
                onClick={() => navigate(`/books/${book._id}`)}
                onFavorite={(id, isFav) => {
                  if (!isFav) {
                    removeFavMutation.mutate(id);
                  }
                }}
              />
            ))}
        {isFetchingNextPage &&
          Array.from({ length: 2 }).map((_, i) => <BookCardSkeleton key={`next-${i}`} />)}
      </div>

      {!isLoading && !error && allBooks.length === 0 && (
        <div style={{ textAlign: 'center', padding: '48px 16px' }}>
          <p style={{ fontSize: '48px', marginBottom: '12px' }}>❤️</p>
          <p style={{ fontWeight: 600, marginBottom: '6px' }}>သိမ်းထားသော စာအုပ်မရှိသေးပါ</p>
          <p style={{ fontSize: '13px', color: 'var(--tg-theme-hint-color)', marginBottom: '16px' }}>
            ကြိုက်နှစ်သက်သော စာအုပ်များကို အလွယ်တကူ သိမ်းဆည်းနိုင်ပါသည်။
          </p>
          <button className="btn-primary" onClick={() => navigate('/browse')}>
            စာအုပ်များ ကြည့်ရှုမည်
          </button>
        </div>
      )}

      <div ref={sentinelRef} style={{ height: '1px' }} />
    </div>
  );
};
