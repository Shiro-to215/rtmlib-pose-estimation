declare module 'lucide-react' {
  import React from 'react';
  export interface LucideProps extends React.SVGProps<SVGSVGElement> {
    size?: string | number;
    color?: string;
    strokeWidth?: string | number;
  }
  export type LucideIcon = React.FC<LucideProps>;
  export const Play: LucideIcon;
  export const Square: LucideIcon;
  export const Settings: LucideIcon;
  export const Trash2: LucideIcon;
  export const ArrowUp: LucideIcon;
  export const ArrowDown: LucideIcon;
  export const Plus: LucideIcon;
  export const Check: LucideIcon;
  export const X: LucideIcon;
  export const RefreshCw: LucideIcon;
  export const FolderOpen: LucideIcon;
  export const FileVideo: LucideIcon;
  export const AlertCircle: LucideIcon;
  export const AlertTriangle: LucideIcon;
  export const Info: LucideIcon;
  export const CheckCircle: LucideIcon;
  export const Eye: LucideIcon;
  export const Edit: LucideIcon;
  export const ChevronDown: LucideIcon;
  export const ChevronRight: LucideIcon;
  export const ChevronLeft: LucideIcon;
  export const HelpCircle: LucideIcon;
  export const ExternalLink: LucideIcon;
  export const RotateCcw: LucideIcon;
  export const Film: LucideIcon;
  export const Pause: LucideIcon;
  export const Search: LucideIcon;
  export const Sliders: LucideIcon;
  export const SlidersHorizontal: LucideIcon;
  export const FileText: LucideIcon;
  export const CheckSquare: LucideIcon;
  export const Save: LucideIcon;
  export const Cpu: LucideIcon;
  export const Sparkles: LucideIcon;
}
