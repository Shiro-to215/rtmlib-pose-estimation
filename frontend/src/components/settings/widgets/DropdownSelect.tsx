import React from 'react';

export interface DropdownSelectOption {
  value: string;
  label: string;
}

export interface DropdownSelectProps {
  label: string;
  value: string;
  options: (string | DropdownSelectOption)[];
  onChange: (val: string) => void;
  description?: string;
  error?: string;
  className?: string;
}

export const DropdownSelect: React.FC<DropdownSelectProps> = ({
  label,
  value,
  options,
  onChange,
  description,
  error,
  className = '',
}) => {
  return (
    <div className={`py-2 ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-semibold text-[#111111]">{label}</label>
      </div>
      {description && <p className="text-[11px] text-[#71717A] mb-1.5 leading-snug">{description}</p>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-9 px-3 text-xs rounded-[6px] bg-[#F4F5F6] border border-black/[0.08] text-[#111111] hover:border-black/20 focus:bg-white focus:border-[#111111] focus:outline-none transition-colors cursor-pointer"
      >
        {options.map((opt) => {
          const val = typeof opt === 'string' ? opt : opt.value;
          const lbl = typeof opt === 'string' ? opt : opt.label;
          return (
            <option key={val} value={val} className="bg-white text-[#111111]">
              {lbl}
            </option>
          );
        })}
      </select>
      {error && <p className="text-[11px] text-[#B91C1C] mt-1">{error}</p>}
    </div>
  );
};
