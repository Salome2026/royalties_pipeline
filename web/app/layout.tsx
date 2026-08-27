import "./globals.css";
import "./components/vpo-app-frame.css";

export const metadata = {
  title: "VPO Corp",
  description: "VPO Corp royalties reporting",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
