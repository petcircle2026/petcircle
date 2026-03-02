import type { Metadata } from "next";
import DashboardClient from "@/components/DashboardClient";

export const metadata: Metadata = {
  title: "Pet Health Dashboard — PetCircle",
};

interface DashboardPageProps {
  params: { token: string };
}

export default function DashboardPage({ params }: DashboardPageProps) {
  return <DashboardClient token={params.token} />;
}
