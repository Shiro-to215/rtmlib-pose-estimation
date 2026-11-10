import React from 'react';

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
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const num = parseFloat(raw);
    if (!isNaN(num)) {
      onChange(num);
    }
  };

  return (
    <div className={`py-2 ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-bold text-[#1E293B]">{label}</label>
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={handleInputChange}
            className="w-20 px-2 py-0.5 text-xs text-right font-mono border border-[#CBD5E1] rounded focus:border-[#0F766E] focus:outline-none bg-white text-[#1E293B]"
          />
          {unit && <span className="text-[11px] text-[#64748B] w-6">{unit}</span>}
        </div>
      </div>
      {description && <p className="text-[11px] text-[#64748B] mb-1.5">{description}</p>}
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="flex-1 h-1.5 bg-[#E2E8F0] rounded-lg appearance-none cursor-pointer accent-[#0F766E]"
        />
      </div>
      {error && <p className="text-[11px] text-[#C8332B] mt-1">{error}</p>}
    </div>
  );
};
