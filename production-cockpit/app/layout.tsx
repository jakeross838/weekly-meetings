import type { Metadata, Viewport } from "next";
import { Space_Grotesk, Inter, JetBrains_Mono } from "next/font/google";
import { cn } from "@/lib/utils";
import { VersionFooter } from "@/components/version-footer";
import "./globals.css";

const head = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-head",
});

const sans = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Production · Ross Built",
  description: "Production Director cockpit",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(head.variable, sans.variable, mono.variable)}
    >
      <head>
        {/* Apply the saved view mode before paint so there's no mobile→desktop
            flash. Pairs with components/view-toggle.tsx. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{if(localStorage.getItem('viewMode')==='desktop')document.documentElement.classList.add('view-desktop')}catch(e){}",
          }}
        />
      </head>
      <body className="font-sans antialiased bg-background text-foreground">
        {children}
        <VersionFooter />
      </body>
    </html>
  );
}
