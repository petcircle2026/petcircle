import type { Metadata } from "next";
import DashboardClient from "@/components/DashboardClient";

export const metadata: Metadata = {
  title: "Pet Health Dashboard — PetCircle",
};

interface DashboardPageProps {
  params: Promise<{ token: string }>;
}

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { token } = await params;
  return <DashboardClient token={token} />;
}
