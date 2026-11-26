// frontend/src/types/index.ts
export type MajorSlug = 'ceit' | 'ep' | 'ec' | 'arch' | 'mc' | 'mech' | 'civil' | 'archi' | 'me';

export interface MajorOption {
  slug: MajorSlug;
  name: string;
}

export const MAJORS: MajorOption[] = [
  { slug: 'ceit', name: 'CEIT' },
  { slug: 'ep', name: 'EP' },
  { slug: 'ec', name: 'EC' },
  { slug: 'arch', name: 'Architecture' },
  { slug: 'mc', name: 'MC' },
  { slug: 'mech', name: 'Mechanical' },
  { slug: 'civil', name: 'Civil' },
];

export type BookStatus = 'Available' | 'Pending' | 'Sold' | 'Cancelled' | 'Delisted' | 'Deleted';


export interface Book {
  _id: string;
  title: string;
  major: string;
  major_slug: MajorSlug;
  year: number;
  semester: number | string;
  price: number | null;
  is_negotiable: boolean;
  condition: string;
  condition_details?: string | null;
  seller_id: number;
  seller_username?: string;

  // Photo metadata returned by the API
  photo_count?: number;
  has_photos?: boolean;
  photo_file_ids?: string[];

  status: BookStatus;
  current_buyer_id?: number | null;
  admin_hidden?: boolean;
  created_at: string;
  updated_at: string;
  is_favorite?: boolean;
}


export interface UserProfile {
  user_id: number;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  language_code: string | null;
  is_admin: boolean;
  created_at: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    first_name?: string;
    last_name?: string;
    username?: string;
  };
  is_admin: boolean;
}
