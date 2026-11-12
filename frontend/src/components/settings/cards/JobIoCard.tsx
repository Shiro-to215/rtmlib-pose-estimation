import React, { useEffect, useState } from 'react';
import { FolderOpen } from 'lucide-react';
import { ReservationJob } from '../../../types/models';
import { getBackendApi } from '../../../api/pywebview';

export interface JobIoCardProps {
  job: ReservationJob;
  destination: string;
  onChangeDestination: (path: string) => void;
  thumbnail: string;
  onChangeThumbnail: (path: string) => void;
  resetFailed: boolean;
  onChangeResetFailed: (val: boolean) => void;
}

export const JobIoCard: React.FC<JobIoCardProps> = ({
  job,
  destination,
  onChangeDestination,
  thumbnail,
  onChangeThumbnail,
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

  const handleBrowseThumbnail = async () => {
    const api = getBackendApi();
    try {
      const img = await api.select_image_file('撮影日時取得用サムネイル画像を選択');
      if (img) {
        onChangeThumbnail(img);
      }
    } catch (err) {
      console.error('Error selecting thumbnail:', err);
    }
  };

  return (
    <div className="bg-[#F8FAFA] border border-[#D4DFDC] rounded-lg p-4 mb-4 space-y-3 select-none">
      {/* Target Video Path */}
      <div className="text-xs">
        <span className="text-[#64748B]">対象動画: </span>
        <span className="font-bold text-[#1E293B] font-mono">{job.video_path}</span>
      </div>

      {/* Output Destination Folder */}
      <div>
        <label className="block text-xs font-bold text-[#475569] mb-1">
          この予約の出力先フォルダー
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={destination}
            onChange={(e) => onChangeDestination(e.target.value)}
            placeholder="C:\...\出力先フォルダー"
            className="flex-1 h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg bg-white text-[#1E293B] font-mono focus:border-[#0F766E] focus:outline-none"
          />
          <button
            onClick={handleBrowseDestination}
            className="px-3.5 h-9 text-xs font-bold bg-[#EBF0EE] hover:bg-[#E2EBE8] text-[#1E293B] border border-[#CBD5E1] rounded-lg transition-colors cursor-pointer flex items-center gap-1"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            <span>参照…</span>
          </button>
        </div>
      </div>

      {/* Live Output Preview */}
      <div className="bg-white border border-[#CBD5E1] rounded-lg p-2.5 text-[11px] font-mono text-[#0F766E] space-y-0.5">
        <span className="font-bold text-[#475569] block font-sans text-xs mb-1">
          生成ファイル名プレビュー:
        </span>
        <div>・ 骨格動画: {previewNames.OUTPUT_VIDEO_NAME || `${job.output_folder}.mp4`}</div>
        <div>・ 骨格なしcrop動画: {previewNames.OUTPUT_CROP_VIDEO_NAME || `${job.output_folder}-crop.mp4`}</div>
        <div>・ 骨格ありcrop動画: {previewNames.OUTPUT_CROP_SKELETON_VIDEO_NAME || `${job.output_folder}-crop-skeleton.mp4`}</div>
        <div>・ CSVデータ: {previewNames.OUTPUT_CSV_NAME || `${job.output_folder}.csv`}</div>
        <div>・ メタデータ: {previewNames.OUTPUT_METADATA_NAME || `${job.output_folder}_metadata.txt`}</div>
      </div>

      {/* Optional Thumbnail Image */}
      <div>
        <label className="block text-xs font-bold text-[#475569] mb-1">
          撮影日時取得用サムネイル画像（任意）
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={thumbnail}
            onChange={(e) => onChangeThumbnail(e.target.value)}
            placeholder="任意（空欄の場合は動画ファイルから生成）"
            className="flex-1 h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg bg-white text-[#1E293B] font-mono focus:border-[#0F766E] focus:outline-none"
          />
          <button
            onClick={handleBrowseThumbnail}
            className="px-3 h-9 text-xs font-bold bg-[#EBF0EE] hover:bg-[#E2EBE8] text-[#1E293B] border border-[#CBD5E1] rounded-lg transition-colors cursor-pointer flex items-center gap-1"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            <span>参照…</span>
          </button>
          {thumbnail && (
            <button
              onClick={() => onChangeThumbnail('')}
              className="px-2.5 h-9 text-xs text-[#64748B] hover:text-[#C8332B] transition-colors cursor-pointer"
            >
              クリア
            </button>
          )}
        </div>
      </div>

      {/* Failed Job Reset Checkbox */}
      {job.state === 'failed' && (
        <div className="pt-1">
          <label className="flex items-center gap-2 text-xs font-bold text-[#C8332B] cursor-pointer">
            <input
              type="checkbox"
              checked={resetFailed}
              onChange={(e) => onChangeResetFailed(e.target.checked)}
              className="w-4 h-4 rounded text-[#0F766E] focus:ring-[#0F766E] cursor-pointer"
            />
            <span>保存時に「失敗」状態を解除して「待機中」に戻す</span>
          </label>
        </div>
      )}
    </div>
  );
};
