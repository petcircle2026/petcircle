import type { Metadata } from "next";
import { APP_DASHBOARD_TITLE } from "@/lib/branding";
import "./globals.css";

export const metadata: Metadata = {
  title: APP_DASHBOARD_TITLE,
  description: "View your pet's preventive health records and reminders",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
