import React, { useEffect, useState } from 'react';
import { ChevronLeft, FileVideo, FolderOpen, Plus, X } from 'lucide-react';
import { JobSettings } from '../../types/models';
import { getBackendApi } from '../../api/pywebview';

export interface AddReservationViewProps {
  initialVideos?: string[];
  defaultOutputRoot: string;
  defaultSettings: Partial<JobSettings>;
  onCancel: () => void;
  onSubmit: (
    videos: string[],
    outputFolder: string,
    isMulti: boolean
  ) => Promise<boolean>;
  onOpenBasicSettings: () => void;
}

const joinOutputPath = (baseRoot: string, leaf: string): string => {
  const cleanRoot = (baseRoot || '').replace(/[\\/]+$/, '');
  if (!cleanRoot) return leaf;
  const sep = cleanRoot.includes('/') && !cleanRoot.includes('\\') ? '/' : '\\';
  return `${cleanRoot}${sep}${leaf}`;
};

export const AddReservationView: React.FC<AddReservationViewProps> = ({
  initialVideos = [],
  defaultOutputRoot,
  defaultSettings,
  onCancel,
  onSubmit,
  onOpenBasicSettings,
}) => {
  const [videos, setVideos] = useState<string[]>(initialVideos);
  const [singleDest, setSingleDest] = useState<string>('');
  const [parentRoot, setParentRoot] = useState<string>(defaultOutputRoot);
  const [parentRootTouched, setParentRootTouched] = useState<boolean>(false);
  const [previewNames, setPreviewNames] = useState<Record<string, string>>({});
  const [customDestTouched, setCustomDestTouched] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const isMulti = videos.length > 1;

  // Keep default output root synced until edited
  useEffect(() => {
    if (!parentRootTouched) {
      setParentRoot(defaultOutputRoot);
    }
  }, [defaultOutputRoot, parentRootTouched]);

  // Merge newly dropped initialVideos when already inside AddReservationView
  useEffect(() => {
    if (initialVideos && initialVideos.length > 0) {
      setVideos((prev) => Array.from(new Set([...prev, ...initialVideos])));
    }
  }, [initialVideos]);

  // Auto-sync singleDest when 1 video is present, or clear when empty
  useEffect(() => {
    if (videos.length === 0) {
      if (!customDestTouched) {
        setSingleDest('');
      }
      return;
    }
    if (videos.length === 1 && !customDestTouched) {
      const v = videos[0];
      const name = v.split('\\').pop() || v.split('/').pop() || '';
      const stem = name.replace(/\.[^/.]+$/, '');
      setSingleDest(joinOutputPath(parentRoot, stem));
    }
  }, [videos, parentRoot, customDestTouched]);

  // Fetch output preview names when singleDest changes, or clear when invalid
  useEffect(() => {
    if (!isMulti && singleDest) {
      const api = getBackendApi();
      if (api && api.get_output_preview_names) {
        api.get_output_preview_names(singleDest).then((names) => {
          if (names) setPreviewNames(names);
        });
      }
    } else {
      setPreviewNames({});
    }
  }, [singleDest, isMulti]);

  const handleSelectVideos = async () => {
    const api = getBackendApi();
    try {
      const selected = await api.select_video_files();
      if (selected && selected.length > 0) {
        setVideos((prev) => Array.from(new Set([...prev, ...selected])));
      }
    } catch (err) {
      console.error('Error selecting video files:', err);
    }
  };

  const handleClearVideos = () => {
    setVideos([]);
    setSingleDest('');
    setPreviewNames({});
    setCustomDestTouched(false);
  };

  const handleRemoveVideo = (index: number) => {
    setVideos((prev) => {
      const next = prev.filter((_, idx) => idx !== index);
      if (next.length <= 1) {
        setCustomDestTouched(false);
        if (next.length === 0) {
          setSingleDest('');
          setPreviewNames({});
        }
      }
      return next;
    });
  };

  const handleBrowseDestination = async () => {
    const api = getBackendApi();
    try {
      const dir = await api.select_directory(
        isMulti ? '出力親フォルダーを選択' : '出力先フォルダーを選択'
      );
      if (dir) {
        if (isMulti) {
          setParentRoot(dir);
          setParentRootTouched(true);
        } else {
          setSingleDest(dir);
          setCustomDestTouched(true);
        }
      }
    } catch (err) {
      console.error('Error selecting directory:', err);
    }
  };

  const handleSubmit = async () => {
    if (videos.length === 0 || isSubmitting) return;
    setIsSubmitting(true);
    const targetFolder = isMulti ? parentRoot : singleDest;
    const success = await onSubmit(
      videos,
      targetFolder,
      isMulti
    );
    setIsSubmitting(false);
    if (!success) {
      console.error('Failed to submit reservations');
    }
  };

  // Drag and drop into file list section
  const handleDropFiles = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv', '.webm'];
    const paths: string[] = [];
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      for (let i = 0; i < e.dataTransfer.files.length; i++) {
        const file = e.dataTransfer.files[i];
        const path = (file as any).pywebviewFullPath || (file as any).path || '';
        const ext = path ? '.' + path.split('.').pop()?.toLowerCase() : '';
        if (path && videoExts.includes(ext)) {
          paths.push(path);
        }
      }
    }
    if (paths.length > 0) {
      setVideos((prev) => Array.from(new Set([...prev, ...paths])));
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-white select-none">
      {/* Header Bar */}
      <div className="h-14 px-5 border-b border-[#D4DFDC] flex items-center gap-3 bg-[#F8FAFA] flex-shrink-0">
        <button
          onClick={onCancel}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded-lg border border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] bg-white transition-colors cursor-pointer"
        >
          <ChevronLeft className="w-4 h-4" />
          <span>予約リストへ戻る</span>
        </button>
        <h2 className="text-base font-bold text-[#1E293B]">予約を追加</h2>
      </div>

      {/* Main Form Scroll Area */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {/* Section 1: 入力ファイルの選択 */}
        <section
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDropFiles}
          className="bg-white rounded-lg border border-[#D4DFDC] p-4 shadow-xs"
        >
          <div className="flex items-center justify-between mb-2">
            <div>
              <h3 className="text-sm font-bold text-[#1E293B]">1. 入力ファイルの選択</h3>
              <p className="text-xs text-[#64748B] mt-0.5">
                解析したい動画ファイルを選択してください（複数まとめて選択・ドロップも可能）。
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSelectVideos}
                className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold bg-[#E4F3F0] hover:bg-[#D0EBE6] text-[#0B534D] border border-[#B5DDD6] rounded-lg transition-colors cursor-pointer"
              >
                <FolderOpen className="w-3.5 h-3.5" />
                <span>動画ファイルを選択…</span>
              </button>
              {videos.length > 0 && (
                <button
                  onClick={handleClearVideos}
                  className="px-2.5 py-1.5 text-xs font-medium text-[#64748B] hover:text-[#C8332B] transition-colors cursor-pointer"
                >
                  選択をクリア
                </button>
              )}
            </div>
          </div>

          {/* Video List Box */}
          <div className="mt-3 bg-[#F8FAFA] border border-[#D4DFDC] rounded-lg p-2.5 min-h-[90px] max-h-48 overflow-y-auto">
            {videos.length === 0 ? (
              <div className="h-20 flex flex-col items-center justify-center text-xs text-[#94A3B8]">
                <span>動画がまだ選択されていません。</span>
                <span>「動画ファイルを選択…」またはドラッグ＆ドロップで追加してください。</span>
              </div>
            ) : (
              <div className="space-y-1.5">
                {videos.map((vid, idx) => {
                  const filename = vid.split('\\').pop() || vid.split('/').pop() || vid;
                  const parentDir = vid.substring(0, vid.length - filename.length);
                  return (
                    <div
                      key={idx}
                      className="flex items-center justify-between bg-white border border-[#E2E8F0] rounded px-3 py-1.5 text-xs"
                    >
                      <div className="flex items-center gap-2 min-w-0 pr-2">
                        <span className="font-bold text-[#64748B] w-5 text-right">{idx + 1}.</span>
                        <FileVideo className="w-3.5 h-3.5 text-[#0F766E] flex-shrink-0" />
                        <span className="font-bold text-[#1E293B] truncate" title={vid}>
                          {filename}
                        </span>
                        <span className="text-[10px] text-[#94A3B8] truncate" title={parentDir}>
                          ({parentDir})
                        </span>
                      </div>
                      <button
                        onClick={() => handleRemoveVideo(idx)}
                        className="text-[#C8332B] hover:bg-[#FEF2F2] p-1 rounded transition-colors cursor-pointer flex-shrink-0"
                        title="除外"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {/* Section 2: 出力先フォルダーの設定 */}
        <section className="bg-white rounded-lg border border-[#D4DFDC] p-4 shadow-xs">
          <h3 className="text-sm font-bold text-[#1E293B]">2. 出力先フォルダーの設定</h3>
          <p className="text-xs text-[#64748B] mt-0.5">
            解析結果（骨格動画・crop動画2本・CSV・メタデータ）の保存先を指定します。
          </p>

          <div className="mt-3">
            {!isMulti ? (
              /* Single Video Mode */
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-bold text-[#475569] mb-1">
                    出力先フォルダー（フォルダー名から出力ファイル名を自動生成します）
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={singleDest}
                      onChange={(e) => {
                        setSingleDest(e.target.value);
                        setCustomDestTouched(true);
                      }}
                      placeholder="C:\...\出力先フォルダー"
                      className="flex-1 h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg focus:border-[#0F766E] focus:outline-none bg-white font-mono"
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

                {/* Auto-generated names preview */}
                <div className="bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2.5 text-xs text-[#0F766E]">
                  <span className="font-bold text-[#475569] block mb-1">
                    自動生成される出力ファイル:
                  </span>
                  <div className="font-mono text-[11px] space-y-0.5">
                    <div>・ 骨格動画: {previewNames.OUTPUT_VIDEO_NAME || '自動生成'}</div>
                    <div>・ 骨格なしcrop動画: {previewNames.OUTPUT_CROP_VIDEO_NAME || '自動生成'}</div>
                    <div>・ 骨格ありcrop動画: {previewNames.OUTPUT_CROP_SKELETON_VIDEO_NAME || '自動生成'}</div>
                    <div>・ CSVデータ: {previewNames.OUTPUT_CSV_NAME || '自動生成'}</div>
                    <div>・ NPZデータ: {previewNames.OUTPUT_NPZ_NAME || '自動生成'}</div>
                    <div>・ メタデータ(TXT): {previewNames.OUTPUT_METADATA_NAME || '自動生成'}</div>
                    <div>・ メタデータ(JSON): {previewNames.OUTPUT_METADATA_JSON_NAME || '自動生成'}</div>
                  </div>
                </div>
              </div>
            ) : (
              /* Multi Video Mode */
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-bold text-[#475569] mb-1">
                    出力親フォルダー（この中に動画ごとのサブフォルダーを自動作成します）
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={parentRoot}
                      onChange={(e) => {
                        setParentRoot(e.target.value);
                        setParentRootTouched(true);
                      }}
                      placeholder="出力親フォルダーのパス"
                      className="flex-1 h-9 px-3 text-xs border border-[#CBD5E1] rounded-lg focus:border-[#0F766E] focus:outline-none bg-white font-mono"
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

                {/* Subfolder list preview */}
                <div className="bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2.5 text-xs">
                  <span className="font-bold text-[#475569] block mb-1">
                    作成されるサブフォルダー（最大5件表示）:
                  </span>
                  <div className="font-mono text-[11px] text-[#0F766E] space-y-0.5">
                    {videos.slice(0, 5).map((v, i) => {
                      const name = v.split('\\').pop() || v.split('/').pop() || '';
                      const stem = name.replace(/\.[^/.]+$/, '');
                      return (
                        <div key={i} className="truncate">
                          ・ {name} → {joinOutputPath(parentRoot, stem)}
                        </div>
                      );
                    })}
                    {videos.length > 5 && (
                      <div className="text-[#94A3B8] italic pt-0.5">
                        … ほか {videos.length - 5} 件（重複時は自動で連番が付きます）
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Section 3: 設定スナップショット情報 */}
        <section className="bg-[#EBF0EE] border border-[#D4DFDC] rounded-lg p-4 flex items-center justify-between">
          <div className="text-xs text-[#1E293B]">
            <div className="font-bold text-[#0B534D] mb-0.5">適用される初期設定:</div>
            <div className="font-mono text-[#475569]">
              姿勢推定=
              {(defaultSettings.POSE_ENGINE || 'rtmpose') === 'vitpose'
                ? `ViTPose++-${String(defaultSettings.VITPOSE_MODEL || 'h').toUpperCase()} (${defaultSettings.VITPOSE_INPUT_SIZE || '256x192'})`
                : `RTMPose-${defaultSettings.RTMLIB_POSE_MODEL || 'x'} (${defaultSettings.RTMLIB_POSE_INPUT_SIZE || '384x288'})`}{' '}
              / YOLO=
              {(defaultSettings.YOLO_MODEL || 'yolo11m.pt').replace(/^yolo11|\.pt$/g, '')} / デバイス=
              {defaultSettings.DEVICE || 'auto'}
            </div>
            <div className="text-[10px] text-[#64748B] mt-1">
              ※ リストへ追加したあとでも、各行の「設定」ボタンから動画ごとに変更できます。
            </div>
          </div>
          <button
            onClick={onOpenBasicSettings}
            className="px-3.5 py-1.5 text-xs font-bold rounded-lg border border-[#B2C4BE] text-[#1E293B] hover:bg-white bg-white/70 transition-colors cursor-pointer flex-shrink-0"
          >
            基本設定を確認
          </button>
        </section>
      </div>

      {/* Footer Action Bar */}
      <div className="h-16 px-6 bg-[#F8FAFA] border-t border-[#D4DFDC] flex items-center justify-between flex-shrink-0">
        <button
          onClick={onCancel}
          disabled={isSubmitting}
          className="px-5 h-10 text-xs font-bold rounded-lg border border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] bg-white transition-colors cursor-pointer"
        >
          キャンセル
        </button>

        <button
          onClick={handleSubmit}
          disabled={videos.length === 0 || isSubmitting}
          className={`flex items-center gap-2 px-6 h-10 rounded-lg font-bold text-sm transition-all ${
            videos.length > 0 && !isSubmitting
              ? 'bg-[#0F766E] hover:bg-[#115E59] active:bg-[#0B534D] text-white shadow-sm cursor-pointer'
              : 'bg-[#E2E8F0] text-[#94A3B8] cursor-not-allowed shadow-none'
          }`}
        >
          <Plus className="w-4 h-4" />
          <span>{isSubmitting ? '登録中...' : '予約リストに追加する'}</span>
        </button>
      </div>
    </div>
  );
};
