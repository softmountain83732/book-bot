// frontend/src/App.tsx
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './context/AuthContext';
import { AppLayout } from './layouts/AppLayout';
import { HomePage } from './pages/HomePage';
import { BrowsePage } from './pages/BrowsePage';
import { BookDetailPage } from './pages/BookDetailPage';
import { SellPage } from './pages/SellPage';
import { FavoritesPage } from './pages/FavoritesPage';
import { PurchasesPage } from './pages/PurchasesPage';
import { MyBooksPage } from './pages/MyBooksPage';
import { AdminPage } from './pages/AdminPage';
import { ProfilePage } from './pages/ProfilePage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AppLayout />}>
              <Route index element={<HomePage />} />
              <Route path="browse" element={<BrowsePage />} />
              <Route path="books/:bookId" element={<BookDetailPage />} />
              <Route path="sell" element={<SellPage />} />
              <Route path="favorites" element={<FavoritesPage />} />
              <Route path="purchases" element={<PurchasesPage />} />
              <Route path="my-books" element={<MyBooksPage />} />
              <Route path="admin" element={<AdminPage />} />
              <Route path="profile" element={<ProfilePage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
