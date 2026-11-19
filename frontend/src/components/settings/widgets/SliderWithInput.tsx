import React, { useEffect, useState } from 'react';

export interface SliderWithInputProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (val: number) => void;
  description?: string;
  error?: string;
  className?: string;
}

export const SliderWithInput: React.FC<SliderWithInputProps> = ({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
  description,
  error,
  className = '',
}) => {
  const [draft, setDraft] = useState<string>(() => String(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) {
      setDraft(String(value));
    }
  }, [value, focused]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    setDraft(raw);
    const num = parseFloat(raw);
    if (Number.isFinite(num)) {
      onChange(num);
    }
  };

  const handleBlur = () => {
    setFocused(false);
    const num = parseFloat(draft);
    if (!Number.isFinite(num)) {
      setDraft(String(value));
      return;
    }
    const clamped = Math.min(max, Math.max(min, num));
    if (clamped !== value) {
      onChange(clamped);
    }
    setDraft(String(clamped));
  };

  const sliderVal = Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : min;

  return (
    <div className={`py-2 ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-semibold text-[#111111]">{label}</label>
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={min}
            max={max}
            step={step}
            value={draft}
            onChange={handleInputChange}
            onFocus={() => setFocused(true)}
            onBlur={handleBlur}
            className="w-20 px-2 py-0.5 text-xs text-right font-mono tabular-nums rounded-[6px] bg-[#F4F5F6] border border-black/[0.08] text-[#111111] font-semibold focus:bg-white focus:border-[#111111] focus:outline-none select-text"
          />
          {unit && <span className="text-[11px] text-[#71717A] w-6">{unit}</span>}
        </div>
      </div>
      {description && <p className="text-[11px] text-[#71717A] mb-1.5 leading-snug">{description}</p>}
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={sliderVal}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="flex-1 studio-range cursor-pointer"
        />
      </div>
      {error && <p className="text-[11px] text-[#B91C1C] mt-1">{error}</p>}
    </div>
  );
};
