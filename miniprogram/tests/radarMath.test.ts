import { describe, expect, it } from 'vitest';
import {
  clampScore,
  computeRadarGeometry,
  computeRingPoints,
  extractRadarAxes,
} from '../miniprogram/utils/radarMath';

describe('radar chart geometry math', () => {
  it('extracts 5 canonical axes and clamps scores to [0, 100]', () => {
    expect(clampScore(135)).toBe(100);
    expect(clampScore(-10)).toBe(0);
    expect(clampScore('bad', 60)).toBe(60);

    const axes = extractRadarAxes(
      [
        { dimension: '颜色', code: 'color', score: 92 },
        { dimension: '尺码', code: 'size', score: 84 },
        { dimension: '个性', code: 'personality', score: 105 },
      ],
      {
        color: '颜色',
        size: '尺码',
        style: '版型',
        brand: '品牌',
        personality: '个性',
      },
    );
    expect(axes.map((a) => a.score)).toEqual([92, 84, 60, 60, 100]);
  });

  it('computes centered pentagon ring points and axis vertices', () => {
    const ring = computeRingPoints(5, 100, 100, 50);
    expect(ring).toHaveLength(5);
    expect(Math.round(ring[0].x)).toBe(100);
    expect(Math.round(ring[0].y)).toBe(50);

    const geom = computeRadarGeometry(
      [
        { code: 'color', label: 'Color', score: 100 },
        { code: 'size', label: 'Size', score: 50 },
        { code: 'style', label: 'Style', score: 50 },
        { code: 'brand', label: 'Brand', score: 50 },
        { code: 'personality', label: 'MBTI', score: 50 },
      ],
      100,
      100,
      50,
      20,
    );
    expect(Math.round(geom[0].x)).toBe(100);
    expect(Math.round(geom[0].y)).toBe(50);
    expect(Math.round(geom[0].labelY)).toBe(30);
  });
});
