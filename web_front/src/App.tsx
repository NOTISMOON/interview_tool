import { Routes, Route, Navigate } from 'react-router-dom';
import { useAppStore } from '@/store';

import Navbar from '@/components/layout/Navbar';
import DashboardLayout from '@/components/layout/DashboardLayout';

import LandingPage from '@/pages/Landing';
import LoginPage from '@/pages/Login';
import RegisterPage from '@/pages/Register';

import DashboardHome from '@/pages/Dashboard/Home';
import InterviewPage from '@/pages/Dashboard/Interview';
import InterviewSession from '@/pages/Dashboard/InterviewSession';
import HistoryPage from '@/pages/Dashboard/History';
import ReportPage from '@/pages/Dashboard/Report';
import FeedPage from '@/pages/Dashboard/Feed';
import CommunityPage from '@/pages/Dashboard/Community';
import MessagesPage from '@/pages/Dashboard/Messages';
import MessageDetailPage from '@/pages/Dashboard/MessageDetail';
import ProfilePage from '@/pages/Dashboard/Profile';
import PostDetailPage from '@/pages/Dashboard/PostDetail';
import FollowingPage from '@/pages/Dashboard/Following';
import FollowersPage from '@/pages/Dashboard/Followers';
import FavoritesPage from '@/pages/Dashboard/Favorites';
import SettingsPage from '@/pages/Dashboard/Settings';
import HelpPage from '@/pages/Dashboard/Help';
import NotFoundPage from '@/pages/NotFound';
import PrivacyPage from '@/pages/Privacy';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const PublicLayout = ({ children }: { children: React.ReactNode }) => (
  <>
    <Navbar />
    {children}
  </>
);

const App = () => {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <PublicLayout>
            <LandingPage />
          </PublicLayout>
        }
      />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardHome />} />
        <Route path="interview" element={<InterviewPage />} />
        <Route path="interview/session/:id" element={<InterviewSession />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="report/:id" element={<ReportPage />} />
        <Route path="feed" element={<FeedPage />} />
        <Route path="community" element={<CommunityPage />} />
        <Route path="messages" element={<MessagesPage />} />
        <Route path="messages/:id" element={<MessageDetailPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="community/post/:id" element={<PostDetailPage />} />
        <Route path="following" element={<FollowingPage />} />
        <Route path="followers" element={<FollowersPage />} />
        <Route path="favorites" element={<FavoritesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="help" element={<HelpPage />} />
      </Route>

      <Route path="/privacy" element={<PrivacyPage />} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
};

export default App;