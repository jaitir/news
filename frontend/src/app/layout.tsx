import type { Metadata } from "next";
import { PT_Sans, PT_Serif } from "next/font/google";
import "./globals.css";

const spaceGrotesk = PT_Sans({
  variable: "--font-space-grotesk",
  subsets: ["latin", "cyrillic"],
  weight: ["400", "700"],
});

const newsreader = PT_Serif({
  variable: "--font-newsreader",
  subsets: ["latin", "cyrillic"],
  weight: ["400", "700"],
});

export const metadata: Metadata = {
  title: "Global Media Intelligence",
  description:
    "Cross-source analyst workspace for global news, X, Telegram, and narrative tracking.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ru"
      suppressHydrationWarning
      className={`${spaceGrotesk.variable} ${newsreader.variable} h-full antialiased`}
    >
      <body suppressHydrationWarning className="min-h-full flex flex-col">
        {children}
      </body>
    </html>
  );
}
