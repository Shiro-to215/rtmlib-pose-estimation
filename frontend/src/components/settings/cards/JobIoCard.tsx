import React, { useEffect, useState } from 'react';
import { FolderOpen } from 'lucide-react';
import { ReservationJob } from '../../../types/models';
import { getBackendApi } from '../../../api/pywebview';

export interface JobIoCardProps {
  job: ReservationJob;
  destination: string;
  onChangeDestination: (path: string) => void;
  resetFailed: boolean;
  onChangeResetFailed: (val: boolean) => void;
}

export const JobIoCard: React.FC<JobIoCardProps> = ({
  job,
  destination,
  onChangeDestination,
  resetFailed,
  onChangeResetFailed,
}) => {
  const [previewNames, setPreviewNames] = useState<Record<string, string>>({});

  useEffect(() => {
    if (destination) {
      const api = getBackendApi();
      if (api && api.get_output_preview_names) {
        api.get_output_preview_names(destination).then((names) => {
          if (names) setPreviewNames(names);
        });
      }
    }
  }, [destination]);

  const handleBrowseDestination = async () => {
    const api = getBackendApi();
    try {
      const dir = await api.select_directory('この予約の出力先フォルダーを選択');
      if (dir) {
        onChangeDestination(dir);
      }
    } catch (err) {
      console.error('Error selecting directory:', err);
    }
  };

  return (
    <div className="bg-white rounded-[14px] p-5 space-y-3 select-none">
      {/* Target Video Path */}
      <div className="text-xs truncate">
        <span className="text-[#71717A]">対象動画: </span>
        <span className="font-medium text-[#111111] font-mono">{job.video_path}</span>
      </div>

      {/* Output Destination Folder */}
      <div>
        <label className="block text-xs font-semibold text-[#111111] mb-1.5">
          この予約の出力先フォルダー
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={destination}
            onChange={(e) => onChangeDestination(e.target.value)}
            placeholder="C:\...\出力先フォルダー"
            className="flex-1 min-w-0 h-9 px-3 text-xs font-mono rounded-[6px] bg-[#F4F5F6] border border-black/[0.08] text-[#111111] placeholder:text-[#A1A1AA] focus:bg-white focus:border-[#111111] focus:outline-none select-text"
          />
          <button
            type="button"
            onClick={handleBrowseDestination}
            className="h-9 px-3 text-xs font-medium bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] rounded-[6px] transition-colors cursor-pointer inline-flex items-center gap-1.5 flex-shrink-0"
          >
            <FolderOpen className="w-3.5 h-3.5 text-[#52525B]" strokeWidth={1.6} />
            <span>参照…</span>
          </button>
        </div>
      </div>

      {/* Live Output Preview */}
      <div className="bg-[#F4F5F6] border border-black/[0.06] rounded-[6px] p-3 text-[11px] font-mono text-[#52525B] space-y-0.5">
        <span className="font-medium text-[#111111] block font-sans text-xs mb-1">
          生成ファイル名プレビュー
        </span>
        <div>骨格動画: {previewNames.OUTPUT_VIDEO_NAME || `${job.output_folder}.mp4`}</div>
        <div>骨格なしcrop動画: {previewNames.OUTPUT_CROP_VIDEO_NAME || `${job.output_folder}-crop.mp4`}</div>
        <div>骨格ありcrop動画: {previewNames.OUTPUT_CROP_SKELETON_VIDEO_NAME || `${job.output_folder}-crop-skeleton.mp4`}</div>
        <div>CSVデータ: {previewNames.OUTPUT_CSV_NAME || `${job.output_folder}.csv`}</div>
        <div>NPZデータ: {previewNames.OUTPUT_NPZ_NAME || `${job.output_folder}.npz`}</div>
        <div>メタデータ(TXT): {previewNames.OUTPUT_METADATA_NAME || `${job.output_folder}_metadata.txt`}</div>
        <div>メタデータ(JSON): {previewNames.OUTPUT_METADATA_JSON_NAME || `${job.output_folder}_metadata.json`}</div>
      </div>

      {/* Failed Job Reset Checkbox */}
      {job.state === 'failed' && (
        <div className="pt-1">
          <label className="flex items-center gap-2 text-xs font-medium text-[#B91C1C] cursor-pointer">
            <input
              type="checkbox"
              checked={resetFailed}
              onChange={(e) => onChangeResetFailed(e.target.checked)}
              className="w-4 h-4 rounded accent-[#111111] cursor-pointer"
            />
            <span>保存時に「失敗」状態を解除して「待機中」に戻す</span>
          </label>
        </div>
      )}
    </div>
  );
};
