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
        <label className="text-xs font-bold text-[#1E293B]">{label}</label>
      </div>
      {description && <p className="text-[11px] text-[#64748B] mb-1.5">{description}</p>}
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
        className="w-full h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg bg-white text-[#1E293B] font-mono focus:border-[#0F766E] focus:outline-none"
      />
      {error && <p className="text-[11px] text-[#C8332B] mt-1">{error}</p>}
    </div>
  );
};
