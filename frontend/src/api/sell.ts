// frontend/src/api/sell.ts
import { apiClient } from './client';

export interface PublishListingPayload {
  title: string;
  major_slug: string;
  year: number;
  semester: string | number;
  price?: number | null;
  is_negotiable: boolean;
  condition: string;
  condition_details?: string | null;
  photo_file_ids: string[];
}

export interface PublishListingResult {
  success: boolean;
  message: string;
  book_id?: string;
}

export interface StagedPhotoResult {
  file_id: string;
  url: string;
}

export async function uploadBookPhoto(file: File): Promise<StagedPhotoResult> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<StagedPhotoResult>('/sell/upload-photo', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
}

export async function getSellDraft(): Promise<PublishListingPayload | null> {
  const response = await apiClient.get<PublishListingPayload | null>('/sell/draft');
  return response.data;
}

export async function saveSellDraft(payload: Partial<PublishListingPayload>): Promise<void> {
  await apiClient.post('/sell/draft', payload);
}

export async function clearSellDraft(): Promise<void> {
  await apiClient.delete('/sell/draft');
}

export async function publishListing(payload: PublishListingPayload): Promise<PublishListingResult> {
  const response = await apiClient.post<PublishListingResult>('/sell/publish', payload);
  return response.data;
}
