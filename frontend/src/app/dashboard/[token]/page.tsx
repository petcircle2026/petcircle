import type { Metadata } from "next";
import DashboardClient from "@/components/DashboardClient";
import { APP_DASHBOARD_PAGE_TITLE } from "@/lib/branding";

export const metadata: Metadata = {
  title: APP_DASHBOARD_PAGE_TITLE,
};

interface DashboardPageProps {
  params: Promise<{ token: string }>;
}

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { token } = await params;
  return <DashboardClient token={token} />;
}
