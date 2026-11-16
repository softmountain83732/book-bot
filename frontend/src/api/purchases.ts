// frontend/src/api/purchases.ts
import { apiClient } from './client';

export interface BuyResponse {
  success: boolean;
  message: string;
  request_id?: string;
}

export interface CancelPurchaseResponse {
  success: boolean;
  message: string;
}

export interface SellerContactResponse {
  book_id: string;
  book_title: string;
  price?: number | null;
  is_negotiable: boolean;
  seller_id: number;
  seller_username?: string | null;
  telegram_link?: string | null;
  has_username: boolean;
}

export interface PurchaseHistoryItem {
  id: string;
  book_id: string;
  book_title: string;
  seller_id: number;
  seller_username?: string;
  price?: number;
  is_negotiable: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PurchaseHistoryPage {
  items: PurchaseHistoryItem[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export async function requestBuyBook(bookId: string): Promise<BuyResponse> {
  const response = await apiClient.post<BuyResponse>('/purchases/buy', {
    book_id: bookId,
  });
  return response.data;
}

export async function fetchSellerContact(bookId: string): Promise<SellerContactResponse> {
  const response = await apiClient.get<SellerContactResponse>(`/purchases/seller-contact/${bookId}`);
  return response.data;
}

export async function cancelPurchaseRequest(requestId: string): Promise<CancelPurchaseResponse> {
  const response = await apiClient.post<CancelPurchaseResponse>('/purchases/cancel', {
    request_id: requestId,
  });
  return response.data;
}

export async function fetchPurchaseHistory(page = 1, page_size = 20): Promise<PurchaseHistoryPage> {
  const response = await apiClient.get<PurchaseHistoryPage>('/purchases/history', {
    params: { page, page_size },
  });
  return response.data;
}
