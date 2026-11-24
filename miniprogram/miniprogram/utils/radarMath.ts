import type { RadarData } from '../types/api';

export type RadarAxisCode = 'color' | 'size' | 'style' | 'brand' | 'personality';

export interface NormalizedRadarAxis {
  code: RadarAxisCode;
  label: string;
  score: number;
  angleRad: number;
  x: number;
  y: number;
  labelX: number;
  labelY: number;
}

export const RADAR_AXIS_ORDER: RadarAxisCode[] = [
  'color',
  'size',
  'style',
  'brand',
  'personality',
];

export function clampScore(raw: unknown, fallback = 60): number {
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(0, Math.min(100, Math.round(n)));
}

export function extractRadarAxes(
  data: RadarData[] | null | undefined,
  labelsByCode: Record<RadarAxisCode, string>,
): Array<{ code: RadarAxisCode; label: string; score: number }> {
  const list = Array.isArray(data) ? data : [];
  return RADAR_AXIS_ORDER.map((code) => {
    const label = labelsByCode[code] || code;
    const found = list.find(
      (item) => item.code === code || item.dimension === label || item.label === label,
    );
    return {
      code,
      label,
      score: found ? clampScore(found.score) : 60,
    };
  });
}

export function computeRadarGeometry(
  axes: Array<{ code: RadarAxisCode; label: string; score: number }>,
  cx: number,
  cy: number,
  radius: number,
  labelOffset = 22,
): NormalizedRadarAxis[] {
  const total = axes.length || 5;
  return axes.map((axis, idx) => {
    const angleRad = -Math.PI / 2 + (idx * 2 * Math.PI) / total;
    const ratio = clampScore(axis.score) / 100;
    const r = radius * ratio;
    const lr = radius + labelOffset;
    return {
      code: axis.code,
      label: axis.label,
      score: clampScore(axis.score),
      angleRad,
      x: cx + Math.cos(angleRad) * r,
      y: cy + Math.sin(angleRad) * r,
      labelX: cx + Math.cos(angleRad) * lr,
      labelY: cy + Math.sin(angleRad) * lr,
    };
  });
}

export function computeRingPoints(
  count: number,
  cx: number,
  cy: number,
  radius: number,
): Array<{ x: number; y: number }> {
  const points: Array<{ x: number; y: number }> = [];
  for (let i = 0; i < count; i += 1) {
    const angleRad = -Math.PI / 2 + (i * 2 * Math.PI) / count;
    points.push({
      x: cx + Math.cos(angleRad) * radius,
      y: cy + Math.sin(angleRad) * radius,
    });
  }
  return points;
}
