// frontend/src/api/reports.ts
import { apiClient } from './client';

export interface SubmitReportPayload {
  book_id: string;
  reason: 'fake' | 'spam' | 'offensive' | 'wrong_major' | 'other' | string;
  notes?: string;
}

export interface SubmitReportResponse {
  success: boolean;
  message: string;
}

export const submitBookReport = async (payload: SubmitReportPayload): Promise<SubmitReportResponse> => {
  const { data } = await apiClient.post<SubmitReportResponse>('/reports', payload);
  return data;
};
