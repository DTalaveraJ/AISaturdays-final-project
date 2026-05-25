import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tu IAbuela de Confianza",
  description: "Optimiza tu compra semanal con inteligencia artificial",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="bg-[#0e1626] text-gray-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}
