import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "面经雷达 | OfferGraph",
  description: "面试情报聚合与结构化分析系统，助力求职者精准备战",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="bg-zinc-950 text-zinc-100 antialiased">{children}</body>
    </html>
  );
}
