import React, { useEffect, useState } from 'react';

export interface NullableNumberInputProps {
  label: string;
  value: number | null;
  onChange: (val: number | null) => void;
  description?: string;
  placeholder?: string;
  error?: string;
  className?: string;
  allowFloat?: boolean;
  min?: number;
  max?: number;
  step?: string | number;
}

export const NullableNumberInput: React.FC<NullableNumberInputProps> = ({
  label,
  value,
  onChange,
  description,
  placeholder = '空欄（自動選択）',
  error,
  className = '',
  allowFloat = false,
  min,
  max,
  step,
}) => {
  const formatVal = (v: number | null | undefined) =>
    v === null || v === undefined ? '' : String(v);
  const [text, setText] = useState<string>(() => formatVal(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) {
      setText(formatVal(value));
    }
  }, [value, focused]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    setText(raw);
    const trimmed = raw.trim();
    if (trimmed === '') {
      onChange(null);
      return;
    }
    const num = allowFloat ? Number(trimmed) : parseInt(trimmed, 10);
    if (Number.isFinite(num)) {
      onChange(num);
    }
  };

  const handleBlur = () => {
    setFocused(false);
    setText(formatVal(value));
  };

  return (
    <div className={`py-2 ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-semibold text-[#111111]">{label}</label>
      </div>
      {description && <p className="text-[11px] text-[#71717A] mb-1.5 leading-snug">{description}</p>}
      <input
        type="number"
        min={min}
        max={max}
        step={step ?? (allowFloat ? 'any' : 1)}
        value={text}
        onChange={handleChange}
        onFocus={() => setFocused(true)}
        onBlur={handleBlur}
        placeholder={placeholder}
        className="w-full h-9 px-3 text-xs rounded-[6px] bg-[#F4F5F6] border border-black/[0.08] text-[#111111] font-mono tabular-nums placeholder:text-[#A1A1AA] focus:bg-white focus:border-[#111111] focus:outline-none select-text"
      />
      {error && <p className="text-[11px] text-[#B91C1C] mt-1">{error}</p>}
    </div>
  );
};
