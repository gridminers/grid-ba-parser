import "./globals.css";

export const metadata = {
  title: "Grid BA Parser",
  description: "Technical PDF extraction console"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
