// src/components/BookCardSkeleton.tsx
import React from 'react';

const SkeletonBox: React.FC<{ width?: string; height?: string; borderRadius?: string }> = ({
  width = '100%',
  height = '14px',
  borderRadius = '6px',
}) => (
  <div
    style={{
      width,
      height,
      borderRadius,
      backgroundColor: 'var(--tg-theme-secondary-bg-color)',
      animation: 'skeleton-pulse 1.4s ease-in-out infinite',
    }}
  />
);

export const BookCardSkeleton: React.FC = () => (
  <div className="book-card">
    <style>{`
      @keyframes skeleton-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
      }
    `}</style>

    {/* Photo placeholder */}
    <SkeletonBox height="150px" borderRadius="0" />

    {/* Info area */}
    <div style={{ padding: '10px 10px 12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <SkeletonBox height="13px" width="90%" />
      <SkeletonBox height="13px" width="70%" />
      <SkeletonBox height="16px" width="55%" />
      <div style={{ display: 'flex', gap: '6px' }}>
        <SkeletonBox height="20px" width="45px" borderRadius="4px" />
        <SkeletonBox height="20px" width="70px" borderRadius="4px" />
      </div>
    </div>
  </div>
);
