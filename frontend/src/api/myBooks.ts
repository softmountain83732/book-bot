// frontend/src/api/myBooks.ts
import { apiClient } from './client';
import type { Book } from '../types';

export interface MyBooksPageResponse {
  items: Book[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface SellerMetricsResponse {
  active_count: number;
  pending_count: number;
  sold_count: number;
  delisted_count: number;
  total_count: number;
}

export interface EditListingPayload {
  title?: string;
  major_slug?: string;
  year?: number;
  semester?: string | number;
  price?: number | null;
  is_negotiable?: boolean;
  condition?: string;
  condition_details?: string | null;
  photo_file_ids?: string[];
}

export async function fetchSellerMetrics(): Promise<SellerMetricsResponse> {
  const response = await apiClient.get<SellerMetricsResponse>('/my-books/metrics');
  return response.data;
}

export async function fetchMyBooks(status?: string, page = 1, page_size = 20): Promise<MyBooksPageResponse> {
  const response = await apiClient.get<MyBooksPageResponse>('/my-books', {
    params: { status: status !== 'all' ? status : undefined, page, page_size },
  });
  return response.data;
}

export async function fetchMyBookDetail(bookId: string): Promise<Book> {
  const response = await apiClient.get<Book>(`/my-books/${bookId}`);
  return response.data;
}

export async function editMyBook(bookId: string, payload: EditListingPayload): Promise<{ message: string }> {
  const response = await apiClient.put<{ message: string }>(`/my-books/${bookId}`, payload);
  return response.data;
}

export async function executeListingAction(bookId: string, action: 'delist' | 'relist' | 'delete'): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>(`/my-books/${bookId}/action`, { action });
  return response.data;
}
