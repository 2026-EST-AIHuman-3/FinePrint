import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, FileText, Globe, Play, Search, Upload } from "lucide-react";
import type { AnalysisType, AnalyzeSubmission, DocumentType } from "../lib/fineprintApi";

interface HomeWorkspaceProps {
  onAnalyze: (submission: AnalyzeSubmission) => void;
  isLoading: boolean;
  fallbackServiceName?: string | null;
}

export default function HomeWorkspace({
  onAnalyze,
  isLoading,
  fallbackServiceName,
}: HomeWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<AnalysisType>("name");
  const [serviceName, setServiceName] = useState("");
  const [url, setUrl] = useState("");
  const [documentType, setDocumentType] = useState<DocumentType>("terms");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!fallbackServiceName) return;
    setServiceName(fallbackServiceName);
    setActiveTab("url");
  }, [fallbackServiceName]);

  const selectTab = (tab: AnalysisType) => {
    setActiveTab(tab);
    setUrl("");
    setFile(null);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const normalizedName = serviceName.trim();
    if (!normalizedName) return;
    if (activeTab === "url" && !url.trim()) return;
    if (activeTab === "document" && !file) return;

    onAnalyze({
      type: activeTab,
      serviceName: normalizedName,
      url: activeTab === "url" ? url.trim() : undefined,
      documentType: activeTab === "name" ? undefined : documentType,
      file: activeTab === "document" ? file || undefined : undefined,
    });
  };

  const acceptFile = (candidate: File) => {
    const extension = candidate.name.split(".").pop()?.toLowerCase();
    if (extension !== "pdf" && extension !== "txt") return;
    setFile(candidate);
  };

  const canSubmit =
    serviceName.trim().length > 0 &&
    (activeTab === "name" ||
      (activeTab === "url" && url.trim().length > 0) ||
      (activeTab === "document" && Boolean(file)));

  return (
    <div className="flex-1 flex flex-col items-center justify-start md:justify-center px-6 md:px-12 py-12 relative overflow-y-auto w-full h-full">
      <div className="max-w-3xl w-full text-center mb-8 z-10">
        <div className="flex justify-center mb-5">
          <img
            alt="FinePrint Logo"
            className="w-[640px] md:w-[800px] max-w-full h-auto object-contain select-none pointer-events-none"
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuB550ld8eJ9KDDoWjvwOC1BWPx3hrruSwjWkIRsgGXnrETxzT0BoA4NPcoVP_jp1wMW6MW1lbmgaby9_7ZccuEw9qo00lnPVX4CqJBc-7KXMLQKuWBtHJQeWBOM_OYFVt1wrnRmEsTd5RrJxbN4lGyzm5hijJrNxh6lFwoIZ1X6EQCkeYNG_z3rdvKxjaAC23wGPWvX17uUZriDR0il5EEn674HOgxCjhi7otMNdGtbHkqj72oUY9PNiq2sWdNDQL6MEw"
            referrerPolicy="no-referrer"
          />
        </div>
        <h2 className="text-2xl md:text-4xl font-headline font-bold text-on-surface mb-3 tracking-tight">
          구독 서비스 약관 분석 및 문제 해결 안내 서비스
        </h2>
        <p className="text-sm md:text-base text-on-surface-variant max-w-xl mx-auto opacity-90 leading-relaxed">
          서비스명을 입력하면 기존 DB를 확인하고, 없을 때 공식 약관을 자동으로 수집합니다.
        </p>
      </div>

      <div className="w-full max-w-2xl z-10">
        {fallbackServiceName && (
          <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 flex gap-3 text-left shadow-sm">
            <AlertTriangle className="text-amber-600 shrink-0" size={20} />
            <div>
              <p className="text-sm font-bold text-amber-900">자동 수집에서 약관을 찾지 못했습니다.</p>
              <p className="text-xs text-amber-800 mt-1 leading-relaxed">
                <strong>{fallbackServiceName}</strong>의 공식 약관 URL을 입력하거나 PDF/TXT 파일을 업로드해 주세요.
              </p>
            </div>
          </div>
        )}

        <div className="flex justify-center gap-3 md:gap-4 mb-6">
          {([
            ["name", Search, "서비스명"],
            ["url", Globe, "URL"],
            ["document", FileText, "문서 업로드"],
          ] as const).map(([tab, Icon, label]) => (
            <button
              key={tab}
              id={`tab-${tab}`}
              type="button"
              onClick={() => selectTab(tab)}
              className={`px-5 py-3 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 border active:scale-95 cursor-pointer ${
                activeTab === tab
                  ? "bg-primary text-on-primary border-primary shadow-sm"
                  : "bg-surface-white text-on-surface border-outline-variant/30 hover:border-primary/50"
              }`}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="relative bg-surface-white border-2 border-border-muted rounded-3xl p-5 md:p-6 shadow-sm space-y-4">
          <label className="block">
            <span className="block text-xs font-bold text-on-surface-variant mb-2">서비스명</span>
            <div className="flex items-center gap-3 rounded-xl border border-border-muted px-4 py-3 focus-within:border-primary">
              <Search size={17} className="text-primary shrink-0" />
              <input
                id="service-name-input"
                value={serviceName}
                onChange={(event) => setServiceName(event.target.value)}
                disabled={isLoading}
                placeholder="예: TVING, Netflix, Adobe Creative Cloud"
                className="w-full bg-transparent outline-none text-sm text-on-surface placeholder-on-surface-variant/40"
              />
            </div>
          </label>

          {activeTab !== "name" && (
            <label className="block">
              <span className="block text-xs font-bold text-on-surface-variant mb-2">문서 종류</span>
              <select
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value as DocumentType)}
                disabled={isLoading}
                className="w-full rounded-xl border border-border-muted bg-white px-4 py-3 text-sm outline-none focus:border-primary"
              >
                <option value="terms">이용약관</option>
                <option value="privacy">개인정보처리방침</option>
              </select>
            </label>
          )}

          {activeTab === "url" && (
            <label className="block">
              <span className="block text-xs font-bold text-on-surface-variant mb-2">공식 문서 URL</span>
              <div className="flex items-center gap-3 rounded-xl border border-border-muted px-4 py-3 focus-within:border-primary">
                <Globe size={17} className="text-primary shrink-0" />
                <input
                  id="policy-url-input"
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  disabled={isLoading}
                  placeholder="https://example.com/terms"
                  className="w-full bg-transparent outline-none text-sm text-on-surface placeholder-on-surface-variant/40"
                />
              </div>
            </label>
          )}

          {activeTab === "document" && (
            <div>
              <input
                ref={fileInputRef}
                id="file-picker-input"
                type="file"
                accept=".pdf,.txt,application/pdf,text/plain"
                className="hidden"
                onChange={(event) => event.target.files?.[0] && acceptFile(event.target.files[0])}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setIsDragging(false);
                  if (event.dataTransfer.files[0]) acceptFile(event.dataTransfer.files[0]);
                }}
                className={`w-full rounded-2xl border-2 border-dashed p-6 text-center transition-colors ${
                  isDragging ? "border-primary bg-primary/10" : "border-border-muted hover:border-primary/50"
                }`}
              >
                <Upload size={25} className="mx-auto text-primary mb-2" />
                <p className="text-sm font-bold text-on-surface">
                  {file ? file.name : "PDF/TXT 파일 선택 또는 드래그"}
                </p>
                <p className="text-xs text-on-surface-variant/60 mt-1">
                  {file ? `${(file.size / 1024).toFixed(1)} KB` : "최대 20MB"}
                </p>
              </button>
            </div>
          )}

          <button
            id="analysis-submit"
            type="submit"
            disabled={isLoading || !canSubmit}
            className={`w-full rounded-xl py-3.5 flex items-center justify-center gap-2 font-bold text-sm transition-all ${
              canSubmit && !isLoading
                ? "bg-primary text-on-primary hover:bg-primary/90 cursor-pointer active:scale-[0.99]"
                : "bg-outline-variant/40 text-on-surface-variant/50 cursor-not-allowed"
            }`}
          >
            {isLoading ? (
              <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : activeTab === "name" ? (
              <Play size={17} fill="currentColor" />
            ) : activeTab === "url" ? (
              <Globe size={17} />
            ) : (
              <Upload size={17} />
            )}
            {activeTab === "name" ? "서비스 준비하기" : activeTab === "url" ? "URL 등록하기" : "문서 등록하기"}
          </button>
        </form>
      </div>
    </div>
  );
}
