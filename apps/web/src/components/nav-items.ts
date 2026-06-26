/**
 * Primary navigation config — one entry per authenticated screen. Kept in its own module (not the
 * layout component file) so the layout exports only components (react-refresh friendly).
 */
import {
  BookOpen,
  Compass,
  Languages as LanguagesIcon,
  LayoutDashboard,
  Settings as SettingsIcon,
  Sparkles,
  User,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/generate', label: 'Generate', icon: Sparkles },
  { to: '/review', label: 'Review', icon: BookOpen },
  { to: '/discover', label: 'Discover', icon: Compass },
  { to: '/languages', label: 'Languages', icon: LanguagesIcon },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
  { to: '/account', label: 'Account', icon: User },
];
