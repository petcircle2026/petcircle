import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PetCircle — Pet Health Dashboard",
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
