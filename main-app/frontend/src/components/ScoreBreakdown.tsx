interface ScoreBreakdownProps {
  breakdown: Record<string, number>;
}

export function ScoreBreakdown({ breakdown }: ScoreBreakdownProps) {
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
          {label} {score}
        </span>
      ))}
    </div>
  );
}
