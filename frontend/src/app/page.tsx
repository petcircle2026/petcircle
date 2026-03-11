import Link from "next/link";
import { APP_BRAND_NAME } from "@/lib/branding";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-3xl font-bold">{APP_BRAND_NAME}</h1>
      <p className="mt-4 text-gray-600 text-center">
        Preventive pet health system powered by WhatsApp.
        <br />
        Access your pet dashboard via the link sent on WhatsApp.
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          href="/admin"
          className="rounded-lg bg-gray-900 px-6 py-3 text-white hover:bg-gray-700 transition-colors"
        >
          Admin Dashboard
        </Link>
      </div>
    </main>
  );
}
