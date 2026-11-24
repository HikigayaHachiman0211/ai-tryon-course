import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useTranslation } from 'react-i18next';
import type { RadarData } from '../types';

interface RadarChartProps {
  data: RadarData[];
}

export const RadarChart: React.FC<RadarChartProps> = ({ data }) => {
  const { t } = useTranslation(['styleLab', 'common']);
  const option = useMemo(() => {
    const indicators = [
      { code: 'color', name: t('score.dimension.color'), max: 100 },
      { code: 'size', name: t('score.dimension.size'), max: 100 },
      { code: 'style', name: t('score.dimension.style'), max: 100 },
      { code: 'brand', name: t('score.dimension.brand'), max: 100 },
      { code: 'personality', name: t('score.dimension.personality'), max: 100 },
    ];

    const values = indicators.map(ind => {
      const found = data.find(d => d.code === ind.code || d.dimension === ind.name);
      return found ? found.score : 60; // default score if missing
    });

    return {
      radar: {
        indicator: indicators,
        radius: '52%',
        splitNumber: 4,
        axisName: {
          color: 'rgba(255, 255, 255, 0.7)',
          fontSize: 10,
          overflow: 'truncate',
          width: 70,
        },
        splitLine: {
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.12)',
          }
        },
        splitArea: {
          areaStyle: {
            color: ['rgba(255, 255, 255, 0.025)', 'transparent']
          }
        },
        axisLine: {
          lineStyle: {
            color: 'rgba(255, 255, 255, 0.12)'
          }
        }
      },
      series: [
        {
          type: 'radar',
          data: [
            {
              value: values,
              name: t('score.matchScore'),
              areaStyle: {
                color: 'rgba(0, 113, 227, 0.18)'
              },
              lineStyle: {
                color: '#0071e3',
                width: 2
              },
              itemStyle: {
                color: '#0071e3',
                borderWidth: 2
              }
            }
          ]
        }
      ],
      tooltip: {
        trigger: 'item',
        confine: true,
        backgroundColor: 'rgba(29, 29, 31, 0.94)',
        borderColor: 'rgba(255,255,255,0.08)',
        textStyle: {
          color: '#ffffff'
        }
      }
    };
  }, [data, t]);

  return (
    <ReactECharts
      option={option}
      style={{ height: '200px', width: '100%' }}
      opts={{ renderer: 'svg' }}
    />
  );
};
