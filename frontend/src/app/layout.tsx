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
            <nav className="flex items-center gap-6">
              <Link href="/" className="text-sm font-medium text-slate-300 hover:text-white transition-colors">
                Live Dashboard
              </Link>
              <Link href="/forecast" className="relative px-4 py-1.5 rounded-full text-sm font-semibold text-cyan-400 bg-cyan-950/50 border border-cyan-500/30 hover:bg-cyan-900/50 hover:border-cyan-500/50 transition-all flex items-center gap-1.5 shadow-[0_0_15px_rgba(6,182,212,0.15)]">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
                AI Tipping Forecast
              </Link>
            </nav>
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
