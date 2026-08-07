import { render, type RenderResult, type RenderOptions } from '@testing-library/react';
import type { ReactElement } from 'react';
import { DashboardProvider } from '@/contexts/DashboardContext';

/**
 * Render a widget (or any component that calls useDashboard) wrapped in the
 * DashboardProvider, matching how widgets are mounted in the real app.
 */
export function renderWithDashboard(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>): RenderResult {
  return render(ui, { wrapper: DashboardProvider, ...options });
}
