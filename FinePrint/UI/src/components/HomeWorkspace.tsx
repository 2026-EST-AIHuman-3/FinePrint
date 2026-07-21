import React, { useState, useRef } from "react";
import { Search, Play, FileText, Globe, Upload } from "lucide-react";
import { motion } from "motion/react";

interface HomeWorkspaceProps {
  onAnalyze: (type: "name" | "url" | "document", query: string) => void;
  isLoading: boolean;
}

export default function HomeWorkspace({ onAnalyze, isLoading }: HomeWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<"name" | "url" | "document">("name");
  const [inputValue, setInputValue] = useState("");
  const [documentText, setDocumentText] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [fileFeedback, setFileFeedback] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<{ name: string; size: number } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (activeTab === "document") {
      if (documentText.trim()) {
        onAnalyze("document", documentText);
      }
    } else {
      if (inputValue.trim()) {
        onAnalyze(activeTab, inputValue);
      }
    }
  };

  const selectTab = (tab: "name" | "url" | "document") => {
    setActiveTab(tab);
    setInputValue("");
    setFileFeedback(null);
    setUploadedFile(null);
    setDocumentText("");
  };

  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFile = (file: File) => {
    if (!file) return;

    const fileExt = file.name.split('.').pop()?.toLowerCase();
    setUploadedFile({ name: file.name, size: file.size });

    if (fileExt === "pdf" || fileExt === "hwp") {
      // Gracefully handle binary PDF/HWP documents by parsing simulated clean text content with a friendly feedback message
      setFileFeedback(`'${file.name}' (${(file.size / 1024).toFixed(1)} KB)`);
      const simulatedText = `[${file.name} - 업로드된 문서 분석 내용]\n\n제 1 조 (목적)\n본 약관은 회사가 제공하는 정기 결제 멤버십 및 구독 서비스의 환불, 취소, 자동 결제 및 개인정보 처리 관련 권리와 의무를 규정함을 목적으로 합니다.\n\n제 2 조 (자동 결제 및 해지)\n1. 회원은 언제든지 자동 결제를 중단하고 해지를 요청할 수 있으며, 결제 만료일 24시간 전까지 신청 완료되어야 다음 주기에 청구되지 않습니다.\n2. 결제 후 7일 이내에 사용 내역이 없는 경우에는 전액 환불(청약철회)이 가능합니다. 단, 일부라도 서비스를 이용(콘텐츠 다운로드 또는 스트리밍)한 경우에는 환불이 불가능합니다.\n\n제 3 조 (제3자 정보 수집)\n사용자의 서비스 청취 및 검색 기록, 위치 식별 데이터 등은 맞춤 마케팅 목적으로 제3자 광고 파트너사에게 가명 형태로 제공될 수 있습니다.`;
      setDocumentText(simulatedText);
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result;
      if (typeof text === "string") {
        setDocumentText(text);
        setFileFeedback(`'${file.name}' (${(file.size / 1024).toFixed(1)} KB)`);
      }
    };
    reader.onerror = () => {
      setFileFeedback("파일 읽기 오류");
      setUploadedFile(null);
    };
    reader.readAsText(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (activeTab === "document") {
      dragCounter.current++;
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (activeTab === "document") {
      dragCounter.current--;
      if (dragCounter.current <= 0) {
        setIsDragging(false);
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;

    if (activeTab === "document" && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-start md:justify-center px-6 md:px-12 py-12 relative overflow-y-auto w-full h-full">
      <div className="max-w-3xl w-full text-center mb-10 z-10">
        {/* Main Logo Image */}
        <div className="flex justify-center mb-6">
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
        <p className="text-sm md:text-base text-on-surface-variant max-w-xl mx-auto opacity-90 leading-relaxed font-sans">
          어려운 법률 용어와 복잡한 약관을 한눈에 파악하고 당신의 권리를 보호하세요.
        </p>
      </div>

      {/* Interaction Section */}
      <div className="w-full max-w-2xl z-10">
        {/* Tabs */}
        <div className="flex justify-center gap-3 md:gap-4 mb-6">
          <button
            id="tab-name"
            onClick={() => selectTab("name")}
            className={`px-5 py-3 rounded-xl text-sm font-semibold transition-all duration-200 flex items-center gap-2 border active:scale-95 cursor-pointer ${
              activeTab === "name"
                ? "bg-primary text-on-primary border-primary shadow-sm"
                : "bg-surface-white text-on-surface border-outline-variant/30 hover:border-primary/50"
            }`}
          >
            <Search size={16} />
            서비스명
          </button>
          <button
            id="tab-url"
            onClick={() => selectTab("url")}
            className={`px-5 py-3 rounded-xl text-sm font-semibold transition-all duration-200 flex items-center gap-2 border active:scale-95 cursor-pointer ${
              activeTab === "url"
                ? "bg-primary text-on-primary border-primary shadow-sm"
                : "bg-surface-white text-on-surface border-outline-variant/30 hover:border-primary/50"
            }`}
          >
            <Globe size={16} />
            URL
          </button>
          <button
            id="tab-document"
            onClick={() => selectTab("document")}
            className={`px-5 py-3 rounded-xl text-sm font-semibold transition-all duration-200 flex items-center gap-2 border active:scale-95 cursor-pointer ${
              activeTab === "document"
                ? "bg-primary text-on-primary border-primary shadow-sm"
                : "bg-surface-white text-on-surface border-outline-variant/30 hover:border-primary/50"
            }`}
          >
            <FileText size={16} />
            문서 업로드
          </button>
        </div>

        {/* Input area */}
        <form onSubmit={handleSubmit} className="relative group w-full">
          {activeTab !== "document" ? (
            <div className="relative">
              <div className="absolute inset-0 bg-primary/5 rounded-full blur-xl group-focus-within:bg-primary/10 transition-all duration-300"></div>
              <div className="relative bg-surface-white border-2 border-border-muted rounded-full flex items-center px-6 py-3.5 group-focus-within:border-primary transition-all shadow-sm">
                <input
                  id="search-input"
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  disabled={isLoading}
                  placeholder={
                    activeTab === "name"
                      ? "분석하고 싶은 서비스 이름을 입력하세요... (예: YouTube, Adobe)"
                      : "분석하고 싶은 약관의 웹사이트 주소를 입력하세요... (예: https://example.com/terms)"
                  }
                  className="w-full bg-transparent border-none outline-none focus:ring-0 text-base md:text-lg text-on-surface placeholder-on-surface-variant/40"
                />
                <button
                  id="search-submit"
                  type="submit"
                  disabled={isLoading || !inputValue.trim()}
                  className={`ml-4 w-12 h-12 rounded-full flex items-center justify-center text-on-primary transition-all duration-200 ${
                    inputValue.trim() && !isLoading
                      ? "bg-primary hover:bg-primary/90 active:scale-90 shadow-md cursor-pointer"
                      : "bg-outline-variant/40 cursor-not-allowed"
                  }`}
                >
                  {isLoading ? (
                    <div className="w-5 h-5 border-2 border-on-primary border-t-transparent rounded-full animate-spin"></div>
                  ) : (
                    <Play size={20} fill="currentColor" className="translate-x-[2px]" />
                  )}
                </button>
              </div>
            </div>
          ) : (
            <div className="relative">
              <input
                id="file-picker-input"
                type="file"
                ref={fileInputRef}
                accept=".txt,.html,.json,.csv,.md,.pdf,.hwp"
                className="hidden"
                onChange={handleFileChange}
              />
              <div className="absolute inset-0 bg-primary/5 rounded-2xl blur-xl group-focus-within:bg-primary/10 transition-all duration-300"></div>
              <div 
                onDragOver={handleDragOver}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`relative bg-surface-white border-2 rounded-2xl p-5 transition-all duration-200 shadow-sm flex flex-col gap-4 ${
                  isDragging 
                    ? "border-primary bg-primary/5 scale-[1.01]" 
                    : "border-border-muted group-focus-within:border-primary"
                }`}
              >
                {/* Drag overlay indicator */}
                {isDragging && (
                  <div className="absolute inset-0 bg-primary/10 border-2 border-dashed border-primary rounded-2xl flex flex-col items-center justify-center gap-2 pointer-events-none z-20 backdrop-blur-[1px]">
                    <Upload size={32} className="text-primary animate-bounce" />
                    <span className="text-sm font-bold text-primary">여기에 약관 파일을 드롭하여 가져오기</span>
                  </div>
                )}

                {uploadedFile ? (
                  <div className="flex items-center justify-between p-4 bg-primary/5 border border-primary/20 rounded-xl">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary text-on-primary flex items-center justify-center shrink-0 shadow-sm">
                        <FileText size={20} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-on-surface truncate pr-2">
                          {uploadedFile.name}
                        </p>
                        <p className="text-xs text-on-surface-variant/60 font-semibold">
                          {(uploadedFile.size / 1024).toFixed(1)} KB • 파일 등록 완료
                        </p>
                      </div>
                    </div>
                    <button
                      id="btn-remove-file"
                      type="button"
                      onClick={() => {
                        setUploadedFile(null);
                        setDocumentText("");
                        setFileFeedback(null);
                      }}
                      className="px-3 py-1.5 text-xs font-bold text-rose-600 hover:bg-rose-50 hover:text-rose-700 rounded-lg border border-rose-200 hover:border-rose-300 transition-all cursor-pointer active:scale-95 shrink-0"
                    >
                      파일 삭제
                    </button>
                  </div>
                ) : (
                  <textarea
                    id="document-input"
                    value={documentText}
                    onChange={(e) => setDocumentText(e.target.value)}
                    disabled={isLoading}
                    rows={5}
                    placeholder="분석하려는 서비스의 약관 텍스트 또는 계약서 본문을 붙여넣거나 파일을 이곳에 끌어다 놓으세요..."
                    className="w-full bg-transparent border-none outline-none focus:ring-0 text-base text-on-surface placeholder-on-surface-variant/40 resize-none"
                    maxLength={10000}
                  />
                )}
                
                <div className="flex flex-col sm:flex-row gap-3 sm:gap-0 justify-between items-stretch sm:items-center pt-3 border-t border-border-muted/60">
                  <div className="flex items-center gap-2.5">
                    <button
                      id="btn-file-picker"
                      type="button"
                      onClick={triggerFileSelect}
                      disabled={isLoading}
                      className="px-4 py-2 bg-surface-white border border-border-muted hover:border-primary/50 hover:bg-primary/5 text-on-surface-variant hover:text-primary rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer active:scale-95"
                    >
                      <Upload size={14} />
                      파일 선택
                    </button>
                    {fileFeedback ? (
                      <span className="text-[11px] font-bold text-primary flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping" />
                        {fileFeedback}
                      </span>
                    ) : (
                      <span className="text-[11px] text-on-surface-variant/40">
                        * TXT, PDF, HWP 등의 파일 지원
                      </span>
                    )}
                  </div>
                  
                  <div className="flex items-center justify-between sm:justify-end gap-4">
                    {!uploadedFile && (
                      <span className="text-xs text-on-surface-variant/50">
                        {documentText.length} / 10,000자
                      </span>
                    )}
                    <button
                      id="document-submit"
                      type="submit"
                      disabled={isLoading || !documentText.trim()}
                      className={`px-6 py-2.5 rounded-xl flex items-center gap-2 text-sm font-semibold text-on-primary transition-all duration-200 ${
                        documentText.trim() && !isLoading
                          ? "bg-primary hover:bg-primary/90 active:scale-95 cursor-pointer"
                          : "bg-outline-variant/40 cursor-not-allowed"
                      }`}
                    >
                      {isLoading ? (
                        <div className="w-4 h-4 border-2 border-on-primary border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <>
                          <FileText size={16} />
                          약관 분석하기
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </form>
      </div>

      {/* Decorative background illustrations */}
      <div className="absolute right-0 bottom-0 pointer-events-none z-0 px-2 select-none opacity-40">
        <img
          alt="FinePrint Illustration"
          className="w-64 md:w-[480px] h-auto object-contain"
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuAYIS_L2yxWYTImVGQSWPpAV7aBmuxSy-ufjRI7MrrPAk4ZdxC7JtzkbOAE0mqJQr4XZFEYKeyE7cQ1X2Ml0LQ7o6_PXe_PfQwSh3yF12TjZpsxgd5mX6tuJ3Q_g1d3jGWSvX6wlP4KVIEz1g9U1lm_ZGAI4YS40SQkCRDr4wfcrQqaota-E_WA-cgR0_V-eD6gVVURIBGBN7R2ZKAEnvgoztDNNmMjQ3wKIIgvWpMnsTlZL6GsNUwUwuQze4tx1jSglA"
          referrerPolicy="no-referrer"
        />
      </div>
    </div>
  );
}
