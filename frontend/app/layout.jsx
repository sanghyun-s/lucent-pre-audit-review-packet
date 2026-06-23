import "./globals.css";

export const metadata = {
  title: "LUCENT — Pre-Audit Review Packet",
  description:
    "Narrow a full general-ledger export into a prioritized review queue — see what to check, why it matters, and what evidence to request before close, CPA handoff, audit readiness, or investor diligence.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background antialiased">{children}</body>
    </html>
  );
}
