import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ClimaSentinel",
  description: "Global Climate Tipping Point Tracker",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Sticky Global Navigation */}
        <header className="sticky top-0 z-50 glass-panel border-b border-white/5 px-6 py-3">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 group transition-opacity hover:opacity-80">
              <span className="font-black text-xl tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-slate-100 to-slate-400">
                ClimaSentinel
              </span>
            </Link>
          </div>
        </header>

        {/* Main Content */}
        <div className="flex-1">
          {children}
        </div>
      </body>
    </html>
  );
}
