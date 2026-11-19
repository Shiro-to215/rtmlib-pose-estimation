import React from 'react';

export interface ToggleSwitchProps {
  label: string;
  checked: boolean;
  onChange: (val: boolean) => void;
  description?: string;
  className?: string;
}

export const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  label,
  checked,
  onChange,
  description,
  className = '',
}) => {
  return (
    <div className={`flex items-center justify-between py-2 ${className}`}>
      <div className="flex-1 pr-4">
        <label
          className="text-xs font-semibold text-[#111111] cursor-pointer"
          onClick={() => onChange(!checked)}
        >
          {label}
        </label>
        {description && (
          <p className="text-[11px] text-[#71717A] mt-0.5 leading-snug">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-150 ease-out focus:outline-none focus:ring-2 focus:ring-[#111111] focus:ring-offset-1 ${
          checked ? 'bg-[#111111]' : 'bg-[#D4D6DA]'
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white transition duration-150 ease-out ${
            checked ? 'translate-x-5' : 'translate-x-0'
          }`}
        />
      </button>
    </div>
  );
};
