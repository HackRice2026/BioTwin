"use client";

import { useEffect, useRef } from "react";

type Point = { t: string; v: number };

/**
 * A 2px line + ~10% opacity area fill, per the dataviz skill's mark specs.
 * Renders in a single accent color (this is always a single-series chart --
 * identity comes from the card it's inside of, not a legend).
 */
export function Sparkline({
  points,
  color,
  height = 64,
}: {
  points: Point[];
  color: string;
  height?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

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
      if (points.length < 2) return;

      const values = points.map((p) => p.v);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const pad = Math.max(1, (max - min) * 0.15);
      const lo = min - pad;
      const hi = max + pad;

      const xAt = (i: number) => (i / (points.length - 1)) * w;
      const yAt = (v: number) => h - ((v - lo) / (hi - lo || 1)) * h;

      ctx.beginPath();
      points.forEach((p, i) => {
        const x = xAt(i);
        const y = yAt(p.v);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.lineTo(xAt(points.length - 1), h);
      ctx.lineTo(xAt(0), h);
      ctx.closePath();
      ctx.fillStyle = color + "1a"; // ~10% opacity
      ctx.fill();

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
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, color]);

  return <canvas ref={canvasRef} className="w-full" style={{ height }} />;
}
