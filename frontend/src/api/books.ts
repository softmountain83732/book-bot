// frontend/src/api/books.ts
import { apiClient } from './client';
import type { Book } from '../types';

export interface BooksPage {
  items: Book[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface BooksFilter {
  year?: number;
  major_slug?: string;
  semester?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export async function fetchBooks(params: BooksFilter): Promise<BooksPage> {
  const response = await apiClient.get<BooksPage>('/books', { params });
  return response.data;
}

export async function fetchBookById(id: string): Promise<Book> {
  const response = await apiClient.get<Book>(`/books/${id}`);
  return response.data;
}

/**
 * Build reliable, absolute/relative URL for streaming book photos via the media proxy.
 * Safely handles trailing slashes and ensures /api/v1 path is present.
 */
export function getPhotoUrl(bookId: string, photoIndex: number = 0): string {
  let base = (import.meta.env.VITE_API_URL || '/api/v1').trim();
  base = base.replace(/\/+$/, '');
  if (!base.endsWith('/api/v1')) {
    base = `${base}/api/v1`;
  }
  return `${base}/media/books/${encodeURIComponent(bookId)}/photos/${photoIndex}`;
}
