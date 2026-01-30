import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-geist-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

export const metadata: Metadata = {
  title: "Agent007 Command Center",
  description: "AI-powered orchestration dashboard for autonomous agent management",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans min-h-screen bg-gradient-to-br from-background via-background to-background`}
      >
        {/* Ambient background effects */}
        <div className="fixed inset-0 -z-10 overflow-hidden">
          <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-radial from-violet-500/10 via-transparent to-transparent blur-3xl" />
          <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-radial from-fuchsia-500/10 via-transparent to-transparent blur-3xl" />
        </div>
        
        {children}
      </body>
    </html>
  );
}
