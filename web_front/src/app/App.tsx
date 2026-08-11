import { Routes, Route, Navigate } from 'react-router-dom';
import { useAppStore } from '@/store';

import Navbar from '@/components/layout/Navbar';
import DashboardLayout from '@/components/layout/DashboardLayout';

import LandingPage from '@/pages/LandingPage';
import LoginPage from '@/pages/auth/LoginPage';

import DashboardHome from '@/pages/dashboard/HomePage';
import InterviewPage from '@/pages/dashboard/interview/InterviewPage';
import InterviewSession from '@/pages/dashboard/interview/InterviewSessionPage';
import HistoryPage from '@/pages/dashboard/interview/HistoryPage';
import ReportPage from '@/pages/dashboard/interview/ReportPage';
import FeedPage from '@/pages/dashboard/community/FeedPage';
import CommunityPage from '@/pages/dashboard/community/CommunityPage';
import PostDetailPage from '@/pages/dashboard/community/PostDetailPage';
import FavoritesPage from '@/pages/dashboard/community/FavoritesPage';
import MessagesPage from '@/pages/dashboard/messages/MessagesPage';
import MessageDetailPage from '@/pages/dashboard/messages/MessageDetailPage';
import ChatPage from '@/pages/dashboard/messages/ChatPage';
import UserPage from '@/pages/dashboard/social/UserPage';
import ProfilePage from '@/pages/dashboard/social/ProfilePage';
import FollowingPage from '@/pages/dashboard/social/FollowingPage';
import FollowersPage from '@/pages/dashboard/social/FollowersPage';
import SettingsPage from '@/pages/dashboard/settings/SettingsPage';
import HelpPage from '@/pages/dashboard/settings/HelpPage';
import NotFoundPage from '@/pages/NotFoundPage';
import PrivacyPage from '@/pages/PrivacyPage';

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
      <Route path="/register" element={<Navigate to="/login" replace />} />

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
        <Route path="messages/chat/:userId" element={<ChatPage />} />
        <Route path="user/:id" element={<UserPage />} />
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