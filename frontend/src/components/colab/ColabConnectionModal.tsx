import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  Cloud,
  Eye,
  EyeOff,
  Loader2,
  RefreshCw,
  X,
} from 'lucide-react';
import { ColabConfig, ColabHealthInfo, ExecutionTarget } from '../../types/models';

export interface ColabConnectionModalProps {
  isOpen: boolean;
  config: ColabConfig;
  isProcessing: boolean;
  onClose: () => void;
  onTestConnection: (
    serverUrl: string,
    apiToken: string
  ) => Promise<{ ok: boolean; health?: ColabHealthInfo; error?: string }>;
  onSave: (
    nextConfig: Partial<ColabConfig>
  ) => Promise<{ status: string; config?: ColabConfig; message?: string }>;
}

export const ColabConnectionModal: React.FC<ColabConnectionModalProps> = ({
  isOpen,
  config,
  isProcessing,
  onClose,
  onTestConnection,
  onSave,
}) => {
  const [executionTarget, setExecutionTarget] = useState<ExecutionTarget>(
    config.execution_target || 'local'
  );
  const [serverUrl, setServerUrl] = useState<string>(config.server_url || '');
  const [apiToken, setApiToken] = useState<string>(config.api_token || '');
  const [rememberToken, setRememberToken] = useState<boolean>(Boolean(config.remember_token));
  const [showToken, setShowToken] = useState<boolean>(false);
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    health?: ColabHealthInfo;
    error?: string;
  } | null>(config.last_health ? { ok: true, health: config.last_health } : null);
  const [formError, setFormError] = useState<string | null>(null);
  const wasOpenRef = useRef<boolean>(false);

  // Sync local form inputs ONLY when the modal transitions from closed -> open
  // so clicking "接続テスト" never resets unsaved edits via config.last_health updates.
  useEffect(() => {
    const justOpened = isOpen && !wasOpenRef.current;
    wasOpenRef.current = isOpen;
    if (justOpened) {
      setExecutionTarget(config.execution_target || 'local');
      setServerUrl(config.server_url || '');
      setApiToken(config.api_token || '');
      setRememberToken(Boolean(config.remember_token));
      setTestResult(config.last_health ? { ok: true, health: config.last_health } : null);
      setFormError(null);
    }
  }, [isOpen, config]);

  if (!isOpen) return null;

  const hasUnsavedUrlOrToken =
    serverUrl.trim() !== (config.server_url || '').trim() ||
    apiToken.trim() !== (config.api_token || '').trim();

  const handleTest = async () => {
    setFormError(null);
    if (!apiToken.trim()) {
      setTestResult({
        ok: false,
        error: 'API トークンが入力されていません。Colab セル 4 に出力されたトークンを入力してください。',
      });
      return;
    }
    setIsTesting(true);
    try {
      const res = await onTestConnection(serverUrl.trim(), apiToken.trim());
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ ok: false, error: err?.message || '接続テストに失敗しました。' });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSave = async () => {
    setFormError(null);
    setIsSaving(true);
    try {
      const res = await onSave({
        execution_target: executionTarget,
        server_url: serverUrl.trim(),
        api_token: apiToken.trim(),
        remember_token: rememberToken,
      });
      if (res && res.status === 'ok') {
        onClose();
      } else {
        setFormError(res?.message || '設定の保存に失敗しました。');
      }
    } catch (err: any) {
      setFormError(err?.message || '設定の保存に失敗しました。');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[1px] p-4 select-none"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-white rounded-xl border border-[#D4DFDC] shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-3.5 bg-[#F8FAFC] border-b border-[#E2E8F0] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cloud className="w-5 h-5 text-[#0F766E]" />
            <h2 className="text-base font-bold text-[#1E293B]">Google Colab 接続設定</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[#64748B] hover:bg-[#E2E8F0] hover:text-[#1E293B] transition-colors cursor-pointer"
            aria-label="閉じる"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <div className="p-5 space-y-4">
          <p className="text-xs text-[#475569] leading-relaxed">
            Colab ノートブック（<code>launch_colab_server.ipynb</code>）の出力に表示された公開 URL と
            API トークンを入力してください。推論のみを Colab GPU で実行し、3 本の MP4 動画は手元の PC で並列生成します。
          </p>

          {/* Execution target selector */}
          <div>
            <label className="block text-xs font-bold text-[#334155] mb-1.5">
              実行先モード
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => setExecutionTarget('local')}
                className={`py-2 px-3 rounded-lg border text-xs font-bold transition-all cursor-pointer ${
                  executionTarget === 'local'
                    ? 'bg-[#E2F2EE] border-[#0F766E] text-[#0B534D]'
                    : 'bg-white border-[#CBD5E1] text-[#475569] hover:bg-[#F8FAFC]'
                } ${isProcessing ? 'opacity-60 cursor-not-allowed' : ''}`}
              >
                ローカル PC
              </button>
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => setExecutionTarget('colab')}
                className={`py-2 px-3 rounded-lg border text-xs font-bold transition-all cursor-pointer ${
                  executionTarget === 'colab'
                    ? 'bg-[#E2F2EE] border-[#0F766E] text-[#0B534D]'
                    : 'bg-white border-[#CBD5E1] text-[#475569] hover:bg-[#F8FAFC]'
                } ${isProcessing ? 'opacity-60 cursor-not-allowed' : ''}`}
              >
                Google Colab GPU
              </button>
            </div>
          </div>

          {/* Server URL */}
          <div>
            <label className="block text-xs font-bold text-[#334155] mb-1">
              サーバー URL（Cloudflare Quick Tunnel / カスタム URL）
            </label>
            <input
              type="url"
              value={serverUrl}
              onChange={(e) => {
                setServerUrl(e.target.value);
                setTestResult(null);
              }}
              placeholder="https://xxxx-xxxx.trycloudflare.com"
              className="w-full px-3 py-2 text-xs font-mono border border-[#CBD5E1] rounded-lg focus:outline-none focus:border-[#0F766E] select-text"
            />
          </div>

          {/* API Token */}
          <div>
            <label className="block text-xs font-bold text-[#334155] mb-1">
              API トークン
            </label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={apiToken}
                onChange={(e) => {
                  setApiToken(e.target.value);
                  setTestResult(null);
                }}
                placeholder="ノートブックセル4に出力されたトークン"
                className="w-full pl-3 pr-9 py-2 text-xs font-mono border border-[#CBD5E1] rounded-lg focus:outline-none focus:border-[#0F766E] select-text"
              />
              <button
                type="button"
                onClick={() => setShowToken((prev) => !prev)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#64748B] hover:text-[#1E293B] cursor-pointer p-1"
                title={showToken ? 'トークンを隠す' : 'トークンを表示'}
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <label className="mt-2 inline-flex items-center gap-2 text-xs text-[#475569] cursor-pointer">
              <input
                type="checkbox"
                checked={rememberToken}
                onChange={(e) => setRememberToken(e.target.checked)}
                className="rounded border-[#CBD5E1] text-[#0F766E]"
              />
              <span>次回起動用にもローカル設定へトークンを保持する</span>
            </label>
          </div>

          {/* Connection Test Action + Status Card */}
          <div className="pt-1">
            <button
              type="button"
              onClick={handleTest}
              disabled={isTesting || !serverUrl.trim()}
              className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold border transition-all ${
                isTesting || !serverUrl.trim()
                  ? 'bg-[#F1F5F9] border-[#E2E8F0] text-[#94A3B8] cursor-not-allowed'
                  : 'bg-white border-[#B2C4BE] text-[#0F766E] hover:bg-[#F0FDF9] cursor-pointer'
              }`}
            >
              {isTesting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RefreshCw className="w-3.5 h-3.5" />
              )}
              <span>{isTesting ? '接続テスト中...' : '接続テスト (/health)'}</span>
            </button>

            {testResult && (
              <div
                className={`mt-2.5 p-3 rounded-lg border text-xs ${
                  testResult.ok
                    ? 'bg-[#F0FDF4] border-[#BBF7D0] text-[#166534]'
                    : 'bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]'
                }`}
              >
                {testResult.ok && testResult.health ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 font-bold">
                      <CheckCircle className="w-4 h-4 flex-shrink-0" />
                      <span>
                        接続成功 ({testResult.health.gpu_name || 'GPU情報取得済'})
                        {testResult.health.latency_ms ? ` · ${testResult.health.latency_ms} ms` : ''}
                      </span>
                    </div>
                    <div className="text-[11px] pl-5 text-[#15803D]">
                      VRAM: {testResult.health.vram_free_gb ?? '?'} / {testResult.health.vram_total_gb ?? '?'} GB
                      {' · '}
                      RAM空き: {testResult.health.ram_available_gb ?? '?'} / {testResult.health.ram_total_gb ?? '?'} GB
                      {' · '}
                      ワーカー: {testResult.health.worker_ready ? '待機完了' : '初期化中'}
                    </div>
                    {hasUnsavedUrlOrToken && (
                      <div className="text-[11px] pl-5 font-bold text-[#0F766E]">
                        ※ まだ保存されていません。右下の「保存して反映」を押して確定してください。
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-start gap-1.5">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <span className="break-all">{testResult.error || '接続できませんでした。'}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {formError && (
            <div className="p-2.5 rounded-lg bg-[#FEF2F2] border border-[#FECACA] text-xs text-[#B91C1C]">
              {formError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-[#F8FAFC] border-t border-[#E2E8F0] flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-xs font-bold text-[#475569] hover:bg-[#E2E8F0] transition-colors cursor-pointer"
          >
            キャンセル
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="px-5 py-2 rounded-lg text-xs font-bold bg-[#0F766E] hover:bg-[#115E59] text-white transition-colors shadow-xs cursor-pointer disabled:opacity-60"
          >
            {isSaving ? '保存中...' : '保存して反映'}
          </button>
        </div>
      </div>
    </div>
  );
};
