import React, { useEffect, useState } from 'react';

export interface TagListInputProps {
  label: string;
  value: number[];
  onChange: (val: number[]) => void;
  description?: string;
  error?: string;
  className?: string;
}

const parseTagList = (raw: string): number[] =>
  raw
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => Number(s))
    .filter((n) => Number.isInteger(n) && n >= 0);

export const TagListInput: React.FC<TagListInputProps> = ({
  label,
  value,
  onChange,
  description,
  error,
  className = '',
}) => {
  const [text, setText] = useState<string>(value.join(', '));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) {
      setText(value.join(', '));
    } else if (JSON.stringify(parseTagList(text)) !== JSON.stringify(value)) {
      setText(value.join(', '));
    }
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    setText(raw);
    onChange(parseTagList(raw));
  };

  const handleBlur = () => {
    setFocused(false);
    setText(value.join(', '));
  };

  return (
    <div className={`py-2 ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-bold text-[#1E293B]">{label}</label>
      </div>
      {description && <p className="text-[11px] text-[#64748B] mb-1.5">{description}</p>}
      <input
        type="text"
        value={text}
        onChange={handleChange}
        onFocus={() => setFocused(true)}
        onBlur={handleBlur}
        placeholder="例: 0 (カンマ区切り)"
        className="w-full h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg bg-white text-[#1E293B] font-mono focus:border-[#0F766E] focus:outline-none"
      />
      {error && <p className="text-[11px] text-[#C8332B] mt-1">{error}</p>}
    </div>
  );
};
