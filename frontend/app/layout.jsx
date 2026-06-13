import "./globals.css";

export const metadata = {
  title: "ARGUS — Audit Risk Guidance, Unified System",
  description:
    "ML anomaly detection + materiality-calibrated risk scoring + PCAOB-aligned labels for QuickBooks GL exports.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background antialiased">{children}</body>
    </html>
  );
}