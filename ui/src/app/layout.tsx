import type { Metadata } from "next";
import "@/app/globals.css";
import { AppProviders } from "@/components/providers";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "AI Content Ops UI",
  description: "Uploader, moderator, and admin UI for AI content operations backend."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <AppProviders>
          <AppShell>{children}</AppShell>
        </AppProviders>
      </body>
    </html>
  );
}
