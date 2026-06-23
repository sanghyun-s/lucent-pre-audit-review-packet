"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// plotly.js is heavy and uses `window`. Disable SSR.
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <div className="h-72 flex items-center justify-center text-sm text-muted-foreground">Loading chart…</div>,
});

const COLOR_MAP = {
  "Potential Material Weakness Indicator": "#c0392b",
  "Potential Significant Deficiency":      "#e67e22",
  "Monitor — Below Escalation Threshold":  "#7f8c8d",
};

export default function RiskDistributionChart({ data }) {
  if (!data?.length) return null;

  const labels = data.map((d) => d.label);
  const counts = data.map((d) => d.count);
  const colors = labels.map((l) => COLOR_MAP[l] || "#888");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Transactions by Review Tier</CardTitle>
      </CardHeader>
      <CardContent>
        <Plot
          data={[
            {
              x: labels,
              y: counts,
              type: "bar",
              marker: { color: colors },
              text: counts.map(String),
              textposition: "outside",
              hovertemplate: "%{x}<br>%{y} transactions<extra></extra>",
            },
          ]}
          layout={{
            margin: { t: 20, l: 50, r: 20, b: 80 },
            xaxis: { tickangle: -15, automargin: true },
            yaxis: { title: "Transaction count" },
            showlegend: false,
            height: 320,
          }}
          config={{ displayModeBar: false, responsive: true }}
          useResizeHandler
          style={{ width: "100%" }}
        />
      </CardContent>
    </Card>
  );
}
