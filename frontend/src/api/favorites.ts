// frontend/src/api/favorites.ts
import { apiClient } from './client';
import type { Book } from '../types';

export interface FavoritesPageResponse {
  items: Book[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface FavoriteToggleResponse {
  book_id: string;
  is_favorite: boolean;
  message: string;
}

export async function fetchFavorites(page = 1, page_size = 20): Promise<FavoritesPageResponse> {
  const response = await apiClient.get<FavoritesPageResponse>('/favorites', {
    params: { page, page_size },
  });
  return response.data;
}

export async function addFavorite(bookId: string): Promise<FavoriteToggleResponse> {
  const response = await apiClient.post<FavoriteToggleResponse>(`/favorites/${bookId}`);
  return response.data;
}

export async function removeFavorite(bookId: string): Promise<FavoriteToggleResponse> {
  const response = await apiClient.delete<FavoriteToggleResponse>(`/favorites/${bookId}`);
  return response.data;
}
