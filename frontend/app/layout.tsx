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
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
