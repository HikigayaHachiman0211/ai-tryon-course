import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { RadarData } from '../types';

interface RadarChartProps {
  data: RadarData[];
}

export const RadarChart: React.FC<RadarChartProps> = ({ data }) => {
  const option = useMemo(() => {
    // Fill in default values if less than 4 (color, size, style, personality)
    const indicators = [
      { name: '颜色适配度', max: 100 },
      { name: '身材适配度', max: 100 },
      { name: '款式适配度', max: 100 },
      { name: '品牌偏好度', max: 100 },
      { name: '性格适配度', max: 100 }
    ];

    const values = indicators.map(ind => {
      const found = data.find(d => d.dimension === ind.name);
      return found ? found.score : 60; // default score if missing
    });

    return {
      radar: {
        indicator: indicators,
        radius: '60%',
        splitNumber: 4,
        axisName: {
          color: 'rgba(255, 255, 255, 0.7)',
          fontSize: 11,
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
              name: '匹配分数',
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
        backgroundColor: 'rgba(29, 29, 31, 0.94)',
        borderColor: 'rgba(255,255,255,0.08)',
        textStyle: {
          color: '#ffffff'
        }
      }
    };
  }, [data]);

  return (
    <ReactECharts
      option={option}
      style={{ height: '200px', width: '100%' }}
      opts={{ renderer: 'svg' }}
    />
  );
};
