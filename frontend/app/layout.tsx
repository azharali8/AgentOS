import './globals.css';
import React from 'react';

export const metadata = {
  title: 'AgentOS Control Center',
  description: 'AI Engineering Operating System Control Center',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen theme-bg-canvas theme-text-primary">
        {children}
      </body>
    </html>
  );
}
