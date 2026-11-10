import React from 'react';

export interface NullableNumberInputProps {
  label: string;
  value: number | null;
  onChange: (val: number | null) => void;
  description?: string;
  placeholder?: string;
  error?: string;
  className?: string;
}

export const NullableNumberInput: React.FC<NullableNumberInputProps> = ({
  label,
  value,
  onChange,
  description,
  placeholder = '空欄（自動選択）',
  error,
  className = '',
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value.trim();
    if (raw === '') {
      onChange(null);
    } else {
      const num = parseInt(raw, 10);
      if (!isNaN(num)) {
        onChange(num);
      }
    }
  };

  return (
    <div className={`py-2 ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-bold text-[#1E293B]">{label}</label>
      </div>
      {description && <p className="text-[11px] text-[#64748B] mb-1.5">{description}</p>}
      <input
        type="number"
        value={value === null || value === undefined ? '' : value}
        onChange={handleChange}
        placeholder={placeholder}
        className="w-full h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg bg-white text-[#1E293B] font-mono focus:border-[#0F766E] focus:outline-none"
      />
      {error && <p className="text-[11px] text-[#C8332B] mt-1">{error}</p>}
    </div>
  );
};
