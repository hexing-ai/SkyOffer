import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "SkyOffer · 可核验选校建议",
  description: "基于官网门槛与字段级证据的 2027 授课型硕士选校建议工具。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
