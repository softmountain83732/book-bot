// frontend/src/api/admin.ts
import { apiClient } from './client';
import type { Book } from '../types';

export interface AdminStats {
  total_users: number;
  total_books: number;
  available_books: number;
  pending_books: number;
  sold_books: number;
  cancelled_books: number;
  delisted_books: number;
  pending_requests: number;
  open_reports: number;
}

export interface ReportItem {
  id: string;
  book_id: string;
  book_title: string;
  reporter_id: number;
  seller_id: number;
  reason: string;
  reason_label: string;
  status: string;
  resolved_by?: number | null;
  created_at: string;
  updated_at?: string | null;
}

export interface ReportsPageResponse {
  items: ReportItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export async function fetchAdminStats(): Promise<AdminStats> {
  const response = await apiClient.get<AdminStats>('/admin/stats');
  return response.data;
}

export async function fetchAdminBooks(status?: string, search?: string, page = 1): Promise<{ items: Book[]; total: number }> {
  const response = await apiClient.get<{ items: Book[]; total: number }>('/admin/books', {
    params: { status: status !== 'all' ? status : undefined, search, page },
  });
  return response.data;
}

export async function moderateBook(bookId: string, action: 'hide' | 'unhide', reason?: string): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>(`/admin/books/${bookId}/action`, { action, reason });
  return response.data;
}

export async function fetchReports(status = 'Open', page = 1): Promise<ReportsPageResponse> {
  const response = await apiClient.get<ReportsPageResponse>('/admin/reports', {
    params: { status, page },
  });
  return response.data;
}

export async function resolveReport(reportId: string, resolution: 'Resolved' | 'Dismissed'): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>(`/admin/reports/${reportId}/resolve`, { resolution });
  return response.data;
}
