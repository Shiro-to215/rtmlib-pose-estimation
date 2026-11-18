import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Cloud,
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  Link2,
  Loader2,
  Play,
  RefreshCw,
  Settings,
  Square,
  X,
} from 'lucide-react';
import { getBackendApi } from '../../api/pywebview';
import {
  ColabCliPrereqs,
  ColabCliStatus,
  ColabConfig,
  ColabGpuType,
  ColabHealthInfo,
  ColabMode,
  ExecutionTarget,
} from '../../types/models';

const GPU_OPTIONS: Array<{ value: ColabGpuType; label: string; hint: string }> = [
  { value: 'T4', label: 'T4', hint: '標準・安定' },
  { value: 'L4', label: 'L4', hint: 'High-RAM固定' },
  { value: 'A100', label: 'A100', hint: '高VRAM・上位プラン' },
  { value: 'G4', label: 'G4', hint: '新世代・枠次第' },
  { value: 'H100', label: 'H100', hint: '最速・上位プラン' },
];

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
  onCliStatusChange?: (status: ColabCliStatus) => void;
}

export const ColabConnectionModal: React.FC<ColabConnectionModalProps> = ({
  isOpen,
  config,
  isProcessing,
  onClose,
  onTestConnection,
  onSave,
  onCliStatusChange,
}) => {
  const [executionTarget, setExecutionTarget] = useState<ExecutionTarget>(
    config.execution_target || 'local'
  );
  const [colabMode, setColabMode] = useState<ColabMode>(config.colab_mode || 'cli_ssh');

  // Manual URL/Token state
  const [serverUrl, setServerUrl] = useState<string>(config.server_url || '');
  const [apiToken, setApiToken] = useState<string>(config.api_token || '');
  const [rememberToken, setRememberToken] = useState<boolean>(Boolean(config.remember_token));
  const [showToken, setShowToken] = useState<boolean>(false);
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    health?: ColabHealthInfo;
    error?: string;
  } | null>(config.last_health ? { ok: true, health: config.last_health } : null);

  // CLI + SSH settings state
  const [cliGpu, setCliGpu] = useState<ColabGpuType>(config.cli_gpu || 'T4');
  const [cliHighMem, setCliHighMem] = useState<boolean>(Boolean(config.cli_high_mem));
  const [cliUseDriveCache, setCliUseDriveCache] = useState<boolean>(
    Boolean(config.cli_use_drive_cache)
  );
  const [cliIdleMinutes, setCliIdleMinutes] = useState<number>(
    Number(config.cli_idle_timeout_minutes ?? 30)
  );

  // CLI Setup & Runtime Live State
  const [prereqs, setPrereqs] = useState<ColabCliPrereqs | null>(null);
  const [isCheckingPrereqs, setIsCheckingPrereqs] = useState<boolean>(false);
  const [isInstallingCli, setIsInstallingCli] = useState<boolean>(false);
  const [isGeneratingKey, setIsGeneratingKey] = useState<boolean>(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [authCode, setAuthCode] = useState<string>('');
  const [isStartingAuth, setIsStartingAuth] = useState<boolean>(false);
  const [isSubmittingAuth, setIsSubmittingAuth] = useState<boolean>(false);
  const [setupMessage, setSetupMessage] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);

  const [cliStatus, setCliStatus] = useState<ColabCliStatus | null>(config.cli_status || null);
  const [isStartingCli, setIsStartingCli] = useState<boolean>(false);
  const [isStoppingCli, setIsStoppingCli] = useState<boolean>(false);

  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);
  const wasOpenRef = useRef<boolean>(false);

  const refreshPrereqs = async () => {
    setIsCheckingPrereqs(true);
    try {
      const api = getBackendApi();
      const [p, st] = await Promise.all([
        api.check_colab_cli_prereqs(),
        api.get_colab_cli_status(),
      ]);
      setPrereqs(p);
      setCliStatus(st);
      if (st && onCliStatusChange) onCliStatusChange(st);
    } catch (err: any) {
      setSetupError(err?.message || '環境チェックに失敗しました。');
    } finally {
      setIsCheckingPrereqs(false);
    }
  };

  useEffect(() => {
    const justOpened = isOpen && !wasOpenRef.current;
    wasOpenRef.current = isOpen;
    if (justOpened) {
      const mode: ColabMode = config.colab_mode || 'cli_ssh';
      setExecutionTarget(config.execution_target || 'local');
      setColabMode(mode);
      setServerUrl(config.server_url || '');
      setApiToken(config.api_token || '');
      setRememberToken(Boolean(config.remember_token));
      setTestResult(config.last_health ? { ok: true, health: config.last_health } : null);
      setCliGpu(config.cli_gpu || 'T4');
      setCliHighMem(config.cli_gpu === 'L4' ? false : Boolean(config.cli_high_mem));
      setCliUseDriveCache(Boolean(config.cli_use_drive_cache));
      setCliIdleMinutes(Number(config.cli_idle_timeout_minutes ?? 30));
      setCliStatus(config.cli_status || null);
      setFormError(null);
      setSetupMessage(null);
      setSetupError(null);
      setAuthUrl(null);
      setAuthCode('');
      if (mode === 'cli_ssh') {
        refreshPrereqs();
      }
    }
  }, [isOpen, config]);

  useEffect(() => {
    if (isOpen && config.cli_status) {
      setCliStatus(config.cli_status);
    }
  }, [isOpen, config.cli_status]);

  if (!isOpen) return null;

  const hasUnsavedUrlOrToken =
    serverUrl.trim() !== (config.server_url || '').trim() ||
    apiToken.trim() !== (config.api_token || '').trim();

  const handleSelectMode = (nextMode: ColabMode) => {
    setColabMode(nextMode);
    setFormError(null);
    if (nextMode === 'cli_ssh' && prereqs === null) {
      refreshPrereqs();
    }
  };

  const handleGpuSelect = (gpu: ColabGpuType) => {
    setCliGpu(gpu);
    if (gpu === 'L4') {
      setCliHighMem(false);
    }
  };

  const handleInstallCli = async () => {
    setSetupError(null);
    setSetupMessage(null);
    setIsInstallingCli(true);
    try {
      const res = await getBackendApi().install_colab_cli();
      setPrereqs(res.prereqs);
      if (res.ok) {
        setSetupMessage(res.message);
      } else {
        setSetupError(res.message);
      }
    } catch (err: any) {
      setSetupError(err?.message || 'Colab CLI のインストールに失敗しました。');
    } finally {
      setIsInstallingCli(false);
    }
  };

  const handleGenerateKey = async () => {
    setSetupError(null);
    setSetupMessage(null);
    setIsGeneratingKey(true);
    try {
      const res = await getBackendApi().generate_colab_ssh_key();
      setPrereqs(res.prereqs);
      if (res.ok) {
        setSetupMessage(res.message);
      } else {
        setSetupError(res.message);
      }
    } catch (err: any) {
      setSetupError(err?.message || 'SSH 鍵の生成に失敗しました。');
    } finally {
      setIsGeneratingKey(false);
    }
  };

  const handleStartAuth = async () => {
    setSetupError(null);
    setSetupMessage(null);
    setIsStartingAuth(true);
    try {
      const res = await getBackendApi().start_colab_cli_auth();
      if (res.status === 'awaiting_code' && res.auth_url) {
        setAuthUrl(res.auth_url);
        setAuthCode('');
        setSetupMessage(res.message || 'URL を開いて認証コードを入力してください。');
      } else if (res.status === 'already_authenticated') {
        setAuthUrl(null);
        if (res.prereqs) setPrereqs(res.prereqs);
        setSetupMessage(res.message || 'すでに認証済みです。');
      } else {
        setSetupError(res.message || 'Google 認証の開始に失敗しました。');
      }
    } catch (err: any) {
      setSetupError(err?.message || 'Google 認証の開始に失敗しました。');
    } finally {
      setIsStartingAuth(false);
    }
  };

  const handleSubmitAuthCode = async () => {
    if (!authCode.trim()) return;
    setSetupError(null);
    setSetupMessage(null);
    setIsSubmittingAuth(true);
    try {
      const res = await getBackendApi().submit_colab_cli_auth_code(authCode.trim());
      if (res.prereqs) setPrereqs(res.prereqs);
      if (res.ok) {
        setAuthUrl(null);
        setAuthCode('');
        setSetupMessage(res.message);
      } else {
        setSetupError(res.message);
      }
    } catch (err: any) {
      setSetupError(err?.message || '認証コード送信に失敗しました。');
    } finally {
      setIsSubmittingAuth(false);
    }
  };

  const handleCopyAuthUrl = () => {
    if (!authUrl || typeof navigator === 'undefined' || !navigator.clipboard) return;
    navigator.clipboard.writeText(authUrl).then(() => {
      setSetupMessage('認証 URL をクリップボードにコピーしました。');
    }).catch(() => {});
  };

  const buildCliConfigPayload = (gpuOverride?: ColabGpuType): Partial<ColabConfig> => {
    const gpu = gpuOverride || cliGpu;
    return {
      execution_target: executionTarget,
      colab_mode: colabMode,
      cli_gpu: gpu,
      cli_high_mem: gpu === 'L4' ? false : cliHighMem,
      cli_use_drive_cache: cliUseDriveCache,
      cli_idle_timeout_minutes: Math.max(0, Math.min(240, Number(cliIdleMinutes) || 0)),
    };
  };

  const handleStartCli = async (gpuOverride?: ColabGpuType) => {
    setFormError(null);
    const targetGpu = gpuOverride || cliGpu;
    if (gpuOverride) {
      handleGpuSelect(gpuOverride);
    }
    setIsStartingCli(true);
    try {
      const payload = buildCliConfigPayload(targetGpu);
      await onSave(payload);
      const res = await getBackendApi().start_colab_cli(payload);
      if (res?.cli_status) {
        setCliStatus(res.cli_status);
        if (onCliStatusChange) onCliStatusChange(res.cli_status);
      }
      if (!res?.ok && res?.error) {
        setFormError(res.error);
      }
    } catch (err: any) {
      setFormError(err?.message || 'Colab ランタイム起動に失敗しました。');
    } finally {
      setIsStartingCli(false);
    }
  };

  const handleStopCli = async () => {
    setFormError(null);
    setIsStoppingCli(true);
    try {
      const res = await getBackendApi().stop_colab_cli();
      if (res?.cli_status) {
        setCliStatus(res.cli_status);
        if (onCliStatusChange) onCliStatusChange(res.cli_status);
      }
      if (!res?.ok && res?.error) {
        setFormError(res.error);
      }
    } catch (err: any) {
      setFormError(err?.message || 'Colab ランタイム停止に失敗しました。');
    } finally {
      setIsStoppingCli(false);
    }
  };

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
      const payload: Partial<ColabConfig> =
        colabMode === 'cli_ssh'
          ? buildCliConfigPayload()
          : {
              execution_target: executionTarget,
              colab_mode: 'manual',
              server_url: serverUrl.trim(),
              api_token: apiToken.trim(),
              remember_token: rememberToken,
            };
      const res = await onSave(payload);
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

  const isL4 = cliGpu === 'L4';
  const cliRunning = cliStatus?.state === 'running';
  const cliBusyTransition = isStartingCli || isStoppingCli || cliStatus?.state === 'starting';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[1px] p-4 select-none"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl max-h-[90vh] flex flex-col bg-white rounded-xl border border-[#D4DFDC] shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-3.5 bg-[#F8FAFC] border-b border-[#E2E8F0] flex items-center justify-between flex-shrink-0">
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
        <div className="p-5 space-y-4 overflow-y-auto">
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

          {/* Connection mode tab switcher */}
          <div>
            <label className="block text-xs font-bold text-[#334155] mb-1.5">
              Colab 接続方式
            </label>
            <div className="grid grid-cols-2 gap-1.5 p-1 rounded-lg bg-[#F1F5F9] border border-[#CBD5E1]">
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => handleSelectMode('cli_ssh')}
                className={`py-1.5 px-2.5 rounded-md text-xs font-bold transition-all ${
                  colabMode === 'cli_ssh'
                    ? 'bg-white text-[#0F766E] shadow-xs'
                    : 'text-[#64748B] hover:text-[#1E293B]'
                } ${isProcessing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                SSH直結（自動・推奨）
              </button>
              <button
                type="button"
                disabled={isProcessing}
                onClick={() => handleSelectMode('manual')}
                className={`py-1.5 px-2.5 rounded-md text-xs font-bold transition-all ${
                  colabMode === 'manual'
                    ? 'bg-white text-[#0F766E] shadow-xs'
                    : 'text-[#64748B] hover:text-[#1E293B]'
                } ${isProcessing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                手動URL（従来ノートブック）
              </button>
            </div>
          </div>

          {colabMode === 'cli_ssh' ? (
            <div className="space-y-4">
              <p className="text-xs text-[#475569] leading-relaxed">
                ブラウザ操作・URL コピペなしで手元 PC から直接 Colab GPU を起動し、OpenSSH トンネルで接続します。
                （推論のみ Colab で行い、3 本の MP4 書き出しはローカルで並列実行します）
              </p>

              {/* Prerequisites & GUI OAuth Setup Card */}
              <div className="p-3.5 rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-[#1E293B] flex items-center gap-1.5">
                    <Settings className="w-3.5 h-3.5 text-[#0F766E]" />
                    <span>PC セットアップ状況</span>
                  </span>
                  <button
                    type="button"
                    onClick={refreshPrereqs}
                    disabled={isCheckingPrereqs}
                    className="inline-flex items-center gap-1 text-[11px] font-bold text-[#0F766E] hover:underline cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3 h-3 ${isCheckingPrereqs ? 'animate-spin' : ''}`} />
                    <span>再確認</span>
                  </button>
                </div>

                {prereqs ? (
                  <div className="space-y-2 text-xs">
                    {/* 1. Colab CLI */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        {prereqs.colab_installed ? (
                          <CheckCircle className="w-3.5 h-3.5 text-[#16A34A]" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5 text-[#DC2626]" />
                        )}
                        <span className="font-medium text-[#334155]">
                          Colab CLI {prereqs.colab_installed ? '導入済' : '未導入'}
                        </span>
                      </div>
                      {!prereqs.colab_installed && (
                        <button
                          type="button"
                          onClick={handleInstallCli}
                          disabled={isInstallingCli || !prereqs.uv_installed}
                          className="px-2.5 py-1 rounded border border-[#0F766E] text-[11px] font-bold text-[#0F766E] bg-white hover:bg-[#F0FDF9] cursor-pointer disabled:opacity-50"
                        >
                          {isInstallingCli
                            ? '導入中...'
                            : prereqs.uv_installed
                            ? 'uv で自動インストール'
                            : 'uv 未検出'}
                        </button>
                      )}
                    </div>

                    {/* 2. SSH Key */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        {prereqs.ssh_installed && prereqs.ssh_key_exists ? (
                          <CheckCircle className="w-3.5 h-3.5 text-[#16A34A]" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5 text-[#D97706]" />
                        )}
                        <span className="font-medium text-[#334155]">
                          SSH 鍵 (ed25519){' '}
                          {!prereqs.ssh_installed
                            ? 'OpenSSH クライアント未導入'
                            : prereqs.ssh_key_exists
                            ? '準備完了'
                            : '未作成'}
                        </span>
                      </div>
                      {prereqs.ssh_installed && !prereqs.ssh_key_exists && (
                        <button
                          type="button"
                          onClick={handleGenerateKey}
                          disabled={isGeneratingKey}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-[#0F766E] text-[11px] font-bold text-[#0F766E] bg-white hover:bg-[#F0FDF9] cursor-pointer disabled:opacity-50"
                        >
                          <Link2 className="w-3 h-3" />
                          <span>{isGeneratingKey ? '生成中...' : 'SSH 鍵を自動生成'}</span>
                        </button>
                      )}
                    </div>

                    {/* 3. Google Auth */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {prereqs.auth_ok ? (
                          <CheckCircle className="w-3.5 h-3.5 text-[#16A34A] flex-shrink-0" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5 text-[#D97706] flex-shrink-0" />
                        )}
                        <span className="font-medium text-[#334155] truncate">
                          Google 認証 {prereqs.auth_ok ? 'ログイン済' : '未認証'}
                          {prereqs.auth_ok && prereqs.usage_summary?.balance != null
                            ? `（残 ${prereqs.usage_summary.balance.toFixed(1)} CU）`
                            : ''}
                        </span>
                      </div>
                      {prereqs.colab_installed && (
                        <button
                          type="button"
                          onClick={handleStartAuth}
                          disabled={isStartingAuth}
                          className="px-2.5 py-1 rounded border border-[#CBD5E1] text-[11px] font-bold text-[#334155] bg-white hover:bg-[#F1F5F9] cursor-pointer disabled:opacity-50 flex-shrink-0"
                        >
                          {isStartingAuth
                            ? '準備中...'
                            : prereqs.auth_ok
                            ? '別アカウントで再認証'
                            : 'Google 認証を開始'}
                        </button>
                      )}
                    </div>

                    {/* Interactive OAuth Code Entry */}
                    {authUrl && (
                      <div className="mt-2 p-2.5 rounded-lg bg-white border border-[#99F6E4] space-y-2">
                        <div className="text-[11px] font-bold text-[#0F766E]">
                          1. 下記リンクをブラウザで開いて許可し、表示された認証コードを貼り付けてください
                        </div>
                        <div className="flex items-center gap-1.5">
                          <a
                            href={authUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded bg-[#0F766E] text-white text-[11px] font-bold hover:bg-[#115E59] flex-shrink-0"
                          >
                            <ExternalLink className="w-3 h-3" />
                            <span>ブラウザで開く</span>
                          </a>
                          <input
                            type="text"
                            readOnly
                            value={authUrl}
                            className="flex-1 min-w-0 px-2 py-1 text-[10px] font-mono bg-[#F8FAFC] border border-[#CBD5E1] rounded select-text"
                          />
                          <button
                            type="button"
                            onClick={handleCopyAuthUrl}
                            className="p-1.5 rounded border border-[#CBD5E1] text-[#475569] hover:bg-[#F1F5F9] cursor-pointer"
                            title="URL をコピー"
                          >
                            <FileText className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <input
                            type="text"
                            value={authCode}
                            onChange={(e) => setAuthCode(e.target.value)}
                            placeholder="2. 取得した認証コード（4/...）を貼り付け"
                            className="flex-1 px-2.5 py-1.5 text-xs font-mono border border-[#CBD5E1] rounded focus:outline-none focus:border-[#0F766E] select-text"
                          />
                          <button
                            type="button"
                            onClick={handleSubmitAuthCode}
                            disabled={isSubmittingAuth || !authCode.trim()}
                            className="px-3 py-1.5 rounded bg-[#0F766E] text-white text-xs font-bold hover:bg-[#115E59] cursor-pointer disabled:opacity-50"
                          >
                            {isSubmittingAuth ? '確認中...' : '認証コード送信'}
                          </button>
                        </div>
                      </div>
                    )}

                    {setupMessage && (
                      <div className="text-[11px] text-[#15803D] font-medium">{setupMessage}</div>
                    )}
                    {setupError && (
                      <div className="text-[11px] text-[#B91C1C] font-medium whitespace-pre-wrap">
                        {setupError}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-[#64748B] flex items-center gap-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>PC 環境を確認中...</span>
                  </div>
                )}
              </div>

              {/* GPU & Runtime Options */}
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-bold text-[#334155] mb-1.5">
                    使用 GPU アクセラレータ
                  </label>
                  <div className="grid grid-cols-5 gap-1.5">
                    {GPU_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        disabled={isProcessing || cliBusyTransition}
                        onClick={() => handleGpuSelect(opt.value)}
                        className={`py-1.5 px-2 rounded-lg border text-center transition-all ${
                          cliGpu === opt.value
                            ? 'bg-[#E2F2EE] border-[#0F766E] text-[#0B534D]'
                            : 'bg-white border-[#CBD5E1] text-[#475569] hover:bg-[#F8FAFC]'
                        } ${isProcessing || cliBusyTransition ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                        title={opt.hint}
                      >
                        <div className="text-xs font-bold">{opt.label}</div>
                        <div className="text-[10px] text-[#64748B] truncate">{opt.hint}</div>
                      </button>
                    ))}
                  </div>
                  <p className="mt-1 text-[11px] text-[#64748B]">
                    ※ 利用可能な GPU・Compute Units 消費レートは Google Colab の契約プランと空き枠に依存します。
                  </p>
                </div>

                {/* High-RAM toggle */}
                <div>
                  <label
                    className={`inline-flex items-center gap-2 text-xs ${
                      isL4 ? 'text-[#94A3B8] cursor-not-allowed' : 'text-[#334155] cursor-pointer'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={!isL4 && cliHighMem}
                      disabled={isL4 || isProcessing || cliBusyTransition}
                      onChange={(e) => setCliHighMem(e.target.checked)}
                      className="rounded border-[#CBD5E1] text-[#0F766E]"
                    />
                    <span className="font-bold">High-RAM ランタイムを使用 (`--high-mem`)</span>
                  </label>
                  {isL4 && (
                    <p className="mt-0.5 pl-6 text-[11px] text-[#64748B]">
                      ※ L4 は単一（High-RAM）構成のみのため選択不要です（指定不可）。
                    </p>
                  )}
                </div>

                {/* Drive Cache toggle (default OFF) */}
                <div>
                  <label className="inline-flex items-center gap-2 text-xs text-[#334155] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={cliUseDriveCache}
                      disabled={isProcessing || cliBusyTransition}
                      onChange={(e) => setCliUseDriveCache(e.target.checked)}
                      className="rounded border-[#CBD5E1] text-[#0F766E]"
                    />
                    <span className="font-bold">Google Drive にモデルキャッシュを同期する</span>
                  </label>
                  <p className="mt-0.5 pl-6 text-[11px] text-[#64748B]">
                    ※ 既定 OFF。OFF でも推論機能は同じです。ON 時に Drive 側障害等でマウント失敗しても警告のみでローカルキャッシュへ自動フォールバックします。
                  </p>
                </div>

                {/* Idle timeout minutes */}
                <div>
                  <div className="flex items-center gap-3">
                    <label className="text-xs font-bold text-[#334155]">
                      無操作時の自動停止（分）:
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={240}
                      value={cliIdleMinutes}
                      disabled={isProcessing}
                      onChange={(e) =>
                        setCliIdleMinutes(Math.max(0, Math.min(240, Number(e.target.value) || 0)))
                      }
                      className="w-20 px-2.5 py-1 text-xs font-mono border border-[#CBD5E1] rounded-lg focus:outline-none focus:border-[#0F766E] select-text"
                    />
                    <span className="text-[11px] text-[#64748B]">（0 で自動停止無効 / 既定 30分）</span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-[#64748B]">
                    ※ 予約一覧に未開始の動画があっても、解析処理が止まっていれば指定時間で `colab stop` を自動実行します（終了時・リモート無通信30分でも自動停止）。
                  </p>
                </div>
              </div>

              {/* Manual Start / Stop & Live Status Card */}
              <div className="pt-1 space-y-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleStartCli()}
                    disabled={isProcessing || cliBusyTransition || !prereqs?.ok}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold bg-[#0F766E] text-white hover:bg-[#115E59] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isStartingCli ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Play className="w-3.5 h-3.5 fill-current" />
                    )}
                    <span>
                      {isStartingCli
                        ? '起動・接続中...'
                        : cliRunning
                        ? '再接続 / 設定反映'
                        : '今すぐ起動・接続'}
                    </span>
                  </button>

                  <button
                    type="button"
                    onClick={handleStopCli}
                    disabled={isProcessing || cliBusyTransition || cliStatus?.state === 'stopped'}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold border border-[#F5C2C0] text-[#C8332B] bg-white hover:bg-[#FEF2F2] cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isStoppingCli ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Square className="w-3.5 h-3.5 fill-current" />
                    )}
                    <span>{isStoppingCli ? '停止中...' : 'ランタイムを停止'}</span>
                  </button>
                </div>

                {cliStatus && (
                  <div
                    className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                      cliStatus.state === 'running'
                        ? 'bg-[#F0FDF4] border-[#BBF7D0] text-[#166534]'
                        : cliStatus.state === 'error'
                        ? 'bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C]'
                        : 'bg-[#F8FAFC] border-[#E2E8F0] text-[#334155]'
                    }`}
                  >
                    <div className="flex items-center justify-between font-bold">
                      <span>状態: {cliStatus.status_message}</span>
                      {cliStatus.state === 'running' &&
                        cliStatus.idle_remaining_sec != null &&
                        cliStatus.idle_timeout_minutes > 0 && (
                          <span className="text-[11px]">
                            自動停止まで約 {Math.max(1, Math.ceil(cliStatus.idle_remaining_sec / 60))} 分
                          </span>
                        )}
                    </div>

                    {cliStatus.last_health && (
                      <div className="text-[11px]">
                        GPU: {cliStatus.last_health.gpu_name || cliStatus.gpu}
                        {' · '}
                        VRAM: {cliStatus.last_health.vram_free_gb ?? '?'} /{' '}
                        {cliStatus.last_health.vram_total_gb ?? '?'} GB
                        {' · '}
                        RAM空き: {cliStatus.last_health.ram_available_gb ?? '?'} /{' '}
                        {cliStatus.last_health.ram_total_gb ?? '?'} GB
                      </div>
                    )}

                    {cliStatus.warnings && cliStatus.warnings.length > 0 && (
                      <div className="pt-1 space-y-1">
                        {cliStatus.warnings.map((w, idx) => (
                          <div key={idx} className="flex items-start gap-1.5 text-[11px] text-[#92400E]">
                            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                            <span>{w}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {cliStatus.error && (
                      <div className="pt-1 space-y-1.5">
                        <div className="break-all text-[11px]">{cliStatus.error}</div>
                        {cliStatus.suggest_switch_to_t4 && cliGpu !== 'T4' && (
                          <button
                            type="button"
                            onClick={() => handleStartCli('T4')}
                            disabled={isStartingCli}
                            className="px-2.5 py-1 rounded bg-[#0F766E] text-white text-[11px] font-bold hover:bg-[#115E59] cursor-pointer"
                          >
                            T4 に切り替えて再試行
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-xs text-[#475569] leading-relaxed">
                Colab ノートブック（<code>launch_colab_server.ipynb</code>）の出力に表示された公開 URL と
                API トークンを入力してください。推論のみを Colab GPU で実行し、3 本の MP4 動画は手元の PC で並列生成します。
              </p>

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
            </div>
          )}

          {formError && (
            <div className="p-2.5 rounded-lg bg-[#FEF2F2] border border-[#FECACA] text-xs text-[#B91C1C] break-all">
              {formError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-[#F8FAFC] border-t border-[#E2E8F0] flex items-center justify-end gap-2 flex-shrink-0">
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
