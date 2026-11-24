import { getLocale, t } from '../../i18n';
import type { RadarData } from '../../types/api';
import {
  computeRadarGeometry,
  computeRingPoints,
  extractRadarAxes,
  type RadarAxisCode,
} from '../../utils/radarMath';

interface CanvasQueryEntry {
  node?: WechatMiniprogram.Canvas;
  width?: number;
  height?: number;
}

Component({
  properties: {
    data: {
      type: Array,
      value: [] as RadarData[],
    },
    locale: {
      type: String,
      value: getLocale(),
    },
  },
  data: {
    title: t('score.radarTitle'),
  },
  observers: {
    'data, locale'() {
      this.setData({ title: t('score.radarTitle') });
      this.scheduleDraw();
    },
  },
  lifetimes: {
    ready() {
      this.scheduleDraw();
    },
  },
  methods: {
    scheduleDraw() {
      wx.nextTick(() => {
        this.drawChart();
      });
    },
    drawChart() {
      const query = this.createSelectorQuery();
      query
        .select('#radarCanvas')
        .fields({ node: true, size: true })
        .exec((res: CanvasQueryEntry[]) => {
          const entry = res && res[0];
          if (!entry || !entry.node) return;
          const canvas = entry.node;
          const width = entry.width || 280;
          const height = entry.height || 210;
          const winInfo = typeof wx.getWindowInfo === 'function' ? wx.getWindowInfo() : null;
          const dpr = (winInfo && winInfo.pixelRatio) || 2;

          canvas.width = Math.round(width * dpr);
          canvas.height = Math.round(height * dpr);

          const ctx = canvas.getContext('2d');
          if (!ctx) return;
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          ctx.clearRect(0, 0, width, height);

          const labelsByCode: Record<RadarAxisCode, string> = {
            color: t('score.color'),
            size: t('score.size'),
            style: t('score.style'),
            brand: t('score.brand'),
            personality: t('score.personality'),
          };
          const axes = extractRadarAxes(this.properties.data as RadarData[], labelsByCode);
          const cx = width / 2;
          const cy = height / 2 + 4;
          const radius = Math.min(width, height) * 0.31;
          const geom = computeRadarGeometry(axes, cx, cy, radius, 26);

          const rings = 4;
          for (let ringIdx = 1; ringIdx <= rings; ringIdx += 1) {
            const ringR = (radius * ringIdx) / rings;
            const pts = computeRingPoints(geom.length, cx, cy, ringR);
            ctx.beginPath();
            pts.forEach((pt, idx) => {
              if (idx === 0) ctx.moveTo(pt.x, pt.y);
              else ctx.lineTo(pt.x, pt.y);
            });
            ctx.closePath();
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.14)';
            ctx.lineWidth = 1;
            ctx.stroke();
            if (ringIdx % 2 === 1) {
              ctx.fillStyle = 'rgba(255, 255, 255, 0.02)';
              ctx.fill();
            }
          }

          const outerPts = computeRingPoints(geom.length, cx, cy, radius);
          outerPts.forEach((pt) => {
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(pt.x, pt.y);
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
            ctx.lineWidth = 1;
            ctx.stroke();
          });

          ctx.beginPath();
          geom.forEach((pt, idx) => {
            if (idx === 0) ctx.moveTo(pt.x, pt.y);
            else ctx.lineTo(pt.x, pt.y);
          });
          ctx.closePath();
          ctx.fillStyle = 'rgba(0, 113, 227, 0.25)';
          ctx.fill();
          ctx.strokeStyle = '#2997ff';
          ctx.lineWidth = 2;
          ctx.stroke();

          ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          geom.forEach((pt) => {
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 3.5, 0, Math.PI * 2);
            ctx.fillStyle = '#64d2ff';
            ctx.fill();
            ctx.strokeStyle = '#0a0a0c';
            ctx.lineWidth = 1.2;
            ctx.stroke();

            ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
            ctx.fillText(`${pt.label} ${pt.score}`, pt.labelX, pt.labelY);
          });
        });
    },
  },
});
