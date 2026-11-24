import { useTranslation } from 'react-i18next';

interface ScoreBreakdownProps {
  breakdown: Record<string, number>;
}

export function ScoreBreakdown({ breakdown }: ScoreBreakdownProps) {
  const { t } = useTranslation(['styleLab', 'common']);
  const codeByLegacyLabel: Record<string, string> = {
    '颜色适配度': 'color',
    '身材适配度': 'size',
    '款式适配度': 'style',
    '品牌偏好度': 'brand',
    '性格适配度': 'personality',
  };
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
      {Object.entries(breakdown).map(([label, score]) => (
        <span
          key={label}
          style={{
            fontSize: 11,
            background: 'rgba(56, 189, 248, 0.08)',
            border: '1px solid rgba(56, 189, 248, 0.18)',
            padding: '4px 8px',
            borderRadius: 999,
            color: 'var(--text-secondary)',
          }}
        >
          {t(`score.dimension.${codeByLegacyLabel[label] ?? label}`)} {score}
        </span>
      ))}
    </div>
  );
}
