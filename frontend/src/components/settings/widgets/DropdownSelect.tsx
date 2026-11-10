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
        <label className="text-xs font-bold text-[#1E293B]">{label}</label>
      </div>
      {description && <p className="text-[11px] text-[#64748B] mb-1.5">{description}</p>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg bg-white text-[#1E293B] hover:border-[#8DA49E] focus:border-[#0F766E] focus:outline-none transition-colors cursor-pointer"
      >
        {options.map((opt) => {
          const val = typeof opt === 'string' ? opt : opt.value;
          const lbl = typeof opt === 'string' ? opt : opt.label;
          return (
            <option key={val} value={val}>
              {lbl}
            </option>
          );
        })}
      </select>
      {error && <p className="text-[11px] text-[#C8332B] mt-1">{error}</p>}
    </div>
  );
};
