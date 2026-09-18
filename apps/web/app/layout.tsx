import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Socratic Tutor",
  description: "Voice-first mastery tutor for CA Final Financial Reporting",
};

export const viewport: Viewport = {
  themeColor: "#09090b",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className="h-dvh flex flex-col overflow-hidden bg-zinc-950 text-zinc-100">{children}</body>
    </html>
  );
}
