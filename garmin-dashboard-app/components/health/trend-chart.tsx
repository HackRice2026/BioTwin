"use client";

import { useEffect, useRef, useState } from "react";
import { formatClockTime, formatDay, formatDayTime } from "@/lib/stats";

type Point = { t: string; v: number };
type TimeFormat = "clock" | "day-time" | "day";

// Server Component props can't carry function references across the
// client boundary (they're not serializable) -- pass a plain string mode
// instead and let this client component own the actual formatting.
const FORMATTERS: Record<TimeFormat, (iso: string) => string> = {
  clock: formatClockTime,
  "day-time": formatDayTime,
  day: formatDay,
};

/**
 * Full-size trend chart -- unlike Sparkline (a bare stat-tile trend
 * indicator, which the dataviz skill exempts from needing a hover layer),
 * this is a standalone chart people are meant to read patterns from, so it
 * always ships the hover crosshair + tooltip per interaction.md.
 */
export function TrendChart({
  points,
  color,
  height = 240,
  unit = "",
  timeFormat = "clock",
}: {
  points: Point[];
  color: string;
  height?: number;
  unit?: string;
  timeFormat?: TimeFormat;
}) {
  const formatTime = FORMATTERS[timeFormat];
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; point: Point } | null>(null);
  const plotRef = useRef<{
    xAt: (i: number) => number;
    yAt: (v: number) => number;
    w: number;
    h: number;
  } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const w = rect.width;
      const h = rect.height;
      ctx.clearRect(0, 0, w, h);
      if (points.length < 2) {
        plotRef.current = null;
        return;
      }

      const values = points.map((p) => p.v);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const pad = Math.max(1, (max - min) * 0.15);
      const lo = min - pad;
      const hi = max + pad;

      const xAt = (i: number) => (i / (points.length - 1)) * w;
      const yAt = (v: number) => h - ((v - lo) / (hi - lo || 1)) * h;

      // gridlines -- hairline, recessive, one-step-off-surface gray
      ctx.strokeStyle = "#e1e0d9";
      ctx.lineWidth = 1;
      for (let g = 0; g <= 3; g++) {
        const y = Math.round((h / 3) * g) + 0.5;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // area fill, ~10% opacity
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = xAt(i);
        const y = yAt(p.v);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.lineTo(xAt(points.length - 1), h);
      ctx.lineTo(xAt(0), h);
      ctx.closePath();
      ctx.fillStyle = color + "1a";
      ctx.fill();

      // line, 2px
      ctx.beginPath();
      points.forEach((p, i) => {
        const x = xAt(i);
        const y = yAt(p.v);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();

      plotRef.current = { xAt, yAt, w, h };
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, color]);

  const handleMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const plot = plotRef.current;
    if (!plot || points.length < 2) return;
    const rect = wrapRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    let nearest = 0;
    let best = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(plot.xAt(i) - mx);
      if (d < best) {
        best = d;
        nearest = i;
      }
    });
    const p = points[nearest];
    setHover({ x: plot.xAt(nearest), y: plot.yAt(p.v), point: p });
  };

  return (
    <div
      ref={wrapRef}
      className="relative w-full"
      onMouseMove={handleMove}
      onMouseLeave={() => setHover(null)}
    >
      <canvas ref={canvasRef} className="w-full rounded-2xl" style={{ height }} />
      {hover && (
        <>
          <div
            className="pointer-events-none absolute top-0 w-px bg-border"
            style={{ left: hover.x, height }}
          />
          <div
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-[calc(100%+10px)] whitespace-nowrap rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-sm"
            style={{ left: hover.x, top: hover.y }}
          >
            <span className="text-sm font-bold text-foreground">
              {hover.point.v}
              {unit}
            </span>
            <span className="ml-1.5 text-muted-foreground">
              {formatTime(hover.point.t)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
