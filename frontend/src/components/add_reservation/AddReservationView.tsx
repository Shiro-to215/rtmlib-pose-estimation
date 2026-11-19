import React, { useEffect, useState } from 'react';
import { FileVideo, FolderOpen, Plus, X } from 'lucide-react';
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
    const success = await onSubmit(videos, targetFolder, isMulti);
    setIsSubmitting(false);
    if (!success) {
      console.error('Failed to submit reservations');
    }
  };

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

  const outputPreviewRows: Array<{ label: string; value: string }> = [
    { label: '骨格動画', value: previewNames.OUTPUT_VIDEO_NAME || '自動生成' },
    { label: '骨格なしcrop動画', value: previewNames.OUTPUT_CROP_VIDEO_NAME || '自動生成' },
    { label: '骨格ありcrop動画', value: previewNames.OUTPUT_CROP_SKELETON_VIDEO_NAME || '自動生成' },
    { label: 'CSVデータ', value: previewNames.OUTPUT_CSV_NAME || '自動生成' },
    { label: 'NPZデータ', value: previewNames.OUTPUT_NPZ_NAME || '自動生成' },
    { label: 'メタデータ(TXT)', value: previewNames.OUTPUT_METADATA_NAME || '自動生成' },
    { label: 'メタデータ(JSON)', value: previewNames.OUTPUT_METADATA_JSON_NAME || '自動生成' },
  ];

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden select-none">
      {/* Compact View Title Strip */}
      <div className="pb-3 flex items-center justify-between gap-4 flex-shrink-0">
        <div className="flex items-baseline gap-3 min-w-0">
          <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[#111111]">
            予約を追加
          </h2>
          <span className="text-xs text-[#71717A] tabular-nums">
            {videos.length > 0 ? `${videos.length}件の動画を選択中` : '動画と出力先を指定して待機リストへ登録'}
          </span>
        </div>
      </div>

      {/* Asymmetric 7 : 5 Bento Grid directly on #ECEEEF */}
      <div className="flex-1 min-h-0 grid grid-cols-12 gap-3">
        {/* Left Column (7 cols): Input Selection + Default Snapshot */}
        <div className="col-span-7 min-h-0 flex flex-col gap-3">
          {/* Card 1: 入力ファイルの選択 */}
          <section
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDropFiles}
            className="bg-white rounded-[14px] p-5 flex-1 min-h-0 flex flex-col"
          >
            <div className="flex items-start justify-between gap-3 flex-shrink-0">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-[#111111]">1. 入力ファイルの選択</h3>
                <p className="text-xs text-[#71717A] mt-0.5">
                  解析したい動画ファイルを選択してください（複数まとめて選択・ドロップも可能）。
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {videos.length > 0 && (
                  <button
                    type="button"
                    onClick={handleClearVideos}
                    className="h-8 px-2.5 rounded-[6px] text-xs font-medium text-[#71717A] hover:text-[#B91C1C] hover:bg-[#FEE2E2]/60 transition-colors cursor-pointer"
                  >
                    選択をクリア
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleSelectVideos}
                  className="h-8 px-3 rounded-[6px] bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] text-xs font-medium inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <FolderOpen className="w-3.5 h-3.5 text-[#52525B]" strokeWidth={1.6} />
                  <span>動画ファイルを選択…</span>
                </button>
              </div>
            </div>

            <div className="flex-1 min-h-0 mt-3 rounded-[6px] bg-[#F4F5F6] border border-black/[0.06] p-2.5 overflow-y-auto flex flex-col">
              {videos.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-6 text-xs text-[#71717A]">
                  <span className="font-medium text-[#52525B]">動画がまだ選択されていません</span>
                  <span className="text-[11px] text-[#A1A1AA] mt-1">
                    「動画ファイルを選択…」またはここへファイルをドラッグ＆ドロップしてください。
                  </span>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {videos.map((vid, idx) => {
                    const filename = vid.split('\\').pop() || vid.split('/').pop() || vid;
                    const parentDir = vid.substring(0, vid.length - filename.length);
                    return (
                      <div
                        key={idx}
                        className="flex items-center justify-between bg-white border border-black/[0.06] rounded-[6px] px-3 py-2 text-xs"
                      >
                        <div className="flex items-center gap-2 min-w-0 pr-2">
                          <span className="font-mono text-[11px] text-[#71717A] w-5 text-right tabular-nums flex-shrink-0">
                            {idx + 1}.
                          </span>
                          <FileVideo className="w-3.5 h-3.5 text-[#71717A] flex-shrink-0" strokeWidth={1.6} />
                          <span className="font-medium text-[#111111] truncate" title={vid}>
                            {filename}
                          </span>
                          <span className="text-[11px] text-[#71717A] font-mono truncate" title={parentDir}>
                            {parentDir}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleRemoveVideo(idx)}
                          className="p-1 rounded-[6px] text-[#71717A] hover:text-[#B91C1C] hover:bg-[#FEE2E2] transition-colors cursor-pointer flex-shrink-0"
                          title="除外"
                          aria-label="除外"
                        >
                          <X className="w-3.5 h-3.5" strokeWidth={1.6} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </section>

          {/* Card 3: 適用される初期設定 */}
          <section className="bg-white rounded-[14px] p-5 flex-shrink-0 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="text-xs font-semibold text-[#111111]">適用される初期設定</div>
              <div className="text-xs font-mono text-[#52525B] truncate mt-1">
                姿勢推定:{' '}
                {(defaultSettings.POSE_ENGINE || 'rtmpose') === 'vitpose'
                  ? `ViTPose++-${String(defaultSettings.VITPOSE_MODEL || 'h').toUpperCase()} (${defaultSettings.VITPOSE_INPUT_SIZE || '256x192'})`
                  : `RTMPose-${String(defaultSettings.RTMLIB_POSE_MODEL || 'x').toUpperCase()} (${defaultSettings.RTMLIB_POSE_INPUT_SIZE || '384x288'})`}{' '}
                / YOLO11-{(defaultSettings.YOLO_MODEL || 'yolo11m.pt').replace(/^yolo11|\.pt$/g, '')} / デバイス:{' '}
                {defaultSettings.DEVICE || 'auto'}
              </div>
              <div className="text-[11px] text-[#71717A] mt-1">
                登録後でも予約リスト各行の歯車アイコンから動画ごとに設定を変更できます。
              </div>
            </div>
            <button
              type="button"
              onClick={onOpenBasicSettings}
              className="h-8 px-3 rounded-[6px] bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] text-xs font-medium transition-colors cursor-pointer flex-shrink-0"
            >
              基本設定を確認
            </button>
          </section>
        </div>

        {/* Right Column (5 cols): Destination Settings + Primary Actions */}
        <div className="col-span-5 min-h-0 flex flex-col gap-3">
          {/* Card 2: 出力先フォルダーの設定 */}
          <section className="bg-white rounded-[14px] p-5 flex-1 min-h-0 flex flex-col">
            <div className="flex-shrink-0">
              <h3 className="text-sm font-semibold text-[#111111]">2. 出力先フォルダーの設定</h3>
              <p className="text-xs text-[#71717A] mt-0.5">
                解析結果（骨格動画・crop動画・CSV・メタデータ）の保存先を指定します。
              </p>
            </div>

            <div className="flex-1 min-h-0 flex flex-col mt-3">
              {!isMulti ? (
                <>
                  <div className="flex-shrink-0">
                    <label className="block text-xs font-medium text-[#52525B] mb-1.5">
                      出力先フォルダー（フォルダー名から出力ファイル名を自動生成）
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
                        className="flex-1 min-w-0 h-9 px-3 text-xs font-mono rounded-[6px] bg-[#F4F5F6] border border-black/[0.08] text-[#111111] placeholder:text-[#A1A1AA] focus:bg-white focus:border-[#111111] focus:outline-none select-text"
                      />
                      <button
                        type="button"
                        onClick={handleBrowseDestination}
                        className="h-9 px-3 rounded-[6px] bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] text-xs font-medium inline-flex items-center gap-1.5 transition-colors cursor-pointer flex-shrink-0"
                      >
                        <FolderOpen className="w-3.5 h-3.5 text-[#52525B]" strokeWidth={1.6} />
                        <span>参照…</span>
                      </button>
                    </div>
                  </div>

                  <div className="flex-1 min-h-0 mt-3 rounded-[6px] bg-[#F4F5F6] border border-black/[0.06] p-3.5 overflow-y-auto">
                    <div className="text-xs font-medium text-[#111111] mb-2">
                      自動生成される出力ファイル
                    </div>
                    <div className="space-y-1.5 font-mono text-[11px]">
                      {outputPreviewRows.map((row) => (
                        <div key={row.label} className="flex items-center justify-between gap-2 min-w-0">
                          <span className="text-[#71717A] font-sans flex-shrink-0">{row.label}</span>
                          <span className="text-[#52525B] truncate" title={row.value}>
                            {row.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex-shrink-0">
                    <label className="block text-xs font-medium text-[#52525B] mb-1.5">
                      出力親フォルダー（動画ごとのサブフォルダーを自動作成）
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
                        className="flex-1 min-w-0 h-9 px-3 text-xs font-mono rounded-[6px] bg-[#F4F5F6] border border-black/[0.08] text-[#111111] placeholder:text-[#A1A1AA] focus:bg-white focus:border-[#111111] focus:outline-none select-text"
                      />
                      <button
                        type="button"
                        onClick={handleBrowseDestination}
                        className="h-9 px-3 rounded-[6px] bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] text-xs font-medium inline-flex items-center gap-1.5 transition-colors cursor-pointer flex-shrink-0"
                      >
                        <FolderOpen className="w-3.5 h-3.5 text-[#52525B]" strokeWidth={1.6} />
                        <span>参照…</span>
                      </button>
                    </div>
                  </div>

                  <div className="flex-1 min-h-0 mt-3 rounded-[6px] bg-[#F4F5F6] border border-black/[0.06] p-3.5 overflow-y-auto">
                    <div className="text-xs font-medium text-[#111111] mb-2">
                      作成されるサブフォルダー（最大5件表示）
                    </div>
                    <div className="space-y-1.5 font-mono text-[11px] text-[#52525B]">
                      {videos.slice(0, 5).map((v, i) => {
                        const name = v.split('\\').pop() || v.split('/').pop() || '';
                        const stem = name.replace(/\.[^/.]+$/, '');
                        return (
                          <div key={i} className="truncate" title={joinOutputPath(parentRoot, stem)}>
                            <span className="text-[#71717A]">{name}</span> → {joinOutputPath(parentRoot, stem)}
                          </div>
                        );
                      })}
                      {videos.length > 5 && (
                        <div className="text-[#71717A] pt-1 font-sans">
                          ほか {videos.length - 5} 件（重複時は自動で連番が付きます）
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          </section>

          {/* Bottom-Right Action Row */}
          <div className="flex items-center justify-end gap-2.5 flex-shrink-0">
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              className="h-9 px-4 rounded-[6px] text-xs font-medium text-[#52525B] hover:text-[#111111] hover:bg-black/[0.05] transition-colors cursor-pointer"
            >
              キャンセル
            </button>

            <button
              type="button"
              onClick={handleSubmit}
              disabled={videos.length === 0 || isSubmitting}
              className={`h-9 px-5 rounded-[6px] text-xs font-semibold inline-flex items-center gap-1.5 transition-colors ${
                videos.length > 0 && !isSubmitting
                  ? 'bg-[#111111] hover:bg-[#27272A] text-white cursor-pointer'
                  : 'bg-[#D9DCE0] text-[#8E8E98] cursor-not-allowed'
              }`}
            >
              <Plus className="w-3.5 h-3.5" strokeWidth={1.8} />
              <span>{isSubmitting ? '登録中...' : '予約リストに追加する'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
