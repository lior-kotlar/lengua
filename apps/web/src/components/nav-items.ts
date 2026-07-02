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

/**
 * The mobile bottom tab bar fits four destinations (the core loop) plus a "More" slot; the
 * remaining screens live in the More bottom sheet. Slicing NAV_ITEMS (rather than separate
 * lists) keeps labels/icons byte-identical to the sidebar, which the pinned
 * h1-equals-nav-label test contract relies on.
 */
export const MOBILE_TAB_ITEMS: NavItem[] = NAV_ITEMS.slice(0, 4);
export const MORE_SHEET_ITEMS: NavItem[] = NAV_ITEMS.slice(4);
