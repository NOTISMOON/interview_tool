import { Routes, Route, Navigate } from 'react-router-dom';
import { useEffect, lazy, Suspense } from 'react';
import Spin from 'antd/es/spin';
import { useAppStore } from '@/store';

import Navbar from '@/components/layout/Navbar';
import DashboardLayout from '@/components/layout/DashboardLayout';

import LandingPage from '@/pages/LandingPage';
import LoginPage from '@/pages/auth/LoginPage';
import CallbackPage from '@/pages/auth/CallbackPage';
import NotFoundPage from '@/pages/NotFoundPage';
import PrivacyPage from '@/pages/PrivacyPage';

const DashboardHome = lazy(() => import('@/pages/dashboard/HomePage'));
const InterviewPage = lazy(() => import('@/pages/dashboard/interview/InterviewPage'));
const InterviewSession = lazy(() => import('@/pages/dashboard/interview/InterviewSessionPage'));
const HistoryPage = lazy(() => import('@/pages/dashboard/interview/HistoryPage'));
const ReportPage = lazy(() => import('@/pages/dashboard/interview/ReportPage'));
const FeedPage = lazy(() => import('@/pages/dashboard/community/FeedPage'));
const CommunityPage = lazy(() => import('@/pages/dashboard/community/CommunityPage'));
const PostDetailPage = lazy(() => import('@/pages/dashboard/community/PostDetailPage'));
const FavoritesPage = lazy(() => import('@/pages/dashboard/community/FavoritesPage'));
const MessagesPage = lazy(() => import('@/pages/dashboard/messages/MessagesPage'));
const MessageDetailPage = lazy(() => import('@/pages/dashboard/messages/MessageDetailPage'));
const ChatPage = lazy(() => import('@/pages/dashboard/messages/ChatPage'));
const UserPage = lazy(() => import('@/pages/dashboard/social/UserPage'));
const ProfilePage = lazy(() => import('@/pages/dashboard/social/ProfilePage'));
const FollowingPage = lazy(() => import('@/pages/dashboard/social/FollowingPage'));
const FollowersPage = lazy(() => import('@/pages/dashboard/social/FollowersPage'));
const SettingsPage = lazy(() => import('@/pages/dashboard/settings/SettingsPage'));
const HelpPage = lazy(() => import('@/pages/dashboard/settings/HelpPage'));

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);
  const authLoading = useAppStore((s) => s.authLoading);

  if (authLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spin size="large" />
      </div>
    );
  }

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
  const initAuth = useAppStore((s) => s.initAuth);

  useEffect(() => {
    void initAuth();
  }, []);

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
      <Route path="/callback" element={<CallbackPage />} />
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