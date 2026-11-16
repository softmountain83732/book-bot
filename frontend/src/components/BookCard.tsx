// frontend/src/components/BookCard.tsx
import React, { useState } from 'react';
import { Heart } from 'lucide-react';
import type { Book } from '../types';
import { getPhotoUrl } from '../api/books';
import { formatSemesterDisplay, formatPrice, getStatusBadgeClass, getStatusLabel } from '../utils/semester';
import { useTelegram } from '../hooks/useTelegram';

interface BookCardProps {
  book: Book;
  onClick?: () => void;
  onFavorite?: (id: string, isFav: boolean) => void;
  showFavoriteBtn?: boolean;
}

export const BookCard: React.FC<BookCardProps> = ({
  book,
  onClick,
  onFavorite,
  showFavoriteBtn = true,
}) => {
  const { triggerHaptic } = useTelegram();
  const [imgError, setImgError] = useState(false);
  const [isFav, setIsFav] = useState(book.is_favorite ?? false);

  // Check photo availability using both has_photos and photo_count metadata
  const hasPhotos = Boolean(
    book.has_photos ||
    (typeof book.photo_count === 'number' && book.photo_count > 0) ||
    (book.photo_file_ids && book.photo_file_ids.length > 0)
  );

  const handleClick = () => {
    triggerHaptic('light');
    onClick?.();
  };

  const handleFavorite = (e: React.MouseEvent) => {
    e.stopPropagation();
    triggerHaptic('light');
    const next = !isFav;
    setIsFav(next);
    onFavorite?.(book._id, next);
  };

  return (
    <div
      className="book-card"
      onClick={handleClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      {/* Photo Container */}
      <div
        style={{
          width: '100%',
          aspectRatio: '4/3',
          backgroundColor: 'var(--tg-theme-secondary-bg-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {hasPhotos && !imgError ? (
          <img
            src={getPhotoUrl(book._id, 0)}
            alt={book.title}
            onError={() => setImgError(true)}
            loading="lazy"
            decoding="async"
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
            }}
          />
        ) : (
          <span style={{ fontSize: '40px' }} role="img" aria-label="Book fallback">📚</span>
        )}

        {/* Favorite Button */}
        {showFavoriteBtn && (
          <button
            onClick={handleFavorite}
            aria-label="Favorite"
            style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              background: 'rgba(0,0,0,0.4)',
              border: 'none',
              borderRadius: '50%',
              width: '32px',
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              backdropFilter: 'blur(4px)',
            }}
          >
            <Heart
              size={16}
              fill={isFav ? '#ef4444' : 'none'}
              color={isFav ? '#ef4444' : '#fff'}
            />
          </button>
        )}

        {/* Status badge overlay */}
        {book.status !== 'Available' && (
          <div
            style={{
              position: 'absolute',
              bottom: '6px',
              left: '6px',
            }}
          >
            <span className={getStatusBadgeClass(book.status)}>
              {getStatusLabel(book.status)}
            </span>
          </div>
        )}
      </div>

      {/* Info */}
      <div style={{ padding: '10px 10px 12px' }}>
        {/* Title */}
        <p
          style={{
            fontWeight: 600,
            fontSize: '13px',
            lineHeight: '1.4',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            marginBottom: '6px',
          }}
        >
          {book.title}
        </p>

        {/* Price */}
        <p
          style={{
            fontWeight: 700,
            fontSize: '14px',
            color: 'var(--tg-theme-button-color)',
            marginBottom: '6px',
          }}
        >
          {formatPrice(book.price, book.is_negotiable)}
        </p>

        {/* Meta badges */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
          <span
            style={{
              fontSize: '10px',
              padding: '2px 6px',
              borderRadius: '4px',
              backgroundColor: 'rgba(59,130,246,0.12)',
              color: 'var(--tg-theme-link-color)',
              fontWeight: 600,
            }}
          >
            {book.major}
          </span>
          <span
            style={{
              fontSize: '10px',
              padding: '2px 6px',
              borderRadius: '4px',
              backgroundColor: 'rgba(0,0,0,0.06)',
              color: 'var(--tg-theme-hint-color)',
              fontWeight: 500,
            }}
          >
            Year {book.year} · {formatSemesterDisplay(book.year, book.semester)}
          </span>
        </div>
      </div>
    </div>
  );
};
